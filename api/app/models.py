"""
Database tables.

The shapes deliberately mirror what the Shopify Admin API gives back
(products have variants, orders have line items) so the synthetic seeder and a
real Shopify sync can write to exactly the same tables.
"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    shopify_id: str | None = Field(default=None, index=True)
    title: str
    handle: str = Field(index=True)
    product_type: str  # hoodie, tee, cargos ...
    tags: str = ""  # comma separated, same as Shopify does it
    description: str = ""
    price: float
    cost: float = 0.0  # what it costs noszn to make, for margin
    image_url: str = ""
    created_at: datetime


class Variant(SQLModel, table=True):
    """A size of a product. Stock lives here, not on the product."""

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    title: str  # "M", "L", "One Size"
    sku: str
    price: float
    inventory_quantity: int


class Customer(SQLModel, table=True):
    """PII is never real. The seeder makes fake names and hashed-looking emails."""

    id: int | None = Field(default=None, primary_key=True)
    shopify_id: str | None = Field(default=None, index=True)
    name: str
    email: str
    created_at: datetime
    country: str = "GB"


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    shopify_id: str | None = Field(default=None, index=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    created_at: datetime = Field(index=True)
    total_price: float
    financial_status: str = "paid"


class OrderLine(SQLModel, table=True):
    """One line of an order: which variant, how many, at what price."""

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    variant_id: int = Field(foreign_key="variant.id", index=True)
    quantity: int
    price: float


class Review(SQLModel, table=True):
    """Customer reviews. `sentiment` starts empty and the AI fills it in."""

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    customer_name: str
    rating: int  # 1-5
    body: str
    created_at: datetime
    sentiment: str | None = Field(default=None, index=True)  # positive/neutral/negative
    theme: str | None = None  # e.g. "sizing", "shipping speed"


class Chunk(SQLModel, table=True):
    """
    A piece of store knowledge the copilot can retrieve and cite.

    Each row records which embedder produced its vector, because vectors from
    two different models can't be compared — mixing them would return
    confident nonsense rather than an obvious error.
    """

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)  # "shipping.md" or "catalogue"
    title: str  # "Shipping › Drops" — shown as the citation
    text: str  # what the copilot reads
    # What was actually embedded, which isn't always the same as `text`. The
    # TF-IDF fallback has to refit on this exact corpus to embed a query — fit
    # it on anything else and the vocabulary differs, so the query vector comes
    # out a different length to the stored ones and nothing matches at all.
    embed_text: str = ""
    # For catalogue chunks, the product this describes. Lets semantic search
    # get back to a real row instead of matching on the title string.
    ref_id: int | None = Field(default=None, index=True)
    embedder: str  # "model:nomic-embed-text" or "tfidf"
    dim: int
    embedding: bytes  # float32 array, packed


class SyncState(SQLModel, table=True):
    """
    What filled this database, and when.

    One row, replaced each time. Without it there's no way to tell a demo from
    a real store by looking at the dashboard, and "is this my actual data?" is
    the first thing anyone asks.
    """

    id: int | None = Field(default=None, primary_key=True)
    source: str  # "demo" or "shopify"
    store_domain: str = ""
    synced_at: datetime
    products: int = 0
    variants: int = 0
    orders: int = 0
    customers: int = 0
    history_days: int = 0
    # Set when the sync finished but something was off — e.g. no cost data, so
    # margin will read as 100%. Shown in the UI rather than buried in a log.
    note: str = ""


class Alert(SQLModel, table=True):
    """
    A rule the owner typed in plain English.

    Both halves are kept: `phrase` is what they actually wrote, so the
    dashboard can show it back to them in their own words, and `rule` is the
    structured version the evaluator runs.
    """

    id: int | None = Field(default=None, primary_key=True)
    phrase: str
    rule: str  # the parsed AlertRule, as JSON
    created_at: datetime
    active: bool = True


class DailySales(SQLModel, table=True):
    """
    Units sold per variant per day.

    The orders table could give us this with a GROUP BY, but the forecaster
    wants a dense day-by-day series (including zero days) and precomputing it
    once at seed time keeps the forecast endpoint fast and simple.
    """

    id: int | None = Field(default=None, primary_key=True)
    variant_id: int = Field(foreign_key="variant.id", index=True)
    day: date = Field(index=True)
    units: int
