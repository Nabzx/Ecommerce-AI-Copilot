"""
Tests for the Lambda that sends the weekly digest.

Worth having precisely because nobody watches a scheduled job. If this breaks
the symptom is an email that silently stops arriving, and the failure would
sit in CloudWatch unread for weeks.

The handler lives outside the api package — it deploys on its own with no
dependencies — so it's loaded by path rather than imported.
"""

import importlib.util
from pathlib import Path

import pytest

HANDLER_PATH = (
    Path(__file__).resolve().parents[2] / "aws" / "digest_scheduler" / "handler.py"
)

spec = importlib.util.spec_from_file_location("digest_handler", HANDLER_PATH)
digest_handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest_handler)


@pytest.fixture
def calls(monkeypatch):
    """Record every POST the handler makes instead of sending it."""
    made: list[dict] = []

    def fake_post(url, payload, token, timeout):
        made.append({"url": url, "payload": payload, "token": token, "timeout": timeout})
        if url.endswith("/api/login"):
            return {"token": "a-signed-token"}
        return {"sent_to": "owner@noszn.example"}

    monkeypatch.setattr(digest_handler, "post_json", fake_post)
    return made


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("STORESENSE_API_URL", "https://storesense.example")
    monkeypatch.setenv("STORESENSE_PASSWORD", "secret")


def test_it_signs_in_then_sends(calls, configured):
    result = digest_handler.handler({}, None)

    assert [c["url"] for c in calls] == [
        "https://storesense.example/api/login",
        "https://storesense.example/api/digest/send",
    ]
    assert result == {"ok": True, "sent_to": "owner@noszn.example"}


def test_the_token_is_carried_to_the_send(calls, configured):
    """The send endpoint is behind auth; forgetting this would 401 weekly."""
    digest_handler.handler({}, None)

    login, send = calls
    assert login["token"] is None
    assert send["token"] == "a-signed-token"


def test_the_password_never_goes_to_the_digest_endpoint(calls, configured):
    digest_handler.handler({}, None)
    assert calls[1]["payload"] in (None, {})


def test_a_trailing_slash_on_the_url_does_not_double_up(calls, monkeypatch):
    """Pasting a URL with a trailing slash into the console is the norm."""
    monkeypatch.setenv("STORESENSE_API_URL", "https://storesense.example/")
    monkeypatch.setenv("STORESENSE_PASSWORD", "secret")

    digest_handler.handler({}, None)

    assert calls[0]["url"] == "https://storesense.example/api/login"


def test_the_first_call_gets_a_long_timeout(calls, configured):
    """
    A free-tier API sleeps between weekly runs, so the sign-in is always the
    one paying for the cold start. Timing it out would look like an outage.
    """
    digest_handler.handler({}, None)
    assert calls[0]["timeout"] >= 60


def test_a_missing_url_fails_loudly(monkeypatch):
    monkeypatch.delenv("STORESENSE_API_URL", raising=False)

    with pytest.raises(digest_handler.DigestError, match="STORESENSE_API_URL"):
        digest_handler.handler({}, None)


def test_a_login_with_no_token_is_an_error_not_a_silent_pass(monkeypatch, configured):
    """A 200 with an empty body would otherwise send an unauthenticated request."""
    monkeypatch.setattr(digest_handler, "post_json", lambda *a, **k: {})

    with pytest.raises(digest_handler.DigestError, match="no token"):
        digest_handler.handler({}, None)


def test_a_wrong_password_surfaces_the_status_code(monkeypatch, configured):
    def refuse(url, payload, token, timeout):
        raise digest_handler.DigestError(f"{url} returned 401: that password isn't right")

    monkeypatch.setattr(digest_handler, "post_json", refuse)

    with pytest.raises(digest_handler.DigestError, match="401"):
        digest_handler.handler({}, None)
