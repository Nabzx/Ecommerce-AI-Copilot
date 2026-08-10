"""
Stock that isn't moving, and what it's costing to sit there.

The mirror of the forecast. That card says what to buy; this one says what to
stop buying, which is the half people ignore until the money is already on a
shelf.

The definition matters more than it looks. "Hasn't sold in 60 days" is the
obvious one and it's nearly useless — on a shop where everything trickles it
finds nothing at all (it finds exactly zero sizes on the demo data). What
actually ties up cash is stock that *is* selling, just far too slowly for how
much of it there is: fourteen sizes here would take over three months to clear,
and that's £8.5k sitting still.

So the measure is days of cover — how long the stock on hand would last at the
rate it's currently going.
"""

from datetime import date, timedelta

from sqlmodel import Session, func, select

from app.models import DailySales, Product, Variant

# How far back to measure the selling rate.
WINDOW_DAYS = 60

# Past this many days of cover, the stock is tying up money rather than
# serving demand. Three months is roughly two production cycles for noszn.
SLOW_COVER_DAYS = 90


def report(
    session: Session,
    window_days: int = WINDOW_DAYS,
    slow_after_days: int = SLOW_COVER_DAYS,
) -> dict:
    """Everything that's moving too slowly for how much of it there is."""
    since = date.today() - timedelta(days=window_days)
    cutoff = date.today() - timedelta(days=window_days)

    rows = session.exec(
        select(Variant, Product).join(Product, Product.id == Variant.product_id)
    ).all()

    not_selling: list[dict] = []
    slow: list[dict] = []
    total_units = 0
    total_at_cost = 0.0
    total_at_retail = 0.0
    have_costs = False

    for variant, product in rows:
        if variant.inventory_quantity <= 0:
            continue

        total_units += variant.inventory_quantity
        total_at_cost += variant.inventory_quantity * product.cost
        total_at_retail += variant.inventory_quantity * variant.price
        if product.cost > 0:
            have_costs = True

        # A drop that launched last week hasn't had a chance to sell yet, and
        # calling it dead stock would be both wrong and annoying.
        if product.created_at.date() > cutoff:
            continue

        sold = session.exec(
            select(func.coalesce(func.sum(DailySales.units), 0)).where(
                DailySales.variant_id == variant.id, DailySales.day >= since
            )
        ).one()

        rate = float(sold) / window_days
        entry = {
            "variant_id": variant.id,
            "product_id": product.id,
            "product": product.title,
            "size": variant.title,
            "sku": variant.sku,
            "inventory": variant.inventory_quantity,
            "units_sold": int(sold),
            "at_cost": round(variant.inventory_quantity * product.cost, 2),
            "at_retail": round(variant.inventory_quantity * variant.price, 2),
        }

        if sold == 0:
            entry["cover_days"] = None
            not_selling.append(entry)
            continue

        cover = variant.inventory_quantity / rate
        if cover > slow_after_days:
            entry["cover_days"] = int(cover)
            slow.append(entry)

    # Worst first: the most money sitting still for the longest.
    not_selling.sort(key=lambda r: -(r["at_cost"] or r["at_retail"]))
    slow.sort(key=lambda r: -r["cover_days"])

    stuck = not_selling + slow

    return {
        "window_days": window_days,
        "slow_after_days": slow_after_days,
        # Whether the cash figures mean anything. Without cost per item in
        # Shopify they're all zero, and the UI should show retail instead of a
        # confident £0.
        "have_costs": have_costs,
        "stuck_units": sum(r["inventory"] for r in stuck),
        "stuck_at_cost": round(sum(r["at_cost"] for r in stuck), 2),
        "stuck_at_retail": round(sum(r["at_retail"] for r in stuck), 2),
        # The denominator, so the number above has a size to be judged against.
        "total_units": total_units,
        "total_at_cost": round(total_at_cost, 2),
        "total_at_retail": round(total_at_retail, 2),
        "not_selling": not_selling[:10],
        "slow": slow[:10],
        "not_selling_count": len(not_selling),
        "slow_count": len(slow),
    }


def by_size(session: Session, window_days: int = 180) -> list[dict]:
    """
    What sells in each size against what's stocked in each size.

    Clothing's own trap: order flat across a size run when demand is a bell
    curve and the tails pile up. On the demo shop XS is 6% of sales and 16% of
    stock, which is money bought to sit still.
    """
    since = date.today() - timedelta(days=window_days)

    rows = session.exec(
        select(
            Variant.title,
            func.coalesce(func.sum(DailySales.units), 0),
        )
        .join(DailySales, DailySales.variant_id == Variant.id)
        .where(DailySales.day >= since)
        .group_by(Variant.title)
    ).all()
    sold = {size: int(units) for size, units in rows}

    stock_rows = session.exec(
        select(Variant.title, func.sum(Variant.inventory_quantity)).group_by(Variant.title)
    ).all()
    stock = {size: int(units or 0) for size, units in stock_rows}

    total_sold = sum(sold.values()) or 1
    total_stock = sum(stock.values()) or 1

    # Size order, not alphabetical — nobody reads L, M, S, XL, XS.
    order = ["XS", "S", "M", "L", "XL", "XXL", "One Size"]
    sizes = sorted(set(sold) | set(stock), key=lambda s: (order.index(s) if s in order else 99, s))

    return [
        {
            "size": size,
            "sold": sold.get(size, 0),
            "sold_share": round(100 * sold.get(size, 0) / total_sold, 1),
            "stock": stock.get(size, 0),
            "stock_share": round(100 * stock.get(size, 0) / total_stock, 1),
        }
        for size in sizes
    ]


if __name__ == "__main__":
    from app.db import engine

    with Session(engine) as db:
        result = report(db)
        print(
            f"{result['stuck_units']} units stuck "
            f"(£{result['stuck_at_cost']:,.0f} at cost, "
            f"£{result['stuck_at_retail']:,.0f} at retail) "
            f"of {result['total_units']} total"
        )
        print(
            f"  {result['not_selling_count']} not selling at all, "
            f"{result['slow_count']} over {result['slow_after_days']} days of cover\n"
        )

        for row in (result["not_selling"] + result["slow"])[:8]:
            cover = f"{row['cover_days']}d cover" if row["cover_days"] else "no sales"
            print(
                f"  {row['product']:24} {row['size']:3} {row['inventory']:>3} units  "
                f"£{row['at_cost']:>6,.0f}  {cover}"
            )

        print("\nsize mix, sold vs stocked:")
        for row in by_size(db):
            print(
                f"  {row['size']:8} sold {row['sold_share']:>5.1f}%   "
                f"stocked {row['stock_share']:>5.1f}%"
            )
