"""
What a request to a model actually costs.

Providers bill per million tokens and quote in dollars. These are in pounds so
the dashboard can show one currency alongside the revenue figures, converted
at a rate that's a setting rather than a hardcoded guess.

Local models cost nothing to call, which is the point of running one — but
they still get counted, because "we used 400k tokens this week" is worth
knowing even when the bill is zero. It's what tells you what the bill *would*
be on a paid provider.
"""

from app.config import settings

# £ per million tokens, (input, output).
#
# Rough, and deliberately easy to correct — providers change these and nobody
# updates their code. Anything not listed falls back to UNKNOWN_PRICE below.
PRICE_PER_MILLION: dict[str, tuple[float, float]] = {
    # OpenAI, converted from USD at roughly 0.79.
    "gpt-4o": (2.00, 7.90),
    "gpt-4o-mini": (0.12, 0.47),
    "gpt-4.1": (1.58, 6.32),
    "gpt-4.1-mini": (0.32, 1.26),
    "o4-mini": (0.87, 3.48),
    "text-embedding-3-small": (0.016, 0.0),
    "text-embedding-3-large": (0.103, 0.0),
    # Anthropic.
    "claude-sonnet-4": (2.37, 11.85),
    "claude-haiku-4": (0.63, 3.16),
}

# Anything running on localhost is free. Matched loosely because the model name
# is whatever the user typed — llama3.1, llama3.1:latest, mistral, moondream.
LOCAL_HINTS = ("llama", "mistral", "phi", "qwen", "gemma", "moondream", "nomic", "whisper")


def is_local(model: str) -> bool:
    name = (model or "").lower()
    return any(hint in name for hint in LOCAL_HINTS)


def lookup(model: str) -> tuple[float, float] | None:
    """Prices for a model, or None if we don't know it."""
    name = (model or "").lower()
    if name in PRICE_PER_MILLION:
        return PRICE_PER_MILLION[name]

    # "gpt-4o-mini-2024-07-18" should price as "gpt-4o-mini", not "gpt-4o" —
    # so take the longest prefix that matches, not the first one found. The
    # short one is 16x the price of the long one, and picking it would inflate
    # every reported cost without anything looking wrong.
    matches = [known for known in PRICE_PER_MILLION if name.startswith(known)]
    if matches:
        return PRICE_PER_MILLION[max(matches, key=len)]

    return None


def cost_gbp(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    What this call cost, in pounds.

    Returns 0.0 for a local model, which is true. Returns 0.0 for an unknown
    paid model too, which isn't — but guessing a price would be worse than
    showing nothing, and `priced` on the usage row records which it was so the
    dashboard never implies a total is complete when it isn't.
    """
    if is_local(model):
        return 0.0

    price = lookup(model)
    if price is None:
        return 0.0

    input_price, output_price = price
    pounds = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    return round(pounds * settings.currency_multiplier, 6)


def known_price(model: str) -> bool:
    """Can we put a real number on this call?"""
    return is_local(model) or lookup(model) is not None
