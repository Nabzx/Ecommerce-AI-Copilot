"""
A shared password for the whole dashboard.

One shop, one owner, one password — there are no roles to model and no user
table worth having. What this needs to stop is a stranger who finds the URL
running up an LLM bill, and a shared password does that.

Log in once and you get a signed token that lasts a day. The token carries its
own expiry and a signature, so nothing has to be stored server-side and a
restart doesn't log anyone out (as long as SESSION_SECRET is set).

**Auth is off unless APP_PASSWORD is set.** That keeps a fresh clone working
with zero setup, which is the whole point of the seeder — but it means a
deployment with no password is open to anyone. The app says so loudly at
startup and /health reports it, because "I forgot" is the likely way this goes
wrong.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request

from app.config import settings

# Falls back to a value generated at boot. That works, but every restart
# invalidates existing tokens — fine locally, set SESSION_SECRET in production.
SECRET = (settings.session_secret or secrets.token_hex(32)).encode()

TOKEN_HOURS = 24


def enabled() -> bool:
    return bool(settings.app_password)


def _sign(raw: str) -> str:
    return hmac.new(SECRET, raw.encode(), hashlib.sha256).hexdigest()[:32]


def make_token(hours: int = TOKEN_HOURS) -> str:
    """A signed token that carries its own expiry."""
    payload = json.dumps({"exp": time.time() + hours * 3600})
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{raw}.{_sign(raw)}"


def valid_token(token: str) -> bool:
    """Is this a token we issued, and is it still in date?"""
    if not token or "." not in token:
        return False

    raw, _, signature = token.rpartition(".")

    # compare_digest rather than ==, so the comparison doesn't leak how much
    # of the signature was right via how long it took to fail.
    if not hmac.compare_digest(signature, _sign(raw)):
        return False

    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return float(payload["exp"]) > time.time()
    except (ValueError, KeyError, TypeError):
        return False


def check_password(attempt: str) -> bool:
    """Constant-time comparison, for the same reason as above."""
    return bool(attempt) and hmac.compare_digest(attempt, settings.app_password)


def bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def require_auth(request: Request) -> None:
    """Dependency for anything that shouldn't be open to the internet."""
    if not enabled():
        return
    if not valid_token(bearer_token(request)):
        raise HTTPException(status_code=401, detail="Sign in to use this.")
