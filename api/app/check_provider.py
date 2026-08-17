"""
Confirm the gateway works against whatever provider it's pointed at.

The gateway claims to be provider-agnostic. This is how you check that's true
rather than assumed — point it at OpenAI, Together, Groq, vLLM or a local
Ollama and run:

    python -m app.check_provider

It exercises the three things the app actually does — a completion, a stream
and an embedding — and reports the tokens and cost each came back with, so it
doubles as a check that the usage accounting is wired up.

Nothing here writes to the database. It's a read-only smoke test, safe to run
against a paid provider without wondering what it left behind.
"""

import asyncio

from app import pricing
from app.config import settings
from app.llm import LLMClient, LLMError


async def main() -> int:
    client = LLMClient()

    # Collected in memory rather than recorded — this deliberately doesn't
    # touch the database.
    seen: list[dict] = []
    client.on_usage = lambda **kwargs: seen.append(kwargs)

    print(f"provider : {settings.llm_base_url}")
    print(f"model    : {settings.llm_model}")
    print(f"embedder : {settings.llm_embed_model}\n")

    if not await client.available():
        print("FAIL  nothing answered at that URL - check LLM_BASE_URL and the key")
        return 1

    question = [{"role": "user", "content": "Reply with exactly: ready"}]

    try:
        reply = await client.complete(question, label="check.complete", temperature=0)
        print(f"ok    completion  {reply.strip()[:60]!r}")

        pieces = [p async for p in client.stream(question, label="check.stream", temperature=0)]
        print(f"ok    streaming   {''.join(pieces).strip()[:60]!r}")

    except LLMError as exc:
        print(f"\nFAIL  {exc}")
        return 1

    # Separate, because a chat-only provider is a normal thing to point at —
    # a fine-tuned adapter serves completions and nothing else, and the app
    # can take its embeddings from somewhere else entirely.
    try:
        vectors = await client.embed(["a test sentence"], label="check.embed")
        print(f"ok    embeddings  {len(vectors[0])} dimensions")
    except LLMError:
        print("note  no embeddings here - chat only, which is fine")

    # --- what it cost ---
    print()
    if not seen:
        print("note  no usage came back - this provider doesn't report token counts")
        return 0

    total = 0.0
    for call in seen:
        cost = pricing.cost_gbp(call["model"], call["prompt_tokens"], call["completion_tokens"])
        total += cost
        tokens = call["prompt_tokens"] + call["completion_tokens"]
        print(f"  {call['endpoint']:16} {tokens:>6} tokens  GBP {cost:.6f}")

    print(f"  {'total':16} {'':>6}         GBP {total:.6f}")

    if total == 0 and not pricing.is_local(settings.llm_model):
        print(
            f"\nnote  {settings.llm_model} isn't in the price list, so cost reads as zero.\n"
            f"      Add it to pricing.py for real figures."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
