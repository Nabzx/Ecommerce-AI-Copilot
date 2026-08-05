"""
Product tagging from a photo.

Upload a picture of a piece and get back Shopify-style tags and a short
description, so a new drop can be listed without writing the same fields out
by hand fourteen times.

The tags are constrained to a vocabulary the store already uses. Left open,
the model returns things like "urban streetwear vibes" — true enough, but it
doesn't match anything already in the catalogue, so filtering by it finds one
product and the tag is dead weight. Anything outside the list is dropped.
"""

import json

from sqlmodel import Session, select

from app.llm import llm
from app.models import Product

PROMPT = """Look at this piece of clothing and describe it for an online shop.

Reply with JSON only, in this shape:
{{"tags": ["...", "..."], "description": "...", "product_type": "...", "colour": "..."}}

tags: 3 to 6 tags, chosen only from this list: {vocabulary}
product_type: one of {types}
colour: the main colour, one or two words
description: two short lowercase lines, under 30 words, plain and understated.
Say what it is and what it looks like. No marketing language.
"""


def vocabulary(session: Session) -> tuple[list[str], list[str]]:
    """The tags and product types the store already uses."""
    products = session.exec(select(Product)).all()

    tags: set[str] = set()
    types: set[str] = set()
    for product in products:
        types.add(product.product_type)
        tags.update(tag.strip() for tag in product.tags.split(",") if tag.strip())

    return sorted(tags), sorted(types)


def extract_object(text: str) -> dict:
    """Pull the JSON object out of the reply, fence or no fence."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start : end + 1])


async def tag_image(session: Session, image_bytes: bytes) -> dict:
    """Tags and a description for one uploaded photo."""
    tags, types = vocabulary(session)

    prompt = PROMPT.format(vocabulary=", ".join(tags), types=", ".join(types))
    reply = await llm.describe_image(image_bytes, prompt)
    data = extract_object(reply)

    # Keep only tags the store actually uses, so the result is something you
    # could filter the catalogue by rather than a nice-sounding orphan.
    allowed = set(tags)
    chosen = [t for t in map(str.lower, map(str, data.get("tags", []))) if t in allowed]

    product_type = str(data.get("product_type", "")).lower()
    if product_type not in types:
        product_type = ""

    return {
        "tags": chosen[:6],
        "product_type": product_type,
        "colour": str(data.get("colour", "")).lower()[:30],
        "description": str(data.get("description", "")).strip(),
        # Worth surfacing: if the model suggested tags the shop has never used,
        # that's either a bad guess or a gap in the tagging.
        "rejected_tags": [
            t for t in map(str.lower, map(str, data.get("tags", []))) if t not in allowed
        ][:6],
    }
