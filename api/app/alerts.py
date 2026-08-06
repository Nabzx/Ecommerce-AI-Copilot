"""
Alerts the owner writes in plain English.

They type "tell me if any product drops below 5 units" and the model turns it
into a small structured rule that the dashboard evaluates itself. The LLM is
only involved at the moment the rule is written — after that it's ordinary
code, so the alerts are cheap to check, they behave the same way every time,
and they keep working when there's no model running.

The rule shape is deliberately narrow. A tight schema is what makes it
possible to reject a bad parse instead of storing something that half works.
"""

import json
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from app import metrics
from app.llm import llm
from app.models import Alert, DailySales, Product, Variant


class AlertRule(BaseModel):
    """The only shapes an alert is allowed to take."""

    metric: Literal[
        "inventory",  # units left of a size
        "days_of_stock",  # how long that stock lasts at the current rate
        "units_7d",  # units sold in the last week
        "revenue_7d",  # whole store, last week
        "aov",  # whole store, last 30 days
        "repeat_rate",  # whole store, last 30 days
    ]
    comparator: Literal["lt", "lte", "gt", "gte"]
    threshold: float
    # Whether the rule is about one size at a time or the whole shop.
    scope: Literal["variant", "store"]
    # Optional filter, e.g. only hoodies. Matched against the product title.
    product_contains: str | None = Field(default=None)


STORE_METRICS = {"revenue_7d", "aov", "repeat_rate"}

PARSE_PROMPT = """Turn the shop owner's sentence into a JSON rule.

Reply with the JSON object and nothing else. No explanation, no markdown fence.

Fields:
  metric: one of inventory, days_of_stock, units_7d, revenue_7d, aov, repeat_rate
  comparator: one of lt, lte, gt, gte
  threshold: a number
  scope: "variant" for rules about a single size, "store" for whole-shop rules
  product_contains: part of a product name to limit the rule to, or null

Use scope "store" only for revenue_7d, aov and repeat_rate. Everything else is "variant".

Examples:

"tell me if any product drops below 5 units"
{"metric":"inventory","comparator":"lt","threshold":5,"scope":"variant","product_contains":null}

"warn me when a hoodie has less than two weeks of stock left"
{"metric":"days_of_stock","comparator":"lt","threshold":14,"scope":"variant","product_contains":"hoodie"}

"let me know if weekly revenue falls under 5000"
{"metric":"revenue_7d","comparator":"lt","threshold":5000,"scope":"store","product_contains":null}

"flag anything selling more than 30 a week"
{"metric":"units_7d","comparator":"gt","threshold":30,"scope":"variant","product_contains":null}

Sentence: {phrase}
"""


def extract_json(text: str) -> dict:
    """
    Pull the JSON object out of whatever the model said.

    Small models like to wrap the answer in a code fence or add "Here you go"
    in front, so take the outermost braces rather than trusting the whole
    reply to parse.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start : end + 1])


async def parse_rule(phrase: str) -> AlertRule:
    """
    Ask the model for a rule, and insist it's a valid one.

    One retry, with the validation error handed back so it can correct itself.
    If it still can't produce something matching the schema we raise rather
    than store a rule that only half works.
    """
    messages = [{"role": "user", "content": PARSE_PROMPT.replace("{phrase}", phrase)}]
    last_error = ""

    for _ in range(2):
        # An LLMError means no model, not a bad rule — let it through untouched
        # so the caller can say "start Ollama" rather than "I didn't understand".
        reply = await llm.complete(messages, temperature=0.0)

        try:
            return AlertRule(**extract_json(reply))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)[:200]

        # Show it what it said and what was wrong with it.
        messages.append({"role": "assistant", "content": reply})
        messages.append(
            {
                "role": "user",
                "content": f"That was not valid: {last_error}. Reply with only the JSON object.",
            }
        )

    # The validation error is right but unreadable — it's a Pydantic dump, and
    # the owner asked a question, not for a schema. Say what it can do instead.
    raise ValueError(
        "I couldn't turn that into a rule. Try something like "
        "“tell me if any product drops below 5 units” or "
        "“warn me when weekly revenue falls under 5000”."
    )


def compare(value: float, comparator: str, threshold: float) -> bool:
    return {
        "lt": value < threshold,
        "lte": value <= threshold,
        "gt": value > threshold,
        "gte": value >= threshold,
    }[comparator]


def evaluate(session: Session, rule: AlertRule) -> list[dict]:
    """Run one rule and return whatever it caught."""
    if rule.metric in STORE_METRICS:
        return _evaluate_store(session, rule)
    return _evaluate_variants(session, rule)


def _evaluate_store(session: Session, rule: AlertRule) -> list[dict]:
    summary = metrics.summary(session, 7 if rule.metric == "revenue_7d" else 30)
    value = {
        "revenue_7d": summary["revenue"],
        "aov": summary["aov"],
        "repeat_rate": summary["repeat_rate"],
    }[rule.metric]

    if not compare(value, rule.comparator, rule.threshold):
        return []
    return [{"label": rule.metric.replace("_", " "), "value": round(value, 2)}]


def _evaluate_variants(session: Session, rule: AlertRule) -> list[dict]:
    since = datetime.now().date() - timedelta(days=7)

    rows = session.exec(
        select(Variant, Product).join(Product, Product.id == Variant.product_id)
    ).all()

    hits = []
    for variant, product in rows:
        if rule.product_contains and rule.product_contains.lower() not in product.title.lower():
            continue

        units_7d = sum(
            row
            for row in session.exec(
                select(DailySales.units).where(
                    DailySales.variant_id == variant.id, DailySales.day >= since
                )
            ).all()
        )

        if rule.metric == "inventory":
            value = float(variant.inventory_quantity)
        elif rule.metric == "units_7d":
            value = float(units_7d)
        else:  # days_of_stock
            rate = units_7d / 7
            # Nothing selling never runs out, so it can't trip a "less than"
            # rule — treating it as zero days would flag the whole dead stock
            # shelf every time.
            if rate <= 0:
                continue
            value = variant.inventory_quantity / rate

        if compare(value, rule.comparator, rule.threshold):
            hits.append(
                {
                    "label": f"{product.title} · {variant.title}",
                    "value": round(value, 1),
                    "variant_id": variant.id,
                    "product_id": product.id,
                }
            )

    # Worst first for "less than" rules, biggest first for "more than".
    hits.sort(key=lambda h: h["value"], reverse=rule.comparator in ("gt", "gte"))
    return hits


def describe(rule: AlertRule) -> str:
    """The rule in words, so the owner can see it was understood correctly."""
    words = {"lt": "below", "lte": "at or below", "gt": "above", "gte": "at or above"}
    metric_words = {
        "inventory": "units left",
        "days_of_stock": "days of stock",
        "units_7d": "units sold in 7 days",
        "revenue_7d": "revenue in 7 days",
        "aov": "average order value",
        "repeat_rate": "repeat rate",
    }
    threshold = int(rule.threshold) if rule.threshold == int(rule.threshold) else rule.threshold
    text = f"{metric_words[rule.metric]} {words[rule.comparator]} {threshold}"
    if rule.product_contains:
        text += f", for products matching “{rule.product_contains}”"
    return text


def load_rule(alert: Alert) -> AlertRule:
    return AlertRule(**json.loads(alert.rule))


def check_all(session: Session) -> list[dict]:
    """Every active alert, with whatever it's currently catching."""
    alerts = session.exec(select(Alert).where(Alert.active).order_by(Alert.created_at)).all()

    results = []
    for alert in alerts:
        rule = load_rule(alert)
        hits = evaluate(session, rule)
        results.append(
            {
                "id": alert.id,
                "phrase": alert.phrase,
                "rule": rule.model_dump(),
                "reads_as": describe(rule),
                "triggered": len(hits) > 0,
                "count": len(hits),
                # A long list would swamp the panel; the count carries the rest.
                "hits": hits[:6],
            }
        )
    return results
