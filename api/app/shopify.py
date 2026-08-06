"""
Pulling real data out of Shopify.

The seeder is the default and the demo path — this is what you point at the
real store once you have API credentials. Everything lands in exactly the same
tables, so nothing downstream changes: the dashboard, the copilot and the
forecaster can't tell which one filled the database.

    python -m app.shopify

Customer data is anonymised on the way in and never stored as it arrives.
noszn's customers didn't agree to be in a portfolio project, so first names
are reduced to an initial and email addresses are replaced with a hash. The
dashboard only ever needed to count people, not identify them.
"""

import asyncio
import hashlib
from datetime import datetime

import httpx
from sqlmodel import Session, delete

from app.config import settings
from app.db import create_tables, engine
from app.models import Customer, DailySales, Order, OrderLine, Product, Variant

API_VERSION = "2024-10"
PAGE_SIZE = 250  # Shopify's maximum


def anonymise_name(name: str) -> str:
    """"Amara Bennett" becomes "Amara B." — enough to tell people apart."""
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "Customer"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def anonymise_email(email: str) -> str:
    """
    A stable fake address.

    Hashed rather than dropped so the same customer keeps the same identity
    across syncs, which is what repeat-purchase rate depends on.
    """
    digest = hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:12]
    return f"{digest}@customers.invalid"


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    # Shopify sends "2026-08-04T10:31:00+01:00"; drop the offset for SQLite.
    return datetime.fromisoformat(value).replace(tzinfo=None)


class ShopifyClient:
    """A small REST Admin API client with cursor pagination."""

    def __init__(self, domain: str | None = None, token: str | None = None):
        self.domain = (domain or settings.shopify_store_domain).replace("https://", "").strip("/")
        self.token = token or settings.shopify_access_token

        if not self.domain or not self.token:
            raise ValueError(
                "Shopify isn't configured. Set SHOPIFY_STORE_DOMAIN and "
                "SHOPIFY_ACCESS_TOKEN, or just run the seeder instead."
            )

        self.base = f"https://{self.domain}/admin/api/{API_VERSION}"

    async def fetch_all(self, resource: str, **params) -> list[dict]:
        """
        Every page of a resource.

        Shopify pages with a Link header rather than a page number, so the
        next URL has to be read out of it — there's no way to guess it.
        """
        rows: list[dict] = []
        url = f"{self.base}/{resource}.json"
        query: dict | None = {"limit": PAGE_SIZE, **params}

        async with httpx.AsyncClient(
            timeout=60.0, headers={"X-Shopify-Access-Token": self.token}
        ) as client:
            while url:
                response = await client.get(url, params=query)

                # 429 means we're going too fast. Shopify says how long to wait.
                if response.status_code == 429:
                    await asyncio.sleep(float(response.headers.get("Retry-After", 2)))
                    continue

                response.raise_for_status()
                rows.extend(response.json().get(resource, []))

                url = next_page_url(response.headers.get("Link", ""))
                query = None  # the next URL already carries the cursor

        return rows


def next_page_url(link_header: str) -> str | None:
    """Pull the rel="next" URL out of a Link header, if there is one."""
    for part in link_header.split(","):
        if 'rel="next"' in part:
            start, end = part.find("<"), part.find(">")
            if start != -1 and end != -1:
                return part[start + 1 : end]
    return None


async def sync() -> dict:
    """Replace everything in the database with what Shopify currently has."""
    client = ShopifyClient()
    create_tables()

    products = await client.fetch_all("products")
    customers = await client.fetch_all("customers")
    orders = await client.fetch_all("orders", status="any")

    with Session(engine) as session:
        # Full replace rather than a merge. Simpler, and correct as long as
        # this runs as a scheduled refresh rather than an incremental sync.
        for model in (DailySales, OrderLine, Order, Customer, Variant, Product):
            session.exec(delete(model))
        session.commit()

        variant_ids: dict[str, int] = {}
        product_ids: dict[str, int] = {}

        for row in products:
            product = Product(
                shopify_id=str(row["id"]),
                title=row.get("title", ""),
                handle=row.get("handle", ""),
                product_type=(row.get("product_type") or "other").lower(),
                tags=row.get("tags", ""),
                description="",
                price=float(row["variants"][0]["price"]) if row.get("variants") else 0.0,
                image_url=(row.get("image") or {}).get("src", "") or "",
                created_at=parse_time(row.get("created_at")),
            )
            session.add(product)
            session.commit()
            session.refresh(product)
            product_ids[str(row["id"])] = product.id

            for variant_row in row.get("variants", []):
                variant = Variant(
                    product_id=product.id,
                    title=variant_row.get("title", "One Size"),
                    sku=variant_row.get("sku") or "",
                    price=float(variant_row.get("price") or 0),
                    inventory_quantity=int(variant_row.get("inventory_quantity") or 0),
                )
                session.add(variant)
                session.commit()
                session.refresh(variant)
                variant_ids[str(variant_row["id"])] = variant.id

        customer_ids: dict[str, int] = {}
        for row in customers:
            full_name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}"
            customer = Customer(
                shopify_id=str(row["id"]),
                name=anonymise_name(full_name),
                email=anonymise_email(row.get("email") or str(row["id"])),
                created_at=parse_time(row.get("created_at")),
                country=(row.get("default_address") or {}).get("country_code") or "",
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)
            customer_ids[str(row["id"])] = customer.id

        # Sales per variant per day, for the forecaster.
        daily: dict[tuple[int, object], int] = {}
        lines = 0

        for row in orders:
            shopify_customer = str((row.get("customer") or {}).get("id", ""))
            customer_id = customer_ids.get(shopify_customer)
            if customer_id is None:
                # A guest checkout, or a customer we didn't get back.
                continue

            created = parse_time(row.get("created_at"))
            order = Order(
                shopify_id=str(row["id"]),
                customer_id=customer_id,
                created_at=created,
                total_price=float(row.get("total_price") or 0),
                financial_status=row.get("financial_status") or "paid",
            )
            session.add(order)
            session.commit()
            session.refresh(order)

            for item in row.get("line_items", []):
                variant_id = variant_ids.get(str(item.get("variant_id")))
                product_id = product_ids.get(str(item.get("product_id")))
                if variant_id is None or product_id is None:
                    # The product was deleted after the order was placed.
                    continue

                quantity = int(item.get("quantity") or 0)
                session.add(
                    OrderLine(
                        order_id=order.id,
                        product_id=product_id,
                        variant_id=variant_id,
                        quantity=quantity,
                        price=float(item.get("price") or 0),
                    )
                )
                lines += 1
                key = (variant_id, created.date())
                daily[key] = daily.get(key, 0) + quantity

        session.add_all(
            DailySales(variant_id=variant_id, day=day, units=units)
            for (variant_id, day), units in daily.items()
        )
        session.commit()

    return {
        "products": len(products),
        "customers": len(customers),
        "orders": len(orders),
        "lines": lines,
    }


if __name__ == "__main__":
    result = asyncio.run(sync())
    print(
        f"synced {result['products']} products, {result['customers']} customers, "
        f"{result['orders']} orders ({result['lines']} lines)"
    )
    print("now rebuild the search index: python -m app.rag")
