"""
StoreSense API.

One FastAPI app in front of the store database and the LLM. The dashboard
talks to nothing else.

    uvicorn app.main:app --reload
"""

import json
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app import (
    alerts,
    auth,
    chat,
    copywriter,
    forecast,
    metrics,
    rag,
    search,
    sentiment,
    vision,
    voice,
)
from app.config import settings
from app.db import create_tables, get_session
from app.llm import LLMError, LLMUnavailable, llm
from app.models import Alert, Product, Review, Variant
from app.ratelimit import RateLimiter, rate_limit

app = FastAPI(
    title="StoreSense API",
    description=f"AI commerce dashboard for {settings.store_name}",
    version="0.1.0",
)

# Reachable without signing in: the health check (the dashboard asks it whether
# a password is even needed) and the login endpoint itself.
PUBLIC_PATHS = {"/health", "/api/login", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def require_login(request, call_next):
    """
    One gate in front of everything, rather than a dependency on twenty routes
    — easy to read, and impossible to forget on a route added later.
    """
    if not auth.enabled() or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # CORS preflight carries no headers to check, and blocking it means the
    # browser never sends the real request at all.
    if request.method == "OPTIONS":
        return await call_next(request)

    if not auth.valid_token(auth.bearer_token(request)):
        return JSONResponse(status_code=401, content={"detail": "Sign in to use this."})

    return await call_next(request)


# Added last on purpose, which makes it the outermost middleware.
#
# Starlette applies these in reverse, so whatever is registered last wraps
# everything before it. With CORS registered first, the 401 above was returned
# without any Access-Control-Allow-Origin header — the browser then blocked it
# as a CORS failure, fetch threw, and the dashboard reported "could not reach
# the API" for what was really an expired token. Wrapping the auth check means
# even a rejection comes back with the headers that let the browser read it.
app.add_middleware(
    CORSMiddleware,
    # The regex covers localhost on any port rather than hardcoding 3000, which
    # saves a confusing afternoon when something else has already taken it.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # Makes a fresh clone work — tables exist even before the seeder runs.
    create_tables()

    if not auth.enabled():
        print(
            "\n  StoreSense is running with no password. Fine on your laptop.\n"
            "  Set APP_PASSWORD before putting this anywhere public.\n"
        )


class LoginRequest(BaseModel):
    password: str


# Much tighter than the usual limit — this is the one endpoint where the
# requests are guesses.
login_limiter = RateLimiter(limit=5, window_seconds=60)


@app.post("/api/login")
def login(body: LoginRequest, request: Request):
    """Swap the shared password for a token that lasts a day."""
    caller = request.client.host if request.client else "unknown"
    login_limiter.check(caller)

    if not auth.enabled():
        # Nothing to log into, but answering with a token keeps the frontend
        # from needing a second code path.
        return {"token": auth.make_token(), "auth_required": False}

    if not auth.check_password(body.password):
        raise HTTPException(status_code=401, detail="That password isn't right.")

    return {"token": auth.make_token(), "auth_required": True}


@app.get("/health")
async def health() -> dict:
    # Reports whether a model is reachable, so the UI can say something useful
    # instead of just failing when someone tries the copilot, and whether a
    # password is needed, so it knows to ask for one.
    return {
        "status": "ok",
        "store": settings.store_name,
        "auth_required": auth.enabled(),
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


# --- copy generation ---

def sse_stream(pieces):
    """Wrap a token generator in the same SSE shape the copilot uses."""
    async def generate():
        try:
            async for piece in pieces:
                yield f"data: {json.dumps({'type': 'token', 'text': piece})}\n\n"
        except LLMUnavailable:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No model is responding. Start Ollama with `ollama serve`.'})}\n\n"
        except LLMError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/copy/description/{product_id}", dependencies=[Depends(rate_limit)])
def write_description(product_id: int, session: Session = Depends(get_session)):
    """A product description in noszn's voice, streamed."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="No such product")
    return sse_stream(copywriter.stream_description(session, product))


@app.post("/api/copy/winback", dependencies=[Depends(rate_limit)])
def write_winback(
    days_since: int = Query(60, ge=7, le=365), session: Session = Depends(get_session)
):
    """A win-back email for customers who haven't ordered in a while."""
    return sse_stream(copywriter.stream_winback(session, days_since))


# --- vision tagging ---

@app.post("/api/vision/tag", dependencies=[Depends(rate_limit)])
async def tag_product_image(
    file: UploadFile = File(...), session: Session = Depends(get_session)
):
    """Turn a product photo into tags and a short description."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="That doesn't look like an image.")

    image_bytes = await file.read()
    if len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image is too big — keep it under 8MB.")

    try:
        return await vision.tag_image(session, image_bytes)
    except LLMUnavailable:
        raise HTTPException(
            status_code=503,
            detail=(
                f"No vision model responding. Pull one with "
                f"`ollama pull {settings.llm_vision_model}`."
            ),
        )
    except (LLMError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't read the reply: {exc}")


# --- voice ---

@app.post("/api/voice/transcribe", dependencies=[Depends(rate_limit)])
async def transcribe_audio(file: UploadFile = File(...)):
    """Recorded audio in, text out. The text then goes through /api/chat."""
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty recording.")

    try:
        return await voice.transcribe(audio, file.filename or "audio.webm")
    except voice.NoTranscriber as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not transcribe that: {exc}")


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
