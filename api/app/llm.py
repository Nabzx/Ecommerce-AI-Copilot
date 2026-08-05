"""
The LLM gateway.

Every call to a model in StoreSense goes through this file — chat, streaming,
embeddings and vision. Nothing else in the codebase talks to a provider
directly, so timeouts, retries and error handling only had to be written once.

It speaks the OpenAI chat-completions shape, which means it works with OpenAI,
Together, Groq, vLLM or anything else that copies that API. The default points
at a local Ollama, so the project runs for free with no account anywhere.
"""

import asyncio
import base64
import json
from typing import AsyncIterator

import httpx

from app.config import settings


class LLMError(Exception):
    """Base class so callers can catch everything from here in one except."""


class LLMUnavailable(LLMError):
    """Couldn't reach a model at all — nothing running, or the wrong URL."""


class LLMBadRequest(LLMError):
    """The provider rejected the request. Retrying wouldn't help."""


# 5xx and 429 are worth another go; 4xx means we sent something wrong.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    """A thin wrapper over one OpenAI-compatible endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        # Tests pass a fake transport in here so they never touch the network.
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        """POST with retries and a backoff, for the non-streaming calls."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with self._client() as client:
                    response = await client.post(path, json=payload, timeout=timeout or self.timeout)

                if response.status_code in RETRYABLE_STATUS:
                    last_error = LLMUnavailable(
                        f"provider returned {response.status_code}"
                    )
                elif response.status_code >= 400:
                    # Our fault — a bad model name or a malformed body. Stop.
                    raise LLMBadRequest(
                        f"provider returned {response.status_code}: {response.text[:200]}"
                    )
                else:
                    return response.json()

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = LLMUnavailable(f"could not reach the model: {exc}")

            # Wait a bit longer each time: 0.5s, then 1s, then 2s.
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))

        raise last_error or LLMUnavailable("the model did not respond")

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """
        Ask for a whole answer in one go.

        `timeout` overrides the default for calls that are legitimately slow —
        classifying a batch of reviews on a local model takes far longer than
        answering a question, and killing it at 60 seconds isn't a failure
        worth retrying.
        """
        payload: dict = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        data = await self._post("/chat/completions", payload, timeout=timeout)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected response shape from the provider: {exc}")

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        """
        Yield the answer a piece at a time.

        Retries only cover opening the connection. Once tokens have started
        arriving we can't quietly start again — the user has already read the
        first half of a sentence — so a failure mid-stream is passed up and the
        UI shows what it got plus a warning.
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            started = False
            try:
                async with self._client() as client:
                    async with client.stream("POST", "/chat/completions", json=payload) as response:
                        if response.status_code >= 400:
                            body = (await response.aread()).decode()[:200]
                            if response.status_code in RETRYABLE_STATUS:
                                last_error = LLMUnavailable(
                                    f"provider returned {response.status_code}"
                                )
                                raise _Retry()
                            raise LLMBadRequest(
                                f"provider returned {response.status_code}: {body}"
                            )

                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return

                            try:
                                chunk = json.loads(data)
                                piece = chunk["choices"][0]["delta"].get("content")
                            except (json.JSONDecodeError, KeyError, IndexError):
                                # A keepalive or a shape we don't recognise.
                                continue

                            if piece:
                                started = True
                                yield piece
                        return

            except _Retry:
                pass
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if started:
                    raise LLMError(f"the model stopped part-way through: {exc}")
                last_error = LLMUnavailable(f"could not reach the model: {exc}")

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))

        raise last_error or LLMUnavailable("the model did not respond")

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Turn text into vectors for search and RAG."""
        data = await self._post(
            "/embeddings",
            {"model": model or settings.llm_embed_model, "input": texts},
        )
        try:
            # Providers don't promise input order back, so sort by index.
            rows = sorted(data["data"], key=lambda row: row["index"])
            return [row["embedding"] for row in rows]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"unexpected embeddings response: {exc}")

    async def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        """
        Send an image to a vision model.

        Images go over as base64 data URLs, which is what the OpenAI vision
        format expects and what Ollama accepts too.
        """
        encoded = base64.b64encode(image_bytes).decode()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    },
                ],
            }
        ]
        return await self.complete(messages, model=settings.llm_vision_model, temperature=0.2)

    async def available(self) -> bool:
        """Is there actually a model to talk to? Used by /health."""
        try:
            async with self._client() as client:
                response = await client.get("/models", timeout=3.0)
            return response.status_code < 400
        except (httpx.TimeoutException, httpx.TransportError):
            return False


class _Retry(Exception):
    """Internal signal to jump to the next attempt inside the stream loop."""


# One shared client for the app.
llm = LLMClient()
