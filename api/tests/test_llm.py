"""
Tests for the LLM gateway.

All of these use a fake transport, so nothing here touches the network or
needs a model running — the point is to check the retry and error behaviour,
which is exactly the part that's awkward to verify by hand because you'd have
to make a real provider fail on purpose.
"""

import json

import httpx
import pytest

from app.llm import LLMBadRequest, LLMClient, LLMError, LLMUnavailable


def make_client(handler, **kwargs) -> LLMClient:
    """A client wired to a fake transport instead of the internet."""
    return LLMClient(
        base_url="http://fake",
        api_key="test",
        model="test-model",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def chat_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


@pytest.mark.asyncio
async def test_complete_returns_the_content():
    client = make_client(lambda request: chat_response("hello"))
    assert await client.complete([{"role": "user", "content": "hi"}]) == "hello"


@pytest.mark.asyncio
async def test_retries_on_server_error_then_succeeds():
    """A 500 is worth another go — the provider might just be having a moment."""
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(500, text="upstream is sad")
        return chat_response("finally")

    client = make_client(handler, max_retries=2)
    assert await client.complete([{"role": "user", "content": "hi"}]) == "finally"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_gives_up_after_the_retries_are_used():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, text="still down")

    client = make_client(handler, max_retries=1)
    with pytest.raises(LLMUnavailable):
        await client.complete([{"role": "user", "content": "hi"}])

    # One attempt plus one retry, and no more.
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_does_not_retry_a_bad_request():
    """A 400 means we sent something wrong. Sending it again won't help."""
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, text="no such model")

    client = make_client(handler, max_retries=3)
    with pytest.raises(LLMBadRequest):
        await client.complete([{"role": "user", "content": "hi"}])

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_timeout_reads_as_unavailable():
    def handler(request):
        raise httpx.ConnectTimeout("took too long")

    client = make_client(handler, max_retries=0)
    with pytest.raises(LLMUnavailable):
        await client.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_stream_yields_the_pieces_in_order():
    frames = [
        'data: {"choices":[{"delta":{"content":"the "}}]}',
        'data: {"choices":[{"delta":{"content":"boxy "}}]}',
        'data: {"choices":[{"delta":{"content":"tee"}}]}',
        "data: [DONE]",
    ]

    def handler(request):
        return httpx.Response(200, text="\n\n".join(frames))

    client = make_client(handler)
    pieces = [piece async for piece in client.stream([{"role": "user", "content": "hi"}])]
    assert "".join(pieces) == "the boxy tee"


@pytest.mark.asyncio
async def test_stream_ignores_frames_it_cannot_parse():
    """Keepalives and junk shouldn't kill an answer that's already flowing."""
    frames = [
        'data: {"choices":[{"delta":{"content":"one"}}]}',
        "data: not json at all",
        ": a comment keepalive",
        'data: {"choices":[{"delta":{}}]}',
        'data: {"choices":[{"delta":{"content":" two"}}]}',
        "data: [DONE]",
    ]

    def handler(request):
        return httpx.Response(200, text="\n\n".join(frames))

    client = make_client(handler)
    pieces = [piece async for piece in client.stream([{"role": "user", "content": "hi"}])]
    assert "".join(pieces) == "one two"


@pytest.mark.asyncio
async def test_embeddings_come_back_in_the_order_they_went_out():
    """
    Providers don't promise to return embeddings in input order, and getting
    this wrong silently pairs every document with the wrong vector.
    """

    def handler(request):
        payload = json.loads(request.content)
        count = len(payload["input"])
        # Deliberately out of order, with the index saying where each belongs.
        data = [{"index": i, "embedding": [float(i)]} for i in reversed(range(count))]
        return httpx.Response(200, json={"data": data})

    client = make_client(handler)
    vectors = await client.embed(["a", "b", "c"])
    assert vectors == [[0.0], [1.0], [2.0]]


@pytest.mark.asyncio
async def test_a_reply_in_the_wrong_shape_is_an_llm_error():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    client = make_client(handler)
    with pytest.raises(LLMError):
        await client.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_available_is_false_when_nothing_answers():
    def handler(request):
        raise httpx.ConnectError("nothing listening")

    assert await make_client(handler).available() is False
