"""Signed unsubscribe token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

_SEPARATOR = "."


def _signature(secret: str, email: str, timestamp: int) -> str:
    message = f"{email.lower()}:{timestamp}".encode()
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def sign_unsubscribe_token(email: str, secret: str, now: int | None = None) -> str:
    """Return a URL-safe signed token for ``email``."""
    if not secret:
        raise ValueError("unsubscribe secret is required")
    timestamp = int(time.time() if now is None else now)
    sig = _signature(secret, email, timestamp)
    return f"{timestamp}{_SEPARATOR}{sig}"


def verify_unsubscribe_token(
    email: str,
    token: str,
    secret: str,
    max_age_seconds: int,
    now: int | None = None,
) -> bool:
    """Return True when ``token`` is valid for ``email`` and not expired."""
    if not email or not token or not secret or max_age_seconds <= 0:
        return False
    try:
        raw_timestamp, supplied_sig = token.split(_SEPARATOR, 1)
        timestamp = int(raw_timestamp)
    except (ValueError, AttributeError):
        return False

    current = int(time.time() if now is None else now)
    if timestamp > current or current - timestamp > max_age_seconds:
        return False

    expected = _signature(secret, email, timestamp)
    return hmac.compare_digest(supplied_sig, expected)
