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
import re
from datetime import datetime, timedelta

import httpx
from sqlmodel import Session, delete

from app import datasource
from app.config import settings
from app.db import create_tables, engine
from app.models import Customer, DailySales, Order, OrderLine, Product, Review, Variant

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


def strip_html(html: str) -> str:
    """
    Shopify keeps product descriptions as HTML. The copilot and the copy
    generator want the words, not the markup.
    """
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    # Collapse the blank lines the markup leaves behind.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    # Shopify sends "2026-08-04T10:31:00+01:00"; drop the offset for SQLite.
    return datetime.fromisoformat(value).replace(tzinfo=None)


class ShopifyClient:
    """A small REST Admin API client with cursor pagination."""

    def __init__(
        self,
        domain: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        # Tests pass a fake transport so the mapping can be checked without a
        # real store, which is the only way to test this without credentials.
        self._transport = transport
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
            timeout=60.0,
            transport=self._transport,
            headers={"X-Shopify-Access-Token": self.token},
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


    async def fetch_costs(self, inventory_item_ids: list[str]) -> dict[str, float]:
        """
        What each variant costs to make.

        Shopify doesn't put cost on the variant — it lives on the inventory
        item behind it, which is a second call. Worth making, because without
        it every margin reads as 100% and the numbers are worse than useless.

        Blank unless the shop actually fills cost per item in, which plenty
        don't; the sync says so afterwards rather than silently showing 100%.
        """
        costs: dict[str, float] = {}

        # The endpoint takes a batch of ids, up to 100 at a time.
        for start in range(0, len(inventory_item_ids), 100):
            batch = inventory_item_ids[start : start + 100]
            rows = await self.fetch_all("inventory_items", ids=",".join(batch))
            for row in rows:
                cost = row.get("cost")
                if cost is not None:
                    costs[str(row["id"])] = float(cost)

        return costs

    async def shop(self) -> dict:
        """The shop record — used to check credentials before a full sync."""
        async with httpx.AsyncClient(
            timeout=30.0,
            transport=self._transport,
            headers={"X-Shopify-Access-Token": self.token},
        ) as client:
            response = await client.get(f"{self.base}/shop.json")

        if response.status_code == 401:
            raise ValueError("Shopify rejected the access token.")
        if response.status_code == 404:
            raise ValueError(f"No shop at {self.domain}. Check the domain.")
        response.raise_for_status()

        return response.json().get("shop", {})


def refunded_quantities(order: dict) -> dict[str, int]:
    """
    How many of each line item came back.

    An order that was half refunded still shows its original total in the
    orders list. Counting that as revenue would put the dashboard permanently
    above what Shopify itself reports, and the first thing anyone does is
    check the two against each other.
    """
    refunded: dict[str, int] = {}

    for refund in order.get("refunds", []):
        for line in refund.get("refund_line_items", []):
            line_id = str(line.get("line_item_id"))
            refunded[line_id] = refunded.get(line_id, 0) + int(line.get("quantity") or 0)

    return refunded


def line_revenue(item: dict, quantity: int) -> float:
    """
    What a line actually brought in.

    `price` is before any discount, so a 20% off code would otherwise be
    invisible. Shopify reports the reduction per line in discount_allocations.
    """
    price = float(item.get("price") or 0)
    ordered = int(item.get("quantity") or 0) or 1

    discount = sum(
        float(allocation.get("amount") or 0)
        for allocation in item.get("discount_allocations", [])
    )
    # The discount covers the whole line; scale it to the units we kept.
    discount_per_unit = discount / ordered

    return max(0.0, (price - discount_per_unit) * quantity)


def next_page_url(link_header: str) -> str | None:
    """Pull the rel="next" URL out of a Link header, if there is one."""
    for part in link_header.split(","):
        if 'rel="next"' in part:
            start, end = part.find("<"), part.find(">")
            if start != -1 and end != -1:
                return part[start + 1 : end]
    return None


async def sync(history_days: int = 365, client: "ShopifyClient | None" = None) -> dict:
    """
    Replace everything in the database with what Shopify currently has.

    Only pulls `history_days` of orders. A shop that has been running for
    years would otherwise drag its entire history down every sync, and the
    forecaster only looks back a few months anyway.
    """
    client = client or ShopifyClient()
    create_tables()

    since = (datetime.now() - timedelta(days=history_days)).isoformat()

    products = await client.fetch_all("products")
    customers = await client.fetch_all("customers")
    orders = await client.fetch_all("orders", status="any", created_at_min=since)

    # Cost lives behind the variant, on the inventory item.
    inventory_item_ids = [
        str(v["inventory_item_id"])
        for p in products
        for v in p.get("variants", [])
        if v.get("inventory_item_id")
    ]
    costs = await client.fetch_costs(inventory_item_ids)

    with Session(engine) as session:
        # Full replace rather than a merge. Simpler, and correct as long as
        # this runs as a scheduled refresh rather than an incremental sync.
        #
        # Reviews go too, and they're the awkward one. Shopify's Admin API has
        # no reviews resource at all — they live in whatever app the shop uses
        # (Judge.me, Loox, and so on). So the only reviews here are the demo
        # ones, and leaving them would be worse than dropping them: products
        # are recreated with fresh ids, so every review would end up attached
        # to whichever product happened to land on its old id, and the
        # sentiment card would blame the wrong things with total confidence.
        for model in (DailySales, Review, OrderLine, Order, Customer, Variant, Product):
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
                status=(row.get("status") or "active").lower(),
                description=strip_html(row.get("body_html") or ""),
                price=float(row["variants"][0]["price"]) if row.get("variants") else 0.0,
                cost=next(
                    (
                        costs[str(v["inventory_item_id"])]
                        for v in row.get("variants", [])
                        if str(v.get("inventory_item_id")) in costs
                    ),
                    0.0,
                ),
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
        order_ids_seen: set[int] = set()

        for row in orders:
            # A cancelled order never happened as far as the numbers go.
            if row.get("cancelled_at"):
                continue

            shopify_customer = str((row.get("customer") or {}).get("id", ""))
            customer_id = customer_ids.get(shopify_customer)
            if customer_id is None:
                # A guest checkout, or a customer we didn't get back.
                continue

            created = parse_time(row.get("created_at"))
            refunded = refunded_quantities(row)

            order = Order(
                shopify_id=str(row["id"]),
                customer_id=customer_id,
                created_at=created,
                # current_total_price is what the order is worth now, after any
                # refunds or edits. total_price is what it was on the day.
                total_price=float(row.get("current_total_price") or row.get("total_price") or 0),
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

                # What's left after anything that came back.
                quantity = int(item.get("quantity") or 0) - refunded.get(str(item.get("id")), 0)
                if quantity <= 0:
                    continue

                session.add(
                    OrderLine(
                        order_id=order.id,
                        product_id=product_id,
                        variant_id=variant_id,
                        quantity=quantity,
                        # Per unit and after discount, so the line totals add
                        # up to what the customer was actually charged.
                        price=line_revenue(item, quantity) / quantity,
                    )
                )
                lines += 1
                order_ids_seen.add(order.id)
                key = (variant_id, created.date())
                daily[key] = daily.get(key, 0) + quantity

        session.add_all(
            DailySales(variant_id=variant_id, day=day, units=units)
            for (variant_id, day), units in daily.items()
        )
        session.commit()

        note = ""
        if not costs:
            note = (
                "No cost per item in Shopify, so margin will read as 100%. "
                "Add cost under each variant's inventory to fix it."
            )

        datasource.record(
            session,
            datasource.SHOPIFY,
            products=len(products),
            variants=len(variant_ids),
            orders=len(order_ids_seen),
            customers=len(customers),
            history_days=history_days,
            store_domain=client.domain,
            note=note,
        )

    return {
        "products": len(products),
        "customers": len(customers),
        "orders": len(order_ids_seen),
        "lines": lines,
        "costs_found": len(costs),
        "note": note,
    }


async def check() -> dict:
    """
    Confirm the credentials work before pulling anything.

    Worth its own command: a wrong domain or a token missing a scope otherwise
    shows up halfway through a full sync, with the database already emptied.
    """
    client = ShopifyClient()
    shop = await client.shop()

    return {
        "connected": True,
        "shop": shop.get("name", ""),
        "domain": client.domain,
        "currency": shop.get("currency", ""),
        "timezone": shop.get("iana_timezone", ""),
    }


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        try:
            info = asyncio.run(check())
        except ValueError as exc:
            print(f"not connected: {exc}")
            raise SystemExit(1) from None
        print(f"connected to {info['shop']} ({info['domain']}), {info['currency']}")
        raise SystemExit(0)

    result = asyncio.run(sync())
    print(
        f"synced {result['products']} products, {result['customers']} customers, "
        f"{result['orders']} orders ({result['lines']} lines)"
    )
    print("now rebuild the search index: python -m app.rag")
