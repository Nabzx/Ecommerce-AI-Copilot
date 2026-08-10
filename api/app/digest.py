"""
The Monday morning digest.

Everything else here waits for someone to open a browser. This is the one
piece that goes the other way, and that's the whole point — a dashboard you
have to remember to look at gets looked at twice and then forgotten.

Nothing new is computed. It pulls the same numbers the cards show, picks the
few worth waking up to, and asks the model to write a couple of lines over the
top. If no model is reachable the figures go out on their own, because a
digest that fails because an LLM was down would be a silly way to lose the
habit.

    python -m app.digest            # print it
    python -m app.digest --send     # email it, if SMTP is configured
"""

import smtplib
from datetime import datetime
from email.message import EmailMessage

from sqlmodel import Session, select

from app import alerts, forecast, metrics, sentiment
from app.config import settings
from app.llm import LLMError, llm
from app.models import Review

SUMMARY_PROMPT = """You write the opening line of a weekly email to the owner of {store}, a small clothing brand.

This week's figures:
{figures}

Write two sentences, no more. Say how the week went and name the one thing worth
doing something about. Lowercase, plain, no marketing language, no greeting, no
sign-off. Do not repeat every number back — pick what matters.
"""


def gather(session: Session) -> dict:
    """The facts the digest is built from."""
    week = metrics.summary(session, 7)
    month = metrics.summary(session, 30)
    top = metrics.top_products(session, 7, limit=3)

    # Sizes worth acting on this week, not the whole low-stock list.
    try:
        running_out = [
            row
            for row in forecast.stockout_report(session, limit=40)
            if row["days_to_stockout"] is not None and row["days_to_stockout"] <= 14
        ][:5]
    except ValueError:
        # Not enough history to forecast — a fresh store, say nothing.
        running_out = []

    sold_out = [row for row in metrics.low_stock(session) if row["inventory"] == 0]

    triggered = [rule for rule in alerts.check_all(session) if rule["triggered"]]

    # Only mention reviews if there are any; a synced store has none.
    has_reviews = session.exec(select(Review).limit(1)).first() is not None
    insights = sentiment.insights(session) if has_reviews else None
    top_complaint = (
        insights["negative_themes"][0]
        if insights and insights["negative_themes"]
        else None
    )

    return {
        "week": week,
        "month": month,
        "top": top,
        "running_out": running_out,
        "sold_out": sold_out,
        "alerts": triggered,
        "top_complaint": top_complaint,
    }


def figures_block(facts: dict) -> str:
    """The numbers, as plain lines. Used in the email and in the prompt."""
    week = facts["week"]
    lines = [
        f"revenue £{week['revenue']:,.0f} ({_change(week['revenue_change'])})",
        f"{week['orders']} orders, AOV £{week['aov']:.2f}, {week['units']} units",
        f"repeat rate {facts['month']['repeat_rate']}% over 30 days",
    ]

    if facts["top"]:
        best = facts["top"][0]
        lines.append(f"best seller: {best['title']}, £{best['revenue']:,.0f}")

    if facts["sold_out"]:
        names = ", ".join(f"{r['product']} {r['size']}" for r in facts["sold_out"][:4])
        lines.append(f"sold out: {names}")

    if facts["running_out"]:
        soon = ", ".join(
            f"{r['product']} {r['size']} ({r['days_to_stockout']}d)"
            for r in facts["running_out"][:4]
        )
        lines.append(f"running out: {soon}")

    if facts["top_complaint"]:
        theme = facts["top_complaint"]
        lines.append(f"most common complaint: {theme['theme']} ({theme['count']} reviews)")

    return "\n".join(lines)


def _change(value: float | None) -> str:
    return "no comparison" if value is None else f"{value:+.1f}% on the week before"


async def write_summary(store: str, figures: str) -> str:
    """
    Two lines over the top, in the shop's voice.

    Best effort on purpose. If the model is down the digest still goes out —
    the numbers are the point, the sentence is the nice part.
    """
    try:
        return (
            await llm.complete(
                [{"role": "user", "content": SUMMARY_PROMPT.format(store=store, figures=figures)}],
                temperature=0.4,
                timeout=90.0,
            )
        ).strip()
    except (LLMError, Exception):
        return ""


async def build(session: Session) -> dict:
    """The whole digest: a summary, the figures, and what to do."""
    facts = gather(session)
    figures = figures_block(facts)
    summary = await write_summary(settings.store_name, figures)

    # The bit he can act on, kept separate from the reporting.
    actions: list[str] = []
    for row in facts["running_out"][:3]:
        actions.append(
            f"Reorder {row['product']} {row['size']} — {row['inventory']} left, "
            f"about {row['days_to_stockout']} days"
        )
    for rule in facts["alerts"][:3]:
        actions.append(f"Alert: {rule['phrase']} ({rule['count']} matching)")
    if facts["top_complaint"] and facts["top_complaint"]["count"] >= 3:
        actions.append(
            f"{facts['top_complaint']['count']} reviews mention "
            f"{facts['top_complaint']['theme']}"
        )

    return {
        "store": settings.store_name,
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "figures": figures,
        "actions": actions,
        "sold_out": len(facts["sold_out"]),
        "week": facts["week"],
    }


def as_text(digest: dict) -> str:
    """Plain text, because a small brand's owner reads this on a phone."""
    parts = [f"{digest['store']} — last 7 days", ""]

    if digest["summary"]:
        parts += [digest["summary"], ""]

    parts += [digest["figures"]]

    if digest["actions"]:
        parts += ["", "worth doing:"]
        parts += [f"- {action}" for action in digest["actions"]]

    parts += ["", "— StoreSense"]
    return "\n".join(parts)


def send_email(digest: dict) -> str:
    """Send it, if there's somewhere to send it to."""
    if not (settings.smtp_host and settings.digest_to):
        raise ValueError(
            "Email isn't configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD "
            "and DIGEST_TO, or just read it on the dashboard."
        )

    message = EmailMessage()
    message["Subject"] = f"{digest['store']} — last week"
    message["From"] = settings.digest_from or settings.smtp_user
    message["To"] = settings.digest_to
    message.set_content(as_text(digest))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)

    return settings.digest_to


if __name__ == "__main__":
    import asyncio
    import sys

    from app.db import engine

    with Session(engine) as db:
        result = asyncio.run(build(db))

    print(as_text(result))

    if "--send" in sys.argv:
        try:
            to = send_email(result)
        except (ValueError, OSError, smtplib.SMTPException) as exc:
            print(f"\nnot sent: {exc}")
            raise SystemExit(1) from None
        print(f"\nsent to {to}")
