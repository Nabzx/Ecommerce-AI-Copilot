"""
Database tables.

The shapes deliberately mirror what the Shopify Admin API gives back
(products have variants, orders have line items) so the synthetic seeder and a
real Shopify sync can write to exactly the same tables.
"""

from datetime import datetime, date
from typing import Optional

from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shopify_id: Optional[str] = Field(default=None, index=True)
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

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    title: str  # "M", "L", "One Size"
    sku: str
    price: float
    inventory_quantity: int


class Customer(SQLModel, table=True):
    """PII is never real. The seeder makes fake names and hashed-looking emails."""

    id: Optional[int] = Field(default=None, primary_key=True)
    shopify_id: Optional[str] = Field(default=None, index=True)
    name: str
    email: str
    created_at: datetime
    country: str = "GB"


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shopify_id: Optional[str] = Field(default=None, index=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    created_at: datetime = Field(index=True)
    total_price: float
    financial_status: str = "paid"


class OrderLine(SQLModel, table=True):
    """One line of an order: which variant, how many, at what price."""

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    variant_id: int = Field(foreign_key="variant.id", index=True)
    quantity: int
    price: float


class Review(SQLModel, table=True):
    """Customer reviews. `sentiment` starts empty and the AI fills it in."""

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    customer_name: str
    rating: int  # 1-5
    body: str
    created_at: datetime
    sentiment: Optional[str] = Field(default=None, index=True)  # positive/neutral/negative
    theme: Optional[str] = None  # e.g. "sizing", "shipping speed"


class Chunk(SQLModel, table=True):
    """
    A piece of store knowledge the copilot can retrieve and cite.

    Each row records which embedder produced its vector, because vectors from
    two different models can't be compared — mixing them would return
    confident nonsense rather than an obvious error.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)  # "shipping.md" or "catalogue"
    title: str  # "Shipping › Drops" — shown as the citation
    text: str
    embedder: str  # "model:nomic-embed-text" or "tfidf"
    dim: int
    embedding: bytes  # float32 array, packed


class DailySales(SQLModel, table=True):
    """
    Units sold per variant per day.

    The orders table could give us this with a GROUP BY, but the forecaster
    wants a dense day-by-day series (including zero days) and precomputing it
    once at seed time keeps the forecast endpoint fast and simple.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    variant_id: int = Field(foreign_key="variant.id", index=True)
    day: date = Field(index=True)
    units: int
