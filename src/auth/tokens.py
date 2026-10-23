"""Signed, expiring, purpose-bound tokens (HMAC-SHA256) for one-shot links.

Same scheme as the Codex download token in ``src/api/routers/leads.py``:
``<subject>.<exp_unix>.<base64url(hmac)>``, keyed by a SHA-256 of
``APP_SECRET_KEY`` plus a *purpose* string, so tokens minted for one purpose
(email verification) can never be replayed for another (Codex download, ...).

An optional ``binding`` (e.g. the email address at issue time) is mixed into
the MAC but NOT carried in the token: the verifier must supply the same value,
which ties the token to the state it was issued for.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime

from src.config import get_settings


def _key(purpose: str) -> bytes:
    raw = f"{get_settings().app_secret_key}:{purpose}".encode()
    return hashlib.sha256(raw).digest()


def _mac(purpose: str, subject: str, exp_unix: int, binding: str) -> str:
    msg = f"{subject}.{exp_unix}.{binding}".encode()
    sig = hmac.new(_key(purpose), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def make_signed_token(
    purpose: str, subject: str, expires_at: datetime, *, binding: str = ""
) -> str:
    """Build ``<subject>.<exp>.<sig>``. ``subject`` must not contain dots."""
    if "." in subject:
        raise ValueError("token subject must not contain '.'")
    exp_unix = int(expires_at.timestamp())
    return f"{subject}.{exp_unix}.{_mac(purpose, subject, exp_unix, binding)}"


def parse_token_subject(token: str) -> str | None:
    """Return the subject of a well-formed, unexpired token WITHOUT checking
    the signature (the caller needs the subject to look up the binding)."""
    parts = token.split(".") if token else []
    if len(parts) != 3:
        return None
    subject, exp_str, _sig = parts
    try:
        exp_unix = int(exp_str)
    except ValueError:
        return None
    if not subject or exp_unix < int(datetime.now(UTC).timestamp()):
        return None
    return subject


def verify_signed_token(purpose: str, token: str, *, binding: str = "") -> str | None:
    """Return the subject if ``token`` is well-formed, unexpired and its MAC
    matches ``purpose`` + ``binding``; otherwise None."""
    subject = parse_token_subject(token)
    if subject is None:
        return None
    _subject, exp_str, sig = token.split(".")
    expected = _mac(purpose, subject, int(exp_str), binding)
    if not hmac.compare_digest(expected, sig):
        return None
    return subject
