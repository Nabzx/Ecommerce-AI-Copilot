"""
Where the data in this database came from.

The seeder and the Shopify sync both write here when they finish, so the
dashboard can say "demo data" or "noszn, synced 20 minutes ago" instead of
leaving everyone to guess. It's the difference between showing your friend a
demo and showing him his own shop.
"""

from datetime import datetime

from sqlmodel import Session, delete, select

from app.models import SyncState

DEMO = "demo"
SHOPIFY = "shopify"


def record(
    session: Session,
    source: str,
    *,
    products: int = 0,
    variants: int = 0,
    orders: int = 0,
    customers: int = 0,
    history_days: int = 0,
    store_domain: str = "",
    note: str = "",
) -> SyncState:
    """Replace the single row saying what's currently loaded."""
    session.exec(delete(SyncState))

    state = SyncState(
        source=source,
        store_domain=store_domain,
        synced_at=datetime.now(),
        products=products,
        variants=variants,
        orders=orders,
        customers=customers,
        history_days=history_days,
        note=note,
    )
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def current(session: Session) -> dict:
    """What the dashboard shows in the header."""
    state = session.exec(select(SyncState)).first()

    if not state:
        # An empty database, or one seeded before this table existed.
        return {"source": "unknown", "synced_at": None, "is_demo": True}

    return {
        "source": state.source,
        "is_demo": state.source == DEMO,
        "store_domain": state.store_domain,
        "synced_at": state.synced_at.isoformat(),
        "products": state.products,
        "variants": state.variants,
        "orders": state.orders,
        "customers": state.customers,
        "history_days": state.history_days,
        "note": state.note,
    }
