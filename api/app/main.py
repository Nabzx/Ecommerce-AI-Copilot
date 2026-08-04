"""
StoreSense API.

One FastAPI app in front of the store database and the LLM. The dashboard
talks to nothing else.

    uvicorn app.main:app --reload
"""

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app import metrics
from app.config import settings
from app.db import create_tables, get_session
from app.models import Product, Review, Variant

app = FastAPI(
    title="StoreSense API",
    description=f"AI commerce dashboard for {settings.store_name}",
    version="0.1.0",
)

# The dashboard runs on a different port in dev, so it needs CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # Makes a fresh clone work — tables exist even before the seeder runs.
    create_tables()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "store": settings.store_name}


# --- dashboard numbers ---

@app.get("/api/metrics/summary")
def get_summary(days: int = Query(30, ge=1, le=365), session: Session = Depends(get_session)):
    return metrics.summary(session, days)


@app.get("/api/metrics/revenue-series")
def get_revenue_series(days: int = Query(30, ge=1, le=365), session: Session = Depends(get_session)):
    return metrics.revenue_series(session, days)


@app.get("/api/metrics/top-products")
def get_top_products(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(6, ge=1, le=20),
    session: Session = Depends(get_session),
):
    return metrics.top_products(session, days, limit)


@app.get("/api/metrics/low-stock")
def get_low_stock(threshold: int | None = None, session: Session = Depends(get_session)):
    return metrics.low_stock(session, threshold)


@app.get("/api/metrics/customers")
def get_customers(days: int = Query(30, ge=1, le=365), session: Session = Depends(get_session)):
    return metrics.customer_stats(session, days)


# --- catalogue ---

@app.get("/api/products")
def list_products(session: Session = Depends(get_session)):
    """Every product with its sizes and stock — used by search and the copilot."""
    products = session.exec(select(Product).order_by(Product.title)).all()

    out = []
    for product in products:
        variants = session.exec(select(Variant).where(Variant.product_id == product.id)).all()
        out.append(
            {
                "id": product.id,
                "title": product.title,
                "handle": product.handle,
                "product_type": product.product_type,
                "tags": [t for t in product.tags.split(",") if t],
                "description": product.description,
                "price": product.price,
                "in_stock": sum(v.inventory_quantity for v in variants),
                "variants": [
                    {"id": v.id, "size": v.title, "sku": v.sku, "inventory": v.inventory_quantity}
                    for v in variants
                ],
            }
        )
    return out


@app.get("/api/reviews")
def list_reviews(limit: int = Query(200, ge=1, le=500), session: Session = Depends(get_session)):
    reviews = session.exec(select(Review).order_by(Review.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "product_id": r.product_id,
            "customer": r.customer_name,
            "rating": r.rating,
            "body": r.body,
            "created_at": r.created_at.isoformat(),
            "sentiment": r.sentiment,
            "theme": r.theme,
        }
        for r in reviews
    ]
