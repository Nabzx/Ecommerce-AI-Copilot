"""
Recording what the models cost.

The gateway doesn't touch the database — it hands a finished call to a hook,
and this is what's plugged into it. That keeps `llm.py` usable from the
seeder, the CLI scripts and the tests without dragging a session along.

Recording is best effort. A failure to write a usage row must never take down
the answer the user was actually waiting for; the accounting is the least
important thing happening in that request.
"""

from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app import pricing
from app.db import engine
from app.models import Usage


def record(
    endpoint: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    streamed: bool = False,
) -> None:
    """Save one call. Swallows its own errors on purpose."""
    try:
        with Session(engine) as session:
            session.add(
                Usage(
                    endpoint=endpoint,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    cost_gbp=pricing.cost_gbp(model, prompt_tokens, completion_tokens),
                    priced=pricing.known_price(model),
                    streamed=streamed,
                    created_at=datetime.now(),
                )
            )
            session.commit()
    except Exception:
        # Losing a cost row is not worth failing a request over.
        pass


def summary(session: Session, days: int = 30) -> dict:
    """Totals, and the breakdown by feature that makes them useful."""
    since = datetime.now() - timedelta(days=days)

    totals = session.exec(
        select(
            func.count(Usage.id),
            func.coalesce(func.sum(Usage.total_tokens), 0),
            func.coalesce(func.sum(Usage.cost_gbp), 0.0),
        ).where(Usage.created_at >= since)
    ).one()

    calls, tokens, cost = int(totals[0]), int(totals[1]), float(totals[2])

    by_endpoint = session.exec(
        select(
            Usage.endpoint,
            func.count(Usage.id),
            func.coalesce(func.sum(Usage.total_tokens), 0),
            func.coalesce(func.sum(Usage.cost_gbp), 0.0),
        )
        .where(Usage.created_at >= since)
        .group_by(Usage.endpoint)
        .order_by(func.sum(Usage.total_tokens).desc())
    ).all()

    # Calls we couldn't price, so the total can admit to being incomplete
    # rather than looking like the whole bill.
    unpriced = session.exec(
        select(func.count(Usage.id)).where(Usage.created_at >= since, Usage.priced == False)  # noqa: E712
    ).one()

    models = session.exec(
        select(Usage.model, func.count(Usage.id))
        .where(Usage.created_at >= since)
        .group_by(Usage.model)
    ).all()

    return {
        "window_days": days,
        "calls": calls,
        "tokens": tokens,
        "cost_gbp": round(cost, 4),
        "unpriced_calls": int(unpriced),
        "by_endpoint": [
            {
                "endpoint": endpoint,
                "calls": int(count),
                "tokens": int(tok),
                "cost_gbp": round(float(spend), 4),
            }
            for endpoint, count, tok, spend in by_endpoint
        ],
        "models": [{"model": model, "calls": int(count)} for model, count in models],
    }
