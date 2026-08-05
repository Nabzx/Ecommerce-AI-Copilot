"""
Copy in noszn's voice.

Product descriptions and win-back emails, streamed into the UI the same way
the copilot is.

The tone brief is the whole feature. Ask any model to "write product copy" and
it produces elevated marketing language — "elevate your wardrobe", "effortless
essential" — which is exactly what noszn does not sound like. So the prompt
spends most of its length on what not to do, with the banned words named
explicitly, because telling a model to "be minimal" does not survive contact
with its training data.
"""

from datetime import datetime, timedelta
from typing import AsyncIterator

from sqlmodel import Session, func, select

from app.llm import llm
from app.models import Order, Product, Variant

# noszn writes lowercase, short, and lets the garment speak. Most of this is
# aimed at stopping the model reaching for stock fashion-marketing phrasing.
# Warm enough not to write the same sentence every time, cool enough that it
# stops paraphrasing product names. At 0.7 the Boxy Tee came back as the
# "boxed tee", which is worse than dull copy — it is a dead link.
COPY_TEMPERATURE = 0.4

TONE = """You write for noszn, a small independent clothing brand.

The voice is minimal and understated:
- lowercase, except for proper nouns and sizes
- short lines, plain words, no adjectives stacked on adjectives
- say what the thing is and what it is made of, then stop
- confident, never excited. no exclamation marks

Never use these words or anything like them: elevate, effortless, essential,
curated, timeless, staple, must-have, iconic, unlock, luxurious, premium,
game-changer, wardrobe staple, level up.

Do not open with a question. Do not add a headline unless asked. Do not
explain what you have written afterwards.

Copy product names exactly as they are given to you, character for character.
Do not reword or "correct" them — they are the real names of real products,
and a customer clicking through to something called by the wrong name is worse
than no email at all."""


def product_brief(session: Session, product: Product) -> str:
    """The facts the copy has to be built from."""
    variants = session.exec(select(Variant).where(Variant.product_id == product.id)).all()
    in_stock = [v.title for v in variants if v.inventory_quantity > 0]

    return (
        f"Product: {product.title}\n"
        f"Type: {product.product_type}\n"
        f"Price: £{product.price:.2f}\n"
        f"Tags: {product.tags.replace(',', ', ')}\n"
        f"Sizes available: {', '.join(in_stock) if in_stock else 'none right now'}"
    )


async def stream_description(session: Session, product: Product) -> AsyncIterator[str]:
    """Two or three lines for a product page."""
    messages = [
        {"role": "system", "content": TONE},
        {
            "role": "user",
            "content": (
                f"{product_brief(session, product)}\n\n"
                "Write the product description. Two or three short lines, about "
                "40 words. No headline, no bullet points."
            ),
        },
    ]
    async for piece in llm.stream(messages, temperature=COPY_TEMPERATURE):
        yield piece


async def stream_winback(session: Session, days_since: int = 60) -> AsyncIterator[str]:
    """
    A short email to customers who have not been back.

    The real numbers go into the brief so the email can mention what is
    actually in stock rather than inventing a reason to write.
    """
    cutoff = datetime.now() - timedelta(days=days_since)

    # Customers whose most recent order is older than the cutoff.
    lapsed = session.exec(
        select(Order.customer_id)
        .group_by(Order.customer_id)
        .having(func.max(Order.created_at) < cutoff)
    ).all()

    stocked = []
    for product in session.exec(select(Product).order_by(Product.title)).all():
        variants = session.exec(select(Variant).where(Variant.product_id == product.id)).all()
        if sum(v.inventory_quantity for v in variants) > 20:
            stocked.append(f"{product.title} (£{product.price:.0f})")

    messages = [
        {"role": "system", "content": TONE},
        {
            "role": "user",
            "content": (
                f"{len(lapsed)} customers last ordered more than {days_since} days ago.\n"
                f"In stock and worth mentioning: {', '.join(stocked[:5])}\n\n"
                "Write a short win-back email to them. Subject line on the first "
                "line, then the body. Under 80 words. No discount code, we are not "
                "offering one. Sign off as noszn."
            ),
        },
    ]
    async for piece in llm.stream(messages, temperature=COPY_TEMPERATURE):
        yield piece

