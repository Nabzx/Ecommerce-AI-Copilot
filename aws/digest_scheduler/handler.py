"""
The thing that actually makes the Monday digest arrive.

StoreSense has no scheduler inside it on purpose — a web process quietly
emailing on a timer is a surprising thing to find in a service, and every host
already has a better mechanism. This is that mechanism: EventBridge wakes this
function once a week, it signs in, and it asks the API to send the email.

Deliberately no dependencies. urllib is in the standard library, so this
deploys as a single pasted file with no packaging step, no layer and no
requirements to keep in sync with the API's.

Environment:
    STORESENSE_API_URL   https://your-api.onrender.com
    STORESENSE_PASSWORD  the same APP_PASSWORD the API has
"""

import json
import os
import urllib.error
import urllib.request

# Free hosting tiers stop the container when nothing has called it for a
# while, and the first request then has to wait for a cold start. Weekly is
# exactly the cadence that guarantees it's always asleep, so the first attempt
# gets a long timeout rather than being treated as a failure.
WAKE_TIMEOUT = 60
CALL_TIMEOUT = 120


class DigestError(Exception):
    """Something went wrong that CloudWatch should show clearly."""


def post_json(url: str, payload: dict | None, token: str | None, timeout: int) -> dict:
    """One POST. Pulled out so tests can replace it without a network."""
    data = json.dumps(payload or {}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise DigestError(f"{url} returned {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise DigestError(f"could not reach {url}: {exc.reason}") from None


def sign_in(base_url: str, password: str) -> str:
    """Swap the shared password for a token, the same as the dashboard does."""
    reply = post_json(
        f"{base_url}/api/login", {"password": password}, None, timeout=WAKE_TIMEOUT
    )
    token = reply.get("token")
    if not token:
        raise DigestError("signed in but got no token back")
    return token


def send_digest(base_url: str, token: str) -> dict:
    return post_json(f"{base_url}/api/digest/send", None, token, timeout=CALL_TIMEOUT)


def handler(event, context):
    """
    EventBridge calls this. The return value shows up in CloudWatch, so it's
    written to be read by a person at 8am wondering whether the email went.
    """
    base_url = (os.environ.get("STORESENSE_API_URL") or "").rstrip("/")
    password = os.environ.get("STORESENSE_PASSWORD") or ""

    if not base_url:
        raise DigestError("STORESENSE_API_URL is not set")

    token = sign_in(base_url, password)
    result = send_digest(base_url, token)

    sent_to = result.get("sent_to", "unknown")
    print(f"digest sent to {sent_to}")

    return {"ok": True, "sent_to": sent_to}
