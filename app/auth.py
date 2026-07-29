from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Request

COOKIE_NAME = "ppd_session"
SESSION_SECONDS = 8 * 60 * 60


@dataclass(slots=True)
class SessionData:
    username: str
    csrf: str
    expires_at: int


def verify_password(provided: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(provided.encode(), expected.encode())


def create_session(username: str, secret: str) -> str:
    payload = {
        "u": username,
        "c": secrets.token_urlsafe(24),
        "e": int(time.time()) + SESSION_SECONDS,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_session(request: Request, secret: str) -> SessionData | None:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        body, signature = token.rsplit(".", 1)
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw)
        expires = int(payload["e"])
        if expires < int(time.time()):
            return None
        return SessionData(username=str(payload["u"]), csrf=str(payload["c"]), expires_at=expires)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def require_csrf(request: Request, session: SessionData) -> bool:
    supplied = request.headers.get("X-CSRF-Token", "")
    return bool(supplied) and hmac.compare_digest(supplied, session.csrf)
