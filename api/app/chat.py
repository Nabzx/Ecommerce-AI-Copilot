"""
The copilot.

Answers two kinds of question the owner actually asks:

  * about the numbers — "how did we do this week?", "what do I need to reorder?"
  * about the store — "what's our returns policy again?", "does the tee run small?"

Both get handled the same way: gather the relevant context, hand it to the
model, and stream the answer back. The numbers come from a snapshot built
fresh on every question, and the store knowledge comes from retrieval, so
every qualitative claim can point at the document it came from.

There's no tool-calling here on purpose. The set of things worth looking up is
small and known, so fetching all of it up front is simpler, one round trip
faster, and works with the small local models this is meant to run on.
"""

import json
from collections.abc import AsyncIterator

from sqlmodel import Session

from app import metrics, rag
from app.config import settings
from app.llm import LLMError, LLMUnavailable, llm

SYSTEM_PROMPT = """You are the assistant inside StoreSense, a dashboard for {store}, a small clothing brand.
You are talking to the owner. They are busy and they know their own store.

The question comes with two blocks of context: <store_data> holds the current figures
and <store_knowledge> holds the relevant bits of the shop's own documents.

How to answer:
- Answer the question. Never repeat, quote or summarise the context blocks or their
  headings — the owner cannot see them and does not want them read back.
- Be direct and short. Two or three sentences unless they asked for detail.
- Lead with the answer, not a preamble. Never open with "Great question".
- Use the figures from <store_data> exactly as given. Never estimate or invent a number.
- For anything about policy, sizing, shipping or products, use <store_knowledge> and
  cite it with a bracketed number like [1] matching the numbers in that block.
- If the context does not answer the question, say so plainly and say what you would
  need. Do not guess.
- No bullet lists unless they asked for a list. No headings. No sign-off.
"""


def build_snapshot(session: Session) -> str:
    """
    A compact picture of how the store is doing right now.

    Kept deliberately terse — this goes in front of every question, and the
    small models this runs on lose the thread if you hand them a wall of text.
    """
    week = metrics.summary(session, 7)
    month = metrics.summary(session, 30)
    top = metrics.top_products(session, 30, limit=5)
    low = metrics.low_stock(session)

    sold_out = [row for row in low if row["inventory"] == 0]
    running_out = [
        row for row in low
        if row["inventory"] > 0 and row["days_of_stock"] is not None and row["days_of_stock"] <= 14
    ]

    lines = [
        "LAST 7 DAYS",
        f"revenue £{week['revenue']:,.0f} ({_change(week['revenue_change'])}), "
        f"{week['orders']} orders, AOV £{week['aov']:.2f}, {week['units']} units",
        "",
        "LAST 30 DAYS",
        f"revenue £{month['revenue']:,.0f} ({_change(month['revenue_change'])}), "
        f"{month['orders']} orders, AOV £{month['aov']:.2f}, {month['units']} units, "
        f"repeat rate {month['repeat_rate']}%",
        "",
        "TOP PRODUCTS (30 days, by revenue)",
    ]
    lines += [f"- {p['title']}: £{p['revenue']:,.0f} from {p['units']} units" for p in top]

    lines += ["", "SOLD OUT"]
    lines += (
        [f"- {r['product']} size {r['size']} (sold {r['units_last_30d']} in the last 30 days)"
         for r in sold_out]
        or ["- nothing"]
    )

    lines += ["", "RUNNING OUT"]
    lines += (
        [f"- {r['product']} size {r['size']}: {r['inventory']} left, "
         f"about {r['days_of_stock']:.0f} days of stock" for r in running_out]
        or ["- nothing"]
    )

    return "\n".join(lines)


def _change(value: float | None) -> str:
    if value is None:
        return "no comparison"
    return f"{value:+.1f}% vs the period before"


async def build_messages(session: Session, question: str, history: list[dict]) -> tuple[list[dict], list[dict]]:
    """Assemble what the model sees. Returns (messages, sources)."""
    snapshot = build_snapshot(session)

    try:
        hits = await rag.retrieve(session, question, k=4)
    except Exception:
        # Retrieval failing shouldn't take the whole answer down — the numbers
        # are still useful on their own.
        hits = []

    sources = [
        {"n": i + 1, "title": hit["title"], "source": hit["source"], "score": hit["score"]}
        for i, hit in enumerate(hits)
    ]

    knowledge = "\n\n".join(
        f"[{i + 1}] {hit['title']}\n{hit['text']}" for i, hit in enumerate(hits)
    ) or "nothing relevant found"

    # The context goes in the user turn, wrapped in tags, rather than in a
    # second system message. Small models treat a lone system message as
    # instructions and a second one as something to read out — the first
    # version of this had a 1B model answering by reciting the headings back.
    user_content = (
        "<store_data>\n"
        f"{snapshot}\n"
        "</store_data>\n\n"
        "<store_knowledge>\n"
        f"{knowledge}\n"
        "</store_knowledge>\n\n"
        f"Question: {question}"
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(store=settings.store_name)}]
    # Only the last few turns — enough to follow a "what about last month?"
    # without slowly filling the context window.
    messages += history[-6:]
    messages.append({"role": "user", "content": user_content})

    return messages, sources


def sse(event: dict) -> str:
    """One server-sent event."""
    return f"data: {json.dumps(event)}\n\n"


async def stream_reply(session: Session, question: str, history: list[dict]) -> AsyncIterator[str]:
    """
    Stream an answer as server-sent events.

    Sources go out first so the panel can render the citation list while the
    text is still arriving. Errors are sent as an event rather than thrown,
    because once the response has started streaming an HTTP error code can no
    longer reach the browser.
    """
    try:
        messages, sources = await build_messages(session, question, history)
    except Exception as exc:
        yield sse({"type": "error", "message": f"Could not gather context: {exc}"})
        yield "data: [DONE]\n\n"
        return

    yield sse({"type": "sources", "sources": sources})

    got_anything = False
    try:
        async for piece in llm.stream(messages, label="copilot"):
            got_anything = True
            yield sse({"type": "token", "text": piece})

    except LLMUnavailable:
        yield sse(
            {
                "type": "error",
                "message": (
                    "No model is responding. Start Ollama with `ollama serve`, "
                    "or set LLM_BASE_URL and LLM_API_KEY to a provider."
                ),
            }
        )
    except LLMError as exc:
        # Half an answer plus an explanation beats silently truncating.
        message = str(exc) if got_anything else f"The model failed: {exc}"
        yield sse({"type": "error", "message": message})

    yield "data: [DONE]\n\n"
