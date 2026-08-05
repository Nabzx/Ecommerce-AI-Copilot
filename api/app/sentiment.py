"""
Review sentiment and the themes underneath it.

Knowing 27% of reviews are negative isn't much use on its own. What the owner
can act on is *what* they're negative about — and in noszn's case the answer
is sizing, which is fixable with a better size chart rather than a better
product.

Two decisions worth knowing about.

Themes come from a closed list rather than free text. Left to invent its own,
the model returns "sizing" for one review, "size" for the next and "fit
issues" for a third, and the counts end up meaningless. A fixed vocabulary is
what makes them add up.

Results are written back to the review row. Classification is the slow part,
so it runs once and the dashboard reads the stored answer.
"""

import json
from collections import Counter

from sqlmodel import Session, func, select

from app.llm import llm
from app.models import Product, Review

# The closed set. "other" is there so the model has somewhere to put things
# rather than bending them into a theme that doesn't fit.
THEMES = [
    "sizing",
    "fabric quality",
    "shipping speed",
    "stock availability",
    "colour",
    "price",
    "returns",
    "customer service",
    "other",
]

BATCH_SIZE = 15

PROMPT = """Classify each customer review.

For every review return its number, a sentiment, and the single theme it is most about.

sentiment: positive, neutral, or negative
theme: one of {themes}

Reply with a JSON array and nothing else, like:
[{{"n": 1, "sentiment": "negative", "theme": "sizing"}}, {{"n": 2, "sentiment": "positive", "theme": "fabric quality"}}]

Reviews:
{reviews}
"""


def extract_array(text: str) -> list[dict]:
    """Pull the JSON array out of the reply, fence or no fence."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array in the reply")
    return json.loads(text[start : end + 1])


async def classify_texts(texts: list[str]) -> dict[str, tuple[str, str]]:
    """
    Label a batch of review texts. Returns {text: (sentiment, theme)}.

    Anything the model returns that isn't in the allowed vocabulary is dropped
    rather than stored — a made-up theme would quietly corrupt the counts, and
    a dropped one just means that review gets picked up on the next run.
    """
    numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(texts))
    prompt = PROMPT.format(themes=", ".join(THEMES), reviews=numbered)

    # Far slower than a chat reply, and timing it out at 60s would throw away
    # work that was going to finish.
    reply = await llm.complete(
        [{"role": "user", "content": prompt}], temperature=0.0, timeout=300.0
    )
    rows = extract_array(reply)

    labelled: dict[str, tuple[str, str]] = {}
    for row in rows:
        try:
            index = int(row["n"]) - 1
            sentiment = str(row["sentiment"]).strip().lower()
            theme = str(row["theme"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue

        if not 0 <= index < len(texts):
            continue
        if sentiment not in {"positive", "neutral", "negative"} or theme not in THEMES:
            continue

        labelled[texts[index]] = (sentiment, theme)

    return labelled


async def analyse(session: Session, limit: int | None = None) -> dict:
    """
    Classify whatever hasn't been classified yet.

    Identical review texts are only sent once. Customers say the same handful
    of things — "runs small", "arrived quickly" — so across 140 reviews there
    are about 23 distinct sentences, and classifying each one six times is six
    times the wait for exactly the same answer. Labels are then applied to
    every review sharing that text.
    """
    query = select(Review).where(Review.sentiment.is_(None))
    if limit:
        query = query.limit(limit)
    pending = list(session.exec(query).all())

    if not pending:
        return {"classified": 0, "remaining": 0, "unique_texts": 0}

    # text -> the reviews that say exactly that
    by_text: dict[str, list[Review]] = {}
    for review in pending:
        by_text.setdefault(review.body.strip(), []).append(review)

    unique = list(by_text)
    done = 0

    for start in range(0, len(unique), BATCH_SIZE):
        batch = unique[start : start + BATCH_SIZE]
        labelled = await classify_texts(batch)

        for text, (sentiment_label, theme) in labelled.items():
            for review in by_text[text]:
                review.sentiment = sentiment_label
                review.theme = theme
                session.add(review)
                done += 1
        session.commit()

    remaining = session.exec(
        select(func.count(Review.id)).where(Review.sentiment.is_(None))
    ).one()

    return {"classified": done, "remaining": int(remaining), "unique_texts": len(unique)}


def insights(session: Session) -> dict:
    """The split, the themes behind it, and a few reviews to read."""
    reviews = session.exec(select(Review).where(Review.sentiment.is_not(None))).all()
    total = session.exec(select(func.count(Review.id))).one()

    if not reviews:
        return {
            "analysed": 0,
            "total": int(total),
            "counts": {},
            "positive_themes": [],
            "negative_themes": [],
            "examples": [],
        }

    counts = Counter(review.sentiment for review in reviews)
    positive = Counter(r.theme for r in reviews if r.sentiment == "positive" and r.theme)
    negative = Counter(r.theme for r in reviews if r.sentiment == "negative" and r.theme)

    titles = {
        product.id: product.title for product in session.exec(select(Product)).all()
    }

    # A couple of real negative reviews, because a theme name on its own
    # doesn't tell the owner how it actually sounds to a customer.
    examples = [
        {
            "body": review.body,
            "theme": review.theme,
            "rating": review.rating,
            "product": titles.get(review.product_id, ""),
        }
        for review in reviews
        if review.sentiment == "negative"
    ][:3]

    return {
        "analysed": len(reviews),
        "total": int(total),
        "counts": dict(counts),
        "positive_themes": [{"theme": t, "count": c} for t, c in positive.most_common(4)],
        "negative_themes": [{"theme": t, "count": c} for t, c in negative.most_common(4)],
        "examples": examples,
    }
