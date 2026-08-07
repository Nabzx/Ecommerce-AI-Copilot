"""
Tests for the shared-password login.

Cheap to write and worth having, because the failure mode of getting a token
check wrong is not an error message — it's a dashboard that quietly lets
everyone in.
"""

import time

import pytest

from app import auth
from app.config import settings


@pytest.fixture
def with_password(monkeypatch):
    """Turn auth on for the duration of a test."""
    monkeypatch.setattr(settings, "app_password", "noszn2026")
    return settings.app_password


def test_auth_is_off_until_a_password_is_set(monkeypatch):
    """The zero-setup path: a fresh clone shouldn't ask for anything."""
    monkeypatch.setattr(settings, "app_password", "")
    assert auth.enabled() is False


def test_auth_is_on_once_a_password_is_set(with_password):
    assert auth.enabled() is True


def test_a_fresh_token_is_accepted():
    assert auth.valid_token(auth.make_token()) is True


def test_an_expired_token_is_rejected():
    # Issued as already having run out.
    assert auth.valid_token(auth.make_token(hours=-1)) is False


def test_a_tampered_signature_is_rejected():
    token = auth.make_token()
    raw, _, signature = token.rpartition(".")
    forged = f"{raw}.{'0' * len(signature)}"
    assert auth.valid_token(forged) is False


def test_a_tampered_expiry_is_rejected():
    """
    Someone editing the payload to give themselves a longer session has to
    re-sign it, and they can't without the secret.
    """
    import base64
    import json

    payload = json.dumps({"exp": time.time() + 10_000_000})
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    # Keep the signature from a real token — it won't match the new payload.
    real_signature = auth.make_token().rpartition(".")[2]
    assert auth.valid_token(f"{raw}.{real_signature}") is False


@pytest.mark.parametrize("rubbish", ["", "nonsense", "no-dot-here", ".", "a.b.c"])
def test_malformed_tokens_are_rejected_rather_than_raising(rubbish):
    assert auth.valid_token(rubbish) is False


def test_the_right_password_is_accepted(with_password):
    assert auth.check_password("noszn2026") is True


@pytest.mark.parametrize("wrong", ["", "noszn2025", "noszn2026 ", "NOSZN2026"])
def test_wrong_passwords_are_rejected(with_password, wrong):
    assert auth.check_password(wrong) is False


def test_the_bearer_prefix_is_read_case_insensitively():
    class FakeRequest:
        def __init__(self, value):
            self.headers = {"Authorization": value}

    assert auth.bearer_token(FakeRequest("Bearer abc123")) == "abc123"
    assert auth.bearer_token(FakeRequest("bearer abc123")) == "abc123"
    assert auth.bearer_token(FakeRequest("Basic abc123")) == ""
    assert auth.bearer_token(FakeRequest("")) == ""
