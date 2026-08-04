"""
Synthetic data seeder for noszn.

Run this once and the whole dashboard works with no Shopify keys and no paid
APIs. Everything here is made up — no real customer ever touches this file.

The simulation runs day by day for a year so the numbers behave like a real
small brand: quiet Mondays, busy weekends, hoodies picking up in autumn, a
couple of spikes when a drop lands, and stock draining between restocks.
That last part matters — it means the low-stock alerts and the forecaster have
genuine patterns to find rather than random noise.

    python -m app.seed
"""

import random
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, delete

from app.db import engine, create_tables
from app.models import (
    Customer,
    DailySales,
    Order,
    OrderLine,
    Product,
    Review,
    Variant,
)

# Same seed every time so the demo always looks the same.
RNG = random.Random(42)

DAYS_OF_HISTORY = 365
APPAREL_SIZES = ["XS", "S", "M", "L", "XL"]
ONE_SIZE = ["One Size"]

# How likely each size is to be the one picked. Middle sizes dominate, which is
# why they're always the first to sell out in real life.
SIZE_WEIGHTS = {"XS": 0.06, "S": 0.18, "M": 0.31, "L": 0.27, "XL": 0.13, "XXL": 0.05, "One Size": 1.0}

# The catalogue. (title, type, price, cost, popularity, season, tags)
# popularity = relative share of sales. season shifts demand across the year:
#   "warm"  sells more in summer, "cold" more in autumn/winter, "all" is flat.
CATALOGUE = [
    ("Core Hoodie — Black",      "hoodie",     85.0, 26.0, 1.00, "cold", "hoodie,heavyweight,black,essential"),
    ("Core Hoodie — Bone",       "hoodie",     85.0, 26.0, 0.72, "cold", "hoodie,heavyweight,bone,essential"),
    ("Zip Hood — Slate",         "hoodie",     92.0, 29.0, 0.48, "cold", "hoodie,zip,slate,layer"),
    ("Boxy Tee — Black",         "tee",        38.0, 9.50, 0.88, "warm", "tee,boxy,black,essential"),
    ("Boxy Tee — White",         "tee",        38.0, 9.50, 0.76, "warm", "tee,boxy,white,essential"),
    ("Washed Tee — Charcoal",    "tee",        42.0, 11.0, 0.54, "warm", "tee,washed,charcoal"),
    ("Longsleeve — Bone",        "longsleeve", 48.0, 14.0, 0.42, "all",  "longsleeve,bone,layer"),
    ("Crewneck — Ash",           "crewneck",   75.0, 23.0, 0.51, "cold", "crewneck,ash,grey,knit"),
    ("Cargo Pant — Black",       "trouser",    95.0, 31.0, 0.64, "all",  "cargo,trouser,black,utility"),
    ("Wide Leg Sweat — Grey",    "trouser",    70.0, 21.0, 0.58, "cold", "sweatpant,wideleg,grey"),
    ("Cargo Short — Stone",      "short",      65.0, 19.0, 0.31, "warm", "short,cargo,stone,utility"),
    ("Puffer Vest — Black",      "outerwear", 120.0, 42.0, 0.27, "cold", "vest,puffer,black,outerwear"),
    ("Knit Beanie — Black",      "accessory",  28.0, 7.00, 0.44, "cold", "beanie,knit,black,accessory"),
    ("Cap — Washed Black",       "accessory",  32.0, 8.50, 0.39, "all",  "cap,washed,black,accessory"),
]

FIRST_NAMES = ["Amara", "Josh", "Leila", "Kofi", "Sam", "Priya", "Deniz", "Mia", "Tomas", "Ife",
               "Ryan", "Zara", "Elias", "Nina", "Jude", "Hana", "Marcus", "Ada", "Reuben", "Sofia"]
LAST_NAMES = ["Bennett", "Osei", "Whitfield", "Nakamura", "Adeyemi", "Clarke", "Yilmaz", "Novak",
              "Rahman", "Fletcher", "Silva", "Mensah", "Kaur", "Doyle", "Petrov", "Ellis"]

# Review text, grouped by the theme it's really about. The sentiment feature
# has to rediscover these themes on its own — they aren't stored as labels.
POSITIVE_REVIEWS = [
    ("fabric", "heavyweight for real. washed it twice and it hasn't lost shape."),
    ("fabric", "the cotton on this is so much thicker than i expected for the price."),
    ("fit", "boxy fit is exactly right. not too cropped."),
    ("fit", "finally a hood that fits properly across the shoulders."),
    ("shipping", "ordered monday, arrived wednesday. no complaints."),
    ("shipping", "packaging was clean and it came quicker than the estimate."),
    ("colour", "the black is properly black, not that faded grey you get elsewhere."),
    ("quality", "stitching is neat all the way through. feels expensive."),
    ("quality", "third piece i've bought from noszn and the quality has been consistent."),
    ("service", "messaged about a size swap and got a reply the same day."),
]
NEGATIVE_REVIEWS = [
    ("sizing", "runs small. i'm normally a M and had to size up to L."),
    ("sizing", "sizing chart wasn't accurate for me, sleeves were short."),
    ("sizing", "had to return and reorder a size up, wish the chart was clearer."),
    ("shipping", "took 9 days to arrive which was longer than the estimate said."),
    ("shipping", "no tracking update for four days, had no idea where it was."),
    ("stock", "the size i wanted has been out of stock for weeks."),
    ("stock", "sold out before i could check out, gutted."),
    ("colour", "the bone is more cream than the photos suggest."),
    ("returns", "return took a while to be refunded."),
    ("price", "good piece but the price is a stretch for a tee."),
]
NEUTRAL_REVIEWS = [
    ("fit", "decent. fit is fine, nothing that stood out either way."),
    ("fabric", "it's ok. does the job, not sure it's worth the hype."),
    ("shipping", "arrived on the day it said it would."),
]


def seasonal_multiplier(day: datetime, season: str) -> float:
    """
    Push demand up or down depending on the time of year.

    Uses day-of-year on a simple cosine so the curve is smooth rather than
    jumping at month boundaries. Peak for "cold" is January, "warm" is July.
    """
    import math

    # 0 in January, rises to 1 in July, back to 0 in January.
    summerness = 0.5 - 0.5 * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365)

    if season == "warm":
        return 0.65 + 0.7 * summerness
    if season == "cold":
        return 0.65 + 0.7 * (1 - summerness)
    return 1.0


def orders_for_day(day: datetime, day_index: int, drop_days: set) -> int:
    """How many orders land on a given day."""
    base = 7.0

    # The brand grows over the year — roughly doubles from start to end.
    growth = 1.0 + (day_index / DAYS_OF_HISTORY)

    # Weekends are busier, Monday is the graveyard.
    weekday_boost = {0: 0.8, 1: 0.9, 2: 0.95, 3: 1.0, 4: 1.15, 5: 1.3, 6: 1.2}[day.weekday()]

    # A drop day and the two days after it are chaos.
    drop_boost = 1.0
    for offset in range(3):
        if (day_index - offset) in drop_days:
            drop_boost = [4.5, 2.4, 1.6][offset]
            break

    expected = base * growth * weekday_boost * drop_boost
    # Poisson-ish noise so no two days are identical.
    return max(0, int(RNG.gauss(expected, expected * 0.3)))


def seed() -> None:
    create_tables()

    with Session(engine) as session:
        # Wipe first so re-running the seeder is safe.
        for model in (DailySales, Review, OrderLine, Order, Customer, Variant, Product):
            session.exec(delete(model))
        session.commit()

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=DAYS_OF_HISTORY)

        # --- products and variants ---
        products, variants = [], []
        for title, ptype, price, cost, popularity, season, tags in CATALOGUE:
            handle = title.lower().replace(" — ", "-").replace(" ", "-")
            product = Product(
                shopify_id=f"gid://shopify/Product/{7000000 + len(products)}",
                title=title,
                handle=handle,
                product_type=ptype,
                tags=tags,
                description="",  # filled in later by the AI copy generator
                price=price,
                cost=cost,
                image_url="",
                created_at=start - timedelta(days=RNG.randint(10, 120)),
            )
            session.add(product)
            session.commit()
            session.refresh(product)
            products.append((product, popularity, season))

            sizes = ONE_SIZE if ptype == "accessory" else APPAREL_SIZES
            for size in sizes:
                variant = Variant(
                    product_id=product.id,
                    title=size,
                    sku=f"NSZN-{product.id:02d}-{size.replace(' ', '')[:2].upper()}",
                    price=price,
                    inventory_quantity=0,  # set by the restock simulation below
                )
                session.add(variant)
                variants.append(variant)
        session.commit()
        for v in variants:
            session.refresh(v)

        # Group variants by product so picking a size is easy.
        variants_by_product = {}
        for v in variants:
            variants_by_product.setdefault(v.product_id, []).append(v)

        # --- customers ---
        # Customers aren't created up front — a customer account appears the
        # day someone first orders, which is how it really works and is what
        # keeps the repeat-purchase rate honest.
        customers = []

        def new_customer(day: datetime) -> Customer:
            first = RNG.choice(FIRST_NAMES)
            last = RNG.choice(LAST_NAMES)
            customer = Customer(
                shopify_id=f"gid://shopify/Customer/{5000000 + len(customers)}",
                name=f"{first} {last[0]}.",  # only an initial — no full fake identities
                email=f"customer{len(customers):05d}@example.com",  # example.com is reserved
                created_at=day,
                country=RNG.choices(["GB", "IE", "DE", "US", "FR"], weights=[70, 8, 8, 9, 5])[0],
            )
            session.add(customer)
            session.flush()
            customers.append(customer)
            return customer

        # --- stock levels ---
        # Restock every 60 days. Each restock tops a variant up to roughly 1.5x
        # what we expect to sell before the next delivery, so between
        # deliveries the middle sizes drain first and the odd size actually
        # runs out. The buffer ignores seasonality on purpose — that mismatch
        # is exactly the situation the forecaster is meant to catch.
        restock_days = set(range(0, DAYS_OF_HISTORY - 40, 60))
        stock = {v.id: 0 for v in variants}

        def restock_target(popularity: float, size: str, day_index: int) -> int:
            """Roughly 60 days of expected demand, plus a buffer."""
            growth = 1.0 + (day_index / DAYS_OF_HISTORY)
            return max(20, int(185 * popularity * SIZE_WEIGHTS[size] * growth))

        # units sold per (variant, day) — becomes the DailySales table
        daily_units = {}
        # Drop days — the brand releases a few times a year and orders spike.
        # The last one is recent on purpose so the dashboard opens on a real
        # story ("revenue is up, there was a drop two weeks ago") rather than
        # a flat month.
        drop_days = {68, 152, 240, 300, 352}
        order_rows, line_rows = [], []

        # Customers who have bought at least once, so repeat orders are real
        # repeats rather than random picks. The repeat rate metric depends on
        # this being honest.
        returning = []

        for day_index in range(DAYS_OF_HISTORY):
            day = start + timedelta(days=day_index)

            if day_index in restock_days:
                for product, popularity, _season in products:
                    for v in variants_by_product[product.id]:
                        stock[v.id] = restock_target(popularity, v.title, day_index)

            # Weight each product for today by popularity and season.
            weights = [p[1] * seasonal_multiplier(day, p[2]) for p in products]

            for _ in range(orders_for_day(day, day_index, drop_days)):
                # ~35% of orders are someone coming back. Everyone else is a
                # brand new customer, created on the spot.
                if returning and RNG.random() < 0.35:
                    customer = RNG.choice(returning)
                else:
                    customer = new_customer(day)

                order = Order(
                    shopify_id=f"gid://shopify/Order/{9000000 + len(order_rows)}",
                    customer_id=customer.id,
                    created_at=day + timedelta(hours=RNG.randint(8, 23), minutes=RNG.randint(0, 59)),
                    total_price=0.0,
                    financial_status="paid",
                )
                session.add(order)
                session.flush()  # assigns the id without a full commit — much faster

                total = 0.0
                # Most people buy one thing, some buy two or three.
                for _ in range(RNG.choices([1, 2, 3], weights=[62, 28, 10])[0]):
                    product, _pop, _season = RNG.choices(products, weights=weights)[0]
                    choices = variants_by_product[product.id]
                    variant = RNG.choices(choices, weights=[SIZE_WEIGHTS[c.title] for c in choices])[0]

                    # Can't sell what isn't there — this is what creates the
                    # lost sales that make stockouts worth forecasting.
                    if stock[variant.id] <= 0:
                        continue

                    quantity = 1 if RNG.random() < 0.9 else 2
                    quantity = min(quantity, stock[variant.id])
                    stock[variant.id] -= quantity

                    line_rows.append(
                        OrderLine(
                            order_id=order.id,
                            product_id=product.id,
                            variant_id=variant.id,
                            quantity=quantity,
                            price=product.price,
                        )
                    )
                    total += product.price * quantity
                    key = (variant.id, day.date())
                    daily_units[key] = daily_units.get(key, 0) + quantity

                order.total_price = round(total, 2)
                order_rows.append(order)
                if total > 0:
                    returning.append(customer)

        # Orders where everything was out of stock ended up empty — drop them.
        empty_ids = {o.id for o in order_rows if o.total_price == 0}
        for order in order_rows:
            if order.id in empty_ids:
                session.delete(order)
            else:
                session.add(order)
        session.add_all(line_rows)
        session.commit()

        # Final stock levels are whatever the simulation left behind.
        for variant in variants:
            variant.inventory_quantity = stock[variant.id]
            session.add(variant)
        session.commit()

        # --- dense daily sales series for the forecaster ---
        rows = []
        for variant in variants:
            for day_index in range(DAYS_OF_HISTORY):
                day = (start + timedelta(days=day_index)).date()
                rows.append(
                    DailySales(
                        variant_id=variant.id,
                        day=day,
                        units=daily_units.get((variant.id, day), 0),
                    )
                )
        session.add_all(rows)
        session.commit()

        # --- reviews ---
        # Weighted so most people are happy but there's a real seam of
        # complaints about sizing and shipping for the AI to surface.
        review_count = 0
        for product, popularity, _season in products:
            for _ in range(int(14 * popularity) + RNG.randint(1, 4)):
                bucket = RNG.choices(
                    [POSITIVE_REVIEWS, NEGATIVE_REVIEWS, NEUTRAL_REVIEWS],
                    weights=[64, 27, 9],
                )[0]
                _theme, body = RNG.choice(bucket)
                if bucket is POSITIVE_REVIEWS:
                    rating = RNG.choice([5, 5, 5, 4])
                elif bucket is NEGATIVE_REVIEWS:
                    rating = RNG.choice([1, 2, 2, 3])
                else:
                    rating = 3

                session.add(
                    Review(
                        product_id=product.id,
                        customer_name=f"{RNG.choice(FIRST_NAMES)} {RNG.choice(LAST_NAMES)[0]}.",
                        rating=rating,
                        body=body,
                        created_at=today - timedelta(days=RNG.randint(0, 200)),
                        sentiment=None,  # the AI fills this in, not the seeder
                        theme=None,
                    )
                )
                review_count += 1
        session.commit()

        kept_orders = len(order_rows) - len(empty_ids)
        revenue = sum(o.total_price for o in order_rows if o.id not in empty_ids)
        print(f"seeded {len(products)} products / {len(variants)} variants")
        print(f"        {kept_orders} orders, {len(line_rows)} lines, £{revenue:,.0f} revenue")
        print(f"        {len(customers)} customers, {review_count} reviews")


if __name__ == "__main__":
    seed()
