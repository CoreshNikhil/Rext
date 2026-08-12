"""Rate limiting via slowapi.

`limiter` is the shared instance, keyed by client IP (`get_remote_address`)
by default — used directly for the plain per-IP limits (login, mock-confirm).

`mobile_number_key` is a second key function used only on the OTP-request
endpoints, which additionally need a per-mobile-number limit so a single
phone number can't be hammered from many different IPs. slowapi calls
key functions synchronously with just the `Request`, so it can't `await
request.json()` itself — instead it reads `request._body`, the raw bytes
Starlette already cached the first time the body was read. That earlier
read is guaranteed to have happened: FastAPI resolves the endpoint's
Pydantic body parameter (which requires reading the body) before invoking
the endpoint callable slowapi wraps, so by the time this key_func runs the
bytes are already sitting in `request._body`, and reading them here doesn't
re-consume the request stream.
"""

from __future__ import annotations

import json

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def mobile_number_key(request: Request) -> str:
    body = getattr(request, "_body", b"") or b""
    try:
        mobile_number = json.loads(body).get("mobile_number")
    except (ValueError, AttributeError):
        mobile_number = None
    return f"mobile:{mobile_number}" if mobile_number else f"ip:{get_remote_address(request)}"
