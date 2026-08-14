"""
Tests for token counting and cost.

The gateway tests use a fake transport, so these can check that a call is
actually recorded end to end without a model running — which matters, because
a cost figure that silently stops updating is worse than no cost figure.
"""

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import pricing
from app.llm import LLMClient
from app.models import Usage

# --- pricing ---


def test_a_local_model_is_free_but_still_counted():
    """The tokens are real even when the bill is zero."""
    assert pricing.cost_gbp("llama3.1:latest", 10_000, 5_000) == 0.0
    assert pricing.is_local("llama3.1:latest") is True
    assert pricing.known_price("llama3.1:latest") is True


def test_a_paid_model_is_priced_per_million_tokens():
    # gpt-4o-mini: £0.12 in, £0.47 out per million.
    cost = pricing.cost_gbp("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.59, abs=0.01)


def test_input_and_output_are_priced_differently():
    """Output costs several times more, and a flat rate would understate."""
    input_only = pricing.cost_gbp("gpt-4o-mini", 1_000_000, 0)
    output_only = pricing.cost_gbp("gpt-4o-mini", 0, 1_000_000)
    assert output_only > input_only * 3


def test_a_dated_model_name_prices_as_its_family():
    """Providers append release dates; the price table shouldn't need updating."""
    assert pricing.cost_gbp("gpt-4o-mini-2024-07-18", 1_000_000, 0) == pricing.cost_gbp(
        "gpt-4o-mini", 1_000_000, 0
    )


def test_an_unknown_model_reports_zero_but_admits_it():
    """
    Guessing a price would be worse than showing nothing — but the total has
    to be able to say it's incomplete, which is what `known_price` is for.
    """
    assert pricing.cost_gbp("some-new-model", 1_000_000, 1_000_000) == 0.0
    assert pricing.known_price("some-new-model") is False


# --- recording through the gateway ---


@pytest.fixture
def recorder():
    """Collects what the gateway reports, standing in for the DB writer."""
    calls: list[dict] = []

    def record(**kwargs):
        calls.append(kwargs)

    return calls, record


@pytest.mark.asyncio
async def test_a_completion_reports_its_tokens(recorder):
    calls, record = recorder

    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 5},
            },
        )

    client = LLMClient(base_url="http://fake", model="gpt-4o-mini",
                       transport=httpx.MockTransport(handler))
    client.on_usage = record

    await client.complete([{"role": "user", "content": "hi"}], label="alerts")

    assert calls == [
        {"endpoint": "alerts", "model": "gpt-4o-mini", "prompt_tokens": 11,
         "completion_tokens": 5, "streamed": False}
    ]


@pytest.mark.asyncio
async def test_a_stream_reports_the_usage_chunk_at_the_end(recorder):
    """
    The one that's easy to miss. Providers send usage in a final chunk with an
    empty choices list — the shape that a naive parser skips as malformed.
    """
    calls, record = recorder
    frames = [
        'data: {"choices":[{"delta":{"content":"the "}}]}',
        'data: {"choices":[{"delta":{"content":"tee"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":40,"completion_tokens":12}}',
        "data: [DONE]",
    ]

    def handler(request):
        return httpx.Response(200, text="\n\n".join(frames))

    client = LLMClient(base_url="http://fake", model="llama3.1",
                       transport=httpx.MockTransport(handler))
    client.on_usage = record

    pieces = [p async for p in client.stream([{"role": "user", "content": "hi"}], label="copilot")]

    assert "".join(pieces) == "the tee", "the usage chunk must not break the text"
    assert calls[0]["prompt_tokens"] == 40
    assert calls[0]["completion_tokens"] == 12
    assert calls[0]["streamed"] is True


@pytest.mark.asyncio
async def test_a_reply_with_no_usage_records_nothing(recorder):
    """Better a missing row than a row of zeroes that looks like a free call."""
    calls, record = recorder

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    client = LLMClient(base_url="http://fake", transport=httpx.MockTransport(handler))
    client.on_usage = record

    await client.complete([{"role": "user", "content": "hi"}])
    assert calls == []


@pytest.mark.asyncio
async def test_a_broken_recorder_cannot_break_the_call():
    """Accounting must never take down the thing it was measuring."""

    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "still fine"}}],
                  "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
        )

    client = LLMClient(base_url="http://fake", transport=httpx.MockTransport(handler))

    def explode(**kwargs):
        raise RuntimeError("the database is on fire")

    client.on_usage = explode

    assert await client.complete([{"role": "user", "content": "hi"}]) == "still fine"


# --- the rollup ---


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_usage(session, endpoint, model, prompt, completion, priced=True):
    from datetime import datetime

    session.add(
        Usage(
            endpoint=endpoint,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            cost_gbp=pricing.cost_gbp(model, prompt, completion),
            priced=priced,
            created_at=datetime.now(),
        )
    )
    session.commit()


def test_the_rollup_breaks_spend_down_by_feature(session):
    """One total tells you nothing; the split tells you where to look."""
    from app import usage

    add_usage(session, "copilot", "gpt-4o-mini", 100_000, 50_000)
    add_usage(session, "copilot", "gpt-4o-mini", 100_000, 50_000)
    add_usage(session, "sentiment", "gpt-4o-mini", 1_000, 500)

    report = usage.summary(session)

    assert report["calls"] == 3
    assert report["tokens"] == 301_500
    assert report["by_endpoint"][0]["endpoint"] == "copilot", "biggest first"
    assert report["by_endpoint"][0]["calls"] == 2
    assert report["cost_gbp"] > 0


def test_the_rollup_flags_calls_it_could_not_price(session):
    from app import usage

    add_usage(session, "copilot", "mystery-model", 1_000, 500, priced=False)

    assert usage.summary(session)["unpriced_calls"] == 1


def test_an_empty_window_is_zeroes_rather_than_an_error(session):
    from app import usage

    report = usage.summary(session)
    assert report["calls"] == 0
    assert report["cost_gbp"] == 0
    assert report["by_endpoint"] == []


def test_nothing_is_written_when_no_recorder_is_attached(session):
    """Scripts and tests use the gateway untracked, and that has to stay true."""
    assert session.exec(select(Usage)).all() == []
