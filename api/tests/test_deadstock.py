"""
Tests for the dead stock report.

The one that matters is the definition. "Hasn't sold in 60 days" is the
obvious rule and it finds nothing on a shop where everything trickles — so the
report has to catch stock that *is* selling, just far too slowly for how much
of it is sitting there.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import deadstock
from app.models import DailySales, Product, Variant


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_variant(session, *, title, size, inventory, sold_per_day, price=50.0, cost=15.0,
                age_days=400, days=60):
    """A product with one size and a steady sales rate over the window."""
    product = Product(
        title=title,
        handle=title.lower().replace(" ", "-"),
        product_type="tee",
        price=price,
        cost=cost,
        created_at=datetime.now() - timedelta(days=age_days),
    )
    session.add(product)
    session.commit()
    session.refresh(product)

    variant = Variant(
        product_id=product.id, title=size, sku=f"{title}-{size}",
        price=price, inventory_quantity=inventory,
    )
    session.add(variant)
    session.commit()
    session.refresh(variant)

    for offset in range(days):
        session.add(
            DailySales(
                variant_id=variant.id,
                day=date.today() - timedelta(days=offset),
                units=sold_per_day,
            )
        )
    session.commit()
    return variant


def test_stock_that_sells_but_far_too_slowly_is_caught(session):
    """
    The case a "no sales" rule misses entirely: 100 units shifting one a
    fortnight is over three years of stock, and it's the money that hurts.
    """
    add_variant(session, title="Slow Tee", size="XS", inventory=100, sold_per_day=0)
    # 60 units at one a month is 1800 days of cover.
    add_variant(session, title="Trickle Tee", size="XS", inventory=60, sold_per_day=0, days=60)

    result = deadstock.report(session)

    assert result["not_selling_count"] == 2
    assert result["stuck_units"] == 160


def test_healthy_stock_is_left_alone(session):
    """Two a day against 30 units is a fortnight of cover — that's fine."""
    add_variant(session, title="Core Tee", size="M", inventory=30, sold_per_day=2)

    result = deadstock.report(session)

    assert result["slow_count"] == 0
    assert result["not_selling_count"] == 0
    assert result["stuck_units"] == 0


def test_slow_is_measured_in_cover_not_in_units_sold(session):
    """
    Both sell at the same rate. Only one has far too much stock behind it, and
    that's the whole distinction.
    """
    add_variant(session, title="Fine Tee", size="M", inventory=20, sold_per_day=1)
    add_variant(session, title="Overbought Tee", size="XS", inventory=400, sold_per_day=1)

    result = deadstock.report(session)

    stuck = [row["product"] for row in result["slow"]]
    assert stuck == ["Overbought Tee"]


def test_a_new_product_is_not_dead_stock_yet(session):
    """A drop that launched last week hasn't had a chance to sell."""
    add_variant(session, title="New Drop", size="M", inventory=80, sold_per_day=0, age_days=5)

    result = deadstock.report(session)

    assert result["not_selling_count"] == 0
    assert result["slow_count"] == 0


def test_sold_out_sizes_are_not_dead_stock(session):
    """Nothing on the shelf means no money tied up in it."""
    add_variant(session, title="Gone Tee", size="M", inventory=0, sold_per_day=0)
    assert deadstock.report(session)["stuck_units"] == 0


def test_the_cash_is_reported_at_cost_and_at_retail(session):
    add_variant(
        session, title="Slow Tee", size="XS", inventory=10, sold_per_day=0, price=50.0, cost=15.0
    )

    result = deadstock.report(session)

    assert result["stuck_at_cost"] == pytest.approx(150.0)
    assert result["stuck_at_retail"] == pytest.approx(500.0)
    assert result["have_costs"] is True


def test_a_shop_with_no_costs_says_so(session):
    """
    Without cost per item every cash figure is zero, and £0 reads as "this is
    free to hold" rather than "we don't know".
    """
    add_variant(session, title="Slow Tee", size="XS", inventory=10, sold_per_day=0, cost=0.0)

    result = deadstock.report(session)

    assert result["have_costs"] is False
    assert result["stuck_at_cost"] == 0
    assert result["stuck_at_retail"] > 0, "retail is the fallback worth showing"


def test_the_total_is_there_to_judge_the_stuck_figure_against(session):
    add_variant(session, title="Slow Tee", size="XS", inventory=10, sold_per_day=0)
    add_variant(session, title="Core Tee", size="M", inventory=30, sold_per_day=2)

    result = deadstock.report(session)

    assert result["total_units"] == 40
    assert result["stuck_units"] == 10


def test_the_size_mix_compares_share_of_sales_with_share_of_stock(session):
    """The usual cause: a size run bought flat when demand is a bell curve."""
    add_variant(session, title="Tee", size="XS", inventory=50, sold_per_day=0)
    add_variant(session, title="Tee M", size="M", inventory=50, sold_per_day=3)

    mix = {row["size"]: row for row in deadstock.by_size(session)}

    assert mix["XS"]["stock_share"] == pytest.approx(50.0)
    assert mix["XS"]["sold_share"] == pytest.approx(0.0)
    assert mix["M"]["sold_share"] == pytest.approx(100.0)


def test_sizes_come_back_in_wearing_order(session):
    """Alphabetical gives L, M, S, XL, XS, which nobody reads."""
    for size in ["XL", "S", "M", "XS", "L"]:
        add_variant(session, title=f"Tee {size}", size=size, inventory=10, sold_per_day=1)

    order = [row["size"] for row in deadstock.by_size(session)]
    assert order == ["XS", "S", "M", "L", "XL"]
