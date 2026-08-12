"""
Tests for the Shopify sync.

There are no credentials to test against, so the whole store is faked with a
mock transport. That's not a lesser substitute here — the things most likely
to be wrong are the mapping and the money, and those are exactly what a fake
store pins down. The first real sync being right matters, because it lands on
someone's actual shop.
"""

import httpx
import pytest

from app import shopify


def test_a_full_name_becomes_a_first_name_and_an_initial():
    assert shopify.anonymise_name("Amara Bennett") == "Amara B."
    assert shopify.anonymise_name("Josh") == "Josh"
    assert shopify.anonymise_name("") == "Customer"
    assert shopify.anonymise_name("  ") == "Customer"


def test_the_same_email_always_hashes_to_the_same_address():
    """
    Repeat-purchase rate depends on a customer keeping one identity across
    syncs. A random fake address each time would make everyone look new.
    """
    first = shopify.anonymise_email("someone@example.com")
    again = shopify.anonymise_email("SOMEONE@example.com  ")

    assert first == again
    assert first.endswith("@customers.invalid")
    assert "someone" not in first


def test_the_next_page_comes_out_of_the_link_header():
    header = (
        '<https://x.myshopify.com/admin/api/2024-10/orders.json?page_info=aaa>; rel="previous", '
        '<https://x.myshopify.com/admin/api/2024-10/orders.json?page_info=bbb>; rel="next"'
    )
    assert shopify.next_page_url(header).endswith("page_info=bbb")


def test_no_next_link_means_the_last_page():
    assert shopify.next_page_url('<https://x/y>; rel="previous"') is None
    assert shopify.next_page_url("") is None


def test_refunded_units_are_counted_per_line():
    order = {
        "refunds": [
            {"refund_line_items": [{"line_item_id": 1, "quantity": 1}]},
            {"refund_line_items": [{"line_item_id": 1, "quantity": 2},
                                   {"line_item_id": 2, "quantity": 1}]},
        ]
    }
    assert shopify.refunded_quantities(order) == {"1": 3, "2": 1}


def test_an_order_with_no_refunds_has_nothing_to_subtract():
    assert shopify.refunded_quantities({"id": 1}) == {}


def test_discounts_come_off_the_line_revenue():
    """A 20% code would otherwise be invisible and inflate every figure."""
    item = {
        "price": "50.00",
        "quantity": 2,
        "discount_allocations": [{"amount": "20.00"}],  # £10 off each
    }
    assert shopify.line_revenue(item, 2) == pytest.approx(80.0)


def test_revenue_is_scaled_when_part_of_a_line_came_back():
    item = {"price": "50.00", "quantity": 2, "discount_allocations": [{"amount": "20.00"}]}
    # One of the two kept: £50 less £10 of discount.
    assert shopify.line_revenue(item, 1) == pytest.approx(40.0)


def test_a_discount_bigger_than_the_price_cannot_go_negative():
    item = {"price": "10.00", "quantity": 1, "discount_allocations": [{"amount": "999"}]}
    assert shopify.line_revenue(item, 1) == 0.0


# --- the whole sync, against a fake shop ---

PRODUCT = {
    "id": 111,
    "title": "Core Hoodie — Black",
    "handle": "core-hoodie-black",
    "product_type": "Hoodie",
    "tags": "hoodie,black",
    "created_at": "2026-01-05T10:00:00+00:00",
    "image": {"src": "https://cdn/hoodie.jpg"},
    "status": "active",
    "body_html": "<p>400gsm loopback.</p><p>cut boxy &amp; short.</p>",
    "variants": [
        {"id": 501, "title": "M", "sku": "H-M", "price": "85.00",
         "inventory_quantity": 4, "inventory_item_id": 901},
        {"id": 502, "title": "L", "sku": "H-L", "price": "85.00",
         "inventory_quantity": 0, "inventory_item_id": 902},
    ],
}

CUSTOMER = {
    "id": 222,
    "first_name": "Amara",
    "last_name": "Bennett",
    "email": "amara@example.com",
    "created_at": "2026-02-01T10:00:00+00:00",
    "default_address": {"country_code": "GB"},
}

# Two units of M ordered, one refunded, with a £10 discount on the line.
ORDER = {
    "id": 333,
    "customer": {"id": 222},
    "created_at": "2026-03-01T12:00:00+00:00",
    "total_price": "170.00",
    "current_total_price": "75.00",
    "financial_status": "partially_refunded",
    "line_items": [
        {"id": 1, "variant_id": 501, "product_id": 111, "quantity": 2,
         "price": "85.00", "discount_allocations": [{"amount": "20.00"}]},
    ],
    "refunds": [{"refund_line_items": [{"line_item_id": 1, "quantity": 1}]}],
}

CANCELLED_ORDER = {
    "id": 444,
    "customer": {"id": 222},
    "created_at": "2026-03-02T12:00:00+00:00",
    "total_price": "85.00",
    "cancelled_at": "2026-03-02T13:00:00+00:00",
    "line_items": [
        {"id": 2, "variant_id": 501, "product_id": 111, "quantity": 1, "price": "85.00"}
    ],
    "refunds": [],
}


def fake_shop(handler_extra=None):
    """A transport that answers like a very small Shopify store."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/products.json"):
            return httpx.Response(200, json={"products": [PRODUCT]})
        if path.endswith("/customers.json"):
            return httpx.Response(200, json={"customers": [CUSTOMER]})
        if path.endswith("/orders.json"):
            return httpx.Response(200, json={"orders": [ORDER, CANCELLED_ORDER]})
        if path.endswith("/inventory_items.json"):
            return httpx.Response(
                200,
                json={"inventory_items": [
                    {"id": 901, "cost": "26.00"},
                    {"id": 902, "cost": "26.00"},
                ]},
            )
        if path.endswith("/shop.json"):
            return httpx.Response(200, json={"shop": {"name": "noszn", "currency": "GBP"}})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler_extra or handler)


@pytest.fixture
def synced(tmp_path, monkeypatch):
    """Run a full sync against the fake store into a throwaway database."""
    from sqlmodel import SQLModel, create_engine

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    SQLModel.metadata.create_all(engine)

    # Point every module that holds the engine at the temporary one.
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr("app.shopify.engine", engine)
    monkeypatch.setattr("app.shopify.create_tables", lambda: None)

    client = shopify.ShopifyClient(
        domain="noszn.myshopify.com", token="test", transport=fake_shop()
    )

    import asyncio

    result = asyncio.run(shopify.sync(history_days=365, client=client))
    return engine, result


def test_the_sync_maps_products_and_variants(synced):
    from sqlmodel import Session, select

    from app.models import Product, Variant

    engine, _ = synced
    with Session(engine) as session:
        product = session.exec(select(Product)).one()
        assert product.title == "Core Hoodie — Black"
        # Shopify's product_type is title-cased; ours is lowercase throughout.
        assert product.product_type == "hoodie"
        assert product.cost == 26.0, "cost has to come off the inventory item"

        variants = session.exec(select(Variant)).all()
        assert {v.title for v in variants} == {"M", "L"}
        assert {v.inventory_quantity for v in variants} == {4, 0}


def test_the_sync_anonymises_customers(synced):
    from sqlmodel import Session, select

    from app.models import Customer

    engine, _ = synced
    with Session(engine) as session:
        customer = session.exec(select(Customer)).one()
        assert customer.name == "Amara B."
        assert "amara@example.com" not in customer.email
        assert customer.email.endswith("@customers.invalid")


def test_cancelled_orders_are_left_out(synced):
    from sqlmodel import Session, select

    from app.models import Order

    engine, _ = synced
    with Session(engine) as session:
        orders = session.exec(select(Order)).all()
        assert len(orders) == 1, "the cancelled order should not be here"
        assert orders[0].shopify_id == "333"


def test_refunded_units_and_discounts_come_off_the_revenue(synced):
    """
    Two hoodies at £85 with £20 off the line, one returned. The shop kept one
    unit at £75 — and that has to match what Shopify itself reports, because
    comparing the two is the first thing anyone does.
    """
    from sqlmodel import Session, select

    from app.models import OrderLine

    engine, _ = synced
    with Session(engine) as session:
        line = session.exec(select(OrderLine)).one()
        assert line.quantity == 1, "the refunded unit should be gone"
        assert line.price == pytest.approx(75.0)
        assert line.quantity * line.price == pytest.approx(75.0)


def test_the_sync_records_that_the_data_is_real(synced):
    from sqlmodel import Session

    from app import datasource

    engine, _ = synced
    with Session(engine) as session:
        state = datasource.current(session)
        assert state["source"] == "shopify"
        assert state["is_demo"] is False
        assert state["store_domain"] == "noszn.myshopify.com"


def test_a_shop_with_no_costs_says_so_rather_than_showing_full_margin(tmp_path, monkeypatch):
    """100% margin on everything is a wrong number that looks like a great one."""
    from sqlmodel import SQLModel, create_engine

    def no_costs(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/inventory_items.json"):
            return httpx.Response(200, json={"inventory_items": []})
        if request.url.path.endswith("/products.json"):
            return httpx.Response(200, json={"products": [PRODUCT]})
        if request.url.path.endswith("/customers.json"):
            return httpx.Response(200, json={"customers": []})
        if request.url.path.endswith("/orders.json"):
            return httpx.Response(200, json={"orders": []})
        return httpx.Response(404, json={})

    engine = create_engine(f"sqlite:///{tmp_path}/nocost.db")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr("app.shopify.engine", engine)
    monkeypatch.setattr("app.shopify.create_tables", lambda: None)

    import asyncio

    client = shopify.ShopifyClient(
        domain="noszn.myshopify.com", token="t", transport=httpx.MockTransport(no_costs)
    )
    result = asyncio.run(shopify.sync(client=client))

    assert result["costs_found"] == 0
    assert "margin" in result["note"].lower()


def test_a_bad_token_is_reported_clearly():
    import asyncio

    def unauthorised(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": "Invalid API key or access token"})

    client = shopify.ShopifyClient(
        domain="noszn.myshopify.com", token="wrong", transport=httpx.MockTransport(unauthorised)
    )

    with pytest.raises(ValueError, match="rejected"):
        asyncio.run(client.shop())


def test_missing_credentials_say_what_to_do(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "shopify_store_domain", "")
    monkeypatch.setattr(settings, "shopify_access_token", "")

    with pytest.raises(ValueError, match="seeder"):
        shopify.ShopifyClient()


def test_html_is_stripped_out_of_the_product_description():
    """Shopify stores descriptions as HTML; the copilot wants the words."""
    assert shopify.strip_html("<p>heavyweight.</p><p>cut boxy &amp; short.</p>") == (
        "heavyweight.\ncut boxy & short."
    )
    assert shopify.strip_html("") == ""
    assert shopify.strip_html("plain text") == "plain text"


def test_the_description_comes_across(synced):
    """It was being dropped on the floor and set to an empty string."""
    from sqlmodel import Session, select

    from app.models import Product

    engine, _ = synced
    with Session(engine) as session:
        product = session.exec(select(Product)).one()
        assert "400gsm loopback" in product.description
        assert "<p>" not in product.description


def test_the_product_status_comes_across(synced):
    from sqlmodel import Session, select

    from app.models import Product

    engine, _ = synced
    with Session(engine) as session:
        assert session.exec(select(Product)).one().status == "active"


def test_an_archived_product_keeps_its_orders_but_leaves_the_stock_reports(tmp_path, monkeypatch):
    """
    The awkward middle case. A discontinued line still earned its revenue, so
    dropping it would understate the past — but it isn't a buying decision any
    more, so it has no business in dead stock or low stock.
    """
    import asyncio

    from sqlmodel import Session, SQLModel, create_engine, select

    from app import deadstock, metrics
    from app.models import Product

    archived = {**PRODUCT, "id": 999, "title": "Last Winter Coat", "status": "archived"}

    def two_products(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/products.json"):
            return httpx.Response(200, json={"products": [PRODUCT, archived]})
        if path.endswith("/customers.json"):
            return httpx.Response(200, json={"customers": [CUSTOMER]})
        if path.endswith("/orders.json"):
            return httpx.Response(200, json={"orders": [ORDER]})
        if path.endswith("/inventory_items.json"):
            return httpx.Response(200, json={"inventory_items": [{"id": 901, "cost": "26.00"}]})
        return httpx.Response(404, json={})

    engine = create_engine(f"sqlite:///{tmp_path}/archived.db")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr("app.shopify.engine", engine)
    monkeypatch.setattr("app.shopify.create_tables", lambda: None)

    client = shopify.ShopifyClient(
        domain="noszn.myshopify.com", token="t", transport=httpx.MockTransport(two_products)
    )
    asyncio.run(shopify.sync(client=client))

    with Session(engine) as session:
        titles = {p.title for p in session.exec(select(Product)).all()}
        assert "Last Winter Coat" in titles, "archived products still have to be stored"

        # But nothing that asks "what should I do about stock" should see it.
        stuck = deadstock.report(session)
        assert all("Winter" not in row["product"] for row in stuck["slow"] + stuck["not_selling"])
        assert all("Winter" not in row["product"] for row in metrics.low_stock(session, 999))
