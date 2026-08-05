"""
StoreSense API.

One FastAPI app in front of the store database and the LLM. The dashboard
talks to nothing else.

    uvicorn app.main:app --reload
"""

from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app import alerts, chat, forecast, metrics, rag, search, sentiment
from app.config import settings
from app.db import create_tables, get_session
from app.llm import LLMError, LLMUnavailable, llm
from app.models import Alert, Product, Review, Variant
from app.ratelimit import rate_limit

app = FastAPI(
    title="StoreSense API",
    description=f"AI commerce dashboard for {settings.store_name}",
    version="0.1.0",
)

# The dashboard runs on its own port in dev, so it needs CORS. The regex covers
# localhost on any port rather than hardcoding 3000, which saves a confusing
# afternoon when something else has already taken it.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # Makes a fresh clone work — tables exist even before the seeder runs.
    create_tables()


@app.get("/health")
async def health() -> dict:
    # Reports whether a model is reachable so the UI can say something useful
    # instead of just failing when someone tries the copilot.
    return {
        "status": "ok",
        "store": settings.store_name,
        "model_available": await llm.available(),
        "model": settings.llm_model,
    }


# --- copilot ---

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat", dependencies=[Depends(rate_limit)])
async def post_chat(body: ChatRequest, session: Session = Depends(get_session)):
    """Streams the answer back as server-sent events."""
    return StreamingResponse(
        chat.stream_reply(session, body.message, body.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx buffering the stream and defeating the whole point.
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/index/rebuild", dependencies=[Depends(rate_limit)])
async def rebuild_index():
    """Re-chunk and re-embed everything. Run after changing the catalogue."""
    return await rag.build_index()


@app.get("/api/search/knowledge", dependencies=[Depends(rate_limit)])
async def search_knowledge(
    q: str = Query(..., min_length=2),
    k: int = Query(4, ge=1, le=10),
    session: Session = Depends(get_session),
):
    """Raw retrieval, handy for checking what the copilot is actually seeing."""
    return await rag.retrieve(session, q, k)


@app.get("/api/search/products", dependencies=[Depends(rate_limit)])
async def search_products(
    q: str = Query(..., min_length=2),
    limit: int = Query(6, ge=1, le=20),
    session: Session = Depends(get_session),
):
    """Natural language catalogue search — "cozy autumn pieces"."""
    return await search.search_products(session, q, limit)


# --- forecasting ---

@app.get("/api/forecast/stockouts")
def get_stockouts(limit: int = Query(10, ge=1, le=60), session: Session = Depends(get_session)):
    """Which sizes run out next, soonest first."""
    try:
        return forecast.stockout_report(session, limit)
    except ValueError as exc:
        # No sales history yet — a fresh clone before the seeder has run.
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/alerts")
def list_alerts(session: Session = Depends(get_session)):
    """Every rule, with whatever it's currently catching."""
    return alerts.check_all(session)


class AlertRequest(BaseModel):
    phrase: str


@app.post("/api/alerts", dependencies=[Depends(rate_limit)])
async def create_alert(body: AlertRequest, session: Session = Depends(get_session)):
    """Turn a sentence into a rule and save it."""
    try:
        rule = await alerts.parse_rule(body.phrase)
    except LLMUnavailable:
        raise HTTPException(
            status_code=503,
            detail="No model is responding, so rules can't be read. Start Ollama with `ollama serve`.",
        )
    except (LLMError, ValueError) as exc:
        # The model answered, it just couldn't be turned into a rule.
        raise HTTPException(status_code=422, detail=str(exc))

    alert = Alert(
        phrase=body.phrase.strip(),
        rule=rule.model_dump_json(),
        created_at=datetime.now(),
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)

    hits = alerts.evaluate(session, rule)
    return {
        "id": alert.id,
        "phrase": alert.phrase,
        "rule": rule.model_dump(),
        "reads_as": alerts.describe(rule),
        "triggered": len(hits) > 0,
        "count": len(hits),
        "hits": hits[:6],
    }


@app.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: int, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="No such alert")
    session.delete(alert)
    session.commit()
    return {"deleted": alert_id}


@app.get("/api/reviews/insights")
def get_review_insights(session: Session = Depends(get_session)):
    """Sentiment split and the recurring themes behind it."""
    return sentiment.insights(session)


@app.post("/api/reviews/analyse", dependencies=[Depends(rate_limit)])
async def analyse_reviews(
    limit: int = Query(60, ge=1, le=500), session: Session = Depends(get_session)
):
    """Classify whatever hasn't been classified yet."""
    try:
        result = await sentiment.analyse(session, limit)
    except LLMUnavailable:
        raise HTTPException(
            status_code=503,
            detail="No model is responding. Start Ollama with `ollama serve`.",
        )
    except (LLMError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"The model's reply couldn't be read: {exc}")

    return {**result, **sentiment.insights(session)}


@app.get("/api/forecast/accuracy")
def get_forecast_accuracy(session: Session = Depends(get_session)):
    """
    How well the forecast actually does against a moving average.

    First call refits across four folds and takes about half a minute, so the
    dashboard asks for this on its own rather than blocking on it.
    """
    try:
        return forecast.backtest(session)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


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
