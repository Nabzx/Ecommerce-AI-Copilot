"""
All the dashboard numbers.

Plain SQL aggregations, nothing clever. Each function takes a session and a
window in days and returns something the frontend can render directly.

Every headline number comes back with the equivalent figure for the previous
window of the same length, so the dashboard can show "vs last 30 days" without
doing any maths of its own.
"""

from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.config import settings
from app.models import Customer, DailySales, Order, OrderLine, Product, Variant


def _window(days: int):
    """Return (start, end) for the current window and the one before it."""
    end = datetime.now()
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    return start, end, previous_start


def _percent_change(current: float, previous: float) -> float | None:
    """Percent change, or None when there's no previous figure to compare to."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _totals(session: Session, start: datetime, end: datetime) -> dict:
    """Revenue, order count and units sold between two dates."""
    revenue, orders = session.exec(
        select(func.coalesce(func.sum(Order.total_price), 0.0), func.count(Order.id))
        .where(Order.created_at >= start, Order.created_at < end)
    ).one()

    units = session.exec(
        select(func.coalesce(func.sum(OrderLine.quantity), 0))
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.created_at >= start, Order.created_at < end)
    ).one()

    return {"revenue": float(revenue), "orders": int(orders), "units": int(units)}


def repeat_purchase_rate(session: Session, start: datetime, end: datetime) -> float:
    """
    Of the customers who ordered in this window, what share are repeat buyers?

    "Repeat buyer" means they have more than one order in their lifetime, not
    just within the window — someone who bought in January and again today is
    a repeat customer, and counting only the window would miss that.
    """
    customer_ids = session.exec(
        select(Order.customer_id)
        .where(Order.created_at >= start, Order.created_at < end)
        .distinct()
    ).all()

    if not customer_ids:
        return 0.0

    repeat = session.exec(
        select(func.count())
        .select_from(
            select(Order.customer_id)
            .where(Order.customer_id.in_(customer_ids))
            .group_by(Order.customer_id)
            .having(func.count(Order.id) > 1)
            .subquery()
        )
    ).one()

    return round(repeat / len(customer_ids) * 100, 1)


def summary(session: Session, days: int = 30) -> dict:
    """The headline cards at the top of the dashboard."""
    start, end, previous_start = _window(days)

    current = _totals(session, start, end)
    previous = _totals(session, previous_start, start)

    aov = current["revenue"] / current["orders"] if current["orders"] else 0.0
    previous_aov = previous["revenue"] / previous["orders"] if previous["orders"] else 0.0

    return {
        "window_days": days,
        "revenue": round(current["revenue"], 2),
        "revenue_change": _percent_change(current["revenue"], previous["revenue"]),
        "orders": current["orders"],
        "orders_change": _percent_change(current["orders"], previous["orders"]),
        "aov": round(aov, 2),
        "aov_change": _percent_change(aov, previous_aov),
        "units": current["units"],
        "units_change": _percent_change(current["units"], previous["units"]),
        "repeat_rate": repeat_purchase_rate(session, start, end),
    }


def revenue_series(session: Session, days: int = 30) -> list[dict]:
    """Revenue per day, including days with no sales so the chart has no gaps."""
    start, end, _ = _window(days)

    rows = session.exec(
        select(func.date(Order.created_at), func.sum(Order.total_price))
        .where(Order.created_at >= start, Order.created_at < end)
        .group_by(func.date(Order.created_at))
    ).all()
    by_day = {str(day): float(total) for day, total in rows}

    series = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        series.append({"day": day, "revenue": round(by_day.get(day, 0.0), 2)})
    return series


def top_products(session: Session, days: int = 30, limit: int = 6) -> list[dict]:
    """Best sellers by revenue, with units alongside."""
    start, end, _ = _window(days)

    rows = session.exec(
        select(
            Product.id,
            Product.title,
            Product.product_type,
            func.sum(OrderLine.quantity * OrderLine.price),
            func.sum(OrderLine.quantity),
        )
        .join(OrderLine, OrderLine.product_id == Product.id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.created_at >= start, Order.created_at < end)
        .group_by(Product.id)
        .order_by(func.sum(OrderLine.quantity * OrderLine.price).desc())
        .limit(limit)
    ).all()

    return [
        {
            "product_id": pid,
            "title": title,
            "product_type": ptype,
            "revenue": round(float(revenue), 2),
            "units": int(units),
        }
        for pid, title, ptype, revenue, units in rows
    ]


def low_stock(session: Session, threshold: int | None = None) -> list[dict]:
    """
    Sizes that are out or nearly out.

    Sorted by how empty they are, and tagged with how fast they've been moving
    lately so the owner can tell "3 left and selling daily" apart from
    "3 left and nobody wants it".
    """
    threshold = threshold if threshold is not None else settings.low_stock_threshold
    recent_start = datetime.now().date() - timedelta(days=30)

    rows = session.exec(
        select(Variant, Product)
        .join(Product, Product.id == Variant.product_id)
        .where(Variant.inventory_quantity <= threshold, Product.status == "active")
        .order_by(Variant.inventory_quantity)
    ).all()

    out = []
    for variant, product in rows:
        sold = session.exec(
            select(func.coalesce(func.sum(DailySales.units), 0))
            .where(DailySales.variant_id == variant.id, DailySales.day >= recent_start)
        ).one()
        per_day = float(sold) / 30

        out.append(
            {
                "variant_id": variant.id,
                "product_id": product.id,
                "product": product.title,
                "size": variant.title,
                "sku": variant.sku,
                "inventory": variant.inventory_quantity,
                "units_last_30d": int(sold),
                # None means it isn't selling, so it'll never run out.
                "days_of_stock": round(variant.inventory_quantity / per_day, 1) if per_day else None,
            }
        )
    return out


def customer_stats(session: Session, days: int = 30) -> dict:
    """New vs returning split, for the customers card."""
    start, end, _ = _window(days)

    new_customers = session.exec(
        select(func.count(Customer.id))
        .where(Customer.created_at >= start, Customer.created_at < end)
    ).one()

    active = session.exec(
        select(func.count(func.distinct(Order.customer_id)))
        .where(Order.created_at >= start, Order.created_at < end)
    ).one()

    return {
        "new_customers": int(new_customers),
        "active_customers": int(active),
        "returning_customers": max(0, int(active) - int(new_customers)),
    }
