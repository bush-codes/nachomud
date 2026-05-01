"""Email magic-link auth.

Flow:
  1. User enters email on the landing page → POST /auth/request
  2. Server generates a single-use token (15-min expiry), emails the
     user a link of the form `https://nacho.bot/auth/verify?token=...`
  3. User clicks the link → GET /auth/verify
  4. Server consumes the token, ensures an Account exists, sets a
     signed session cookie, redirects to /
  5. WS handler reads the cookie on connect and uses the account's
     player_id (instead of the anon localStorage UUID).

Token store is in-memory; tokens are short-lived so server restart is
acceptable. Email goes out via Fastmail SMTP (`smtplib`) — no SES, no
external SDK. `NACHOMUD_AUTH_DEV_ECHO=1` logs the link to stdout
instead, useful for local dev and tests.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock

from itsdangerous import BadSignature, URLSafeSerializer


log = logging.getLogger("nachomud.auth")


# ── Config ──

TOKEN_TTL_SECONDS = 900            # 15 min
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
SESSION_COOKIE_NAME = "nachomud_session"

SECRET_KEY = os.environ.get("NACHOMUD_SECRET_KEY") or secrets.token_hex(32)

# Fastmail SMTP defaults; override via env.
SMTP_HOST = os.environ.get("NACHOMUD_SMTP_HOST", "smtp.fastmail.com")
SMTP_PORT = int(os.environ.get("NACHOMUD_SMTP_PORT", "465"))
SMTP_USER = os.environ.get("NACHOMUD_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("NACHOMUD_SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("NACHOMUD_MAIL_FROM", "noreply@nacho.bot")

DEV_ECHO_LINKS = bool(os.environ.get("NACHOMUD_AUTH_DEV_ECHO", "")) or \
                  os.environ.get("NACHOMUD_AUTH_BACKEND", "") == "dev"


_serializer = URLSafeSerializer(SECRET_KEY, salt="nachomud-session-v1")


# ── Magic-link token store ──

@dataclass
class _PendingToken:
    email: str
    expires_at: float


@dataclass
class TokenStore:
    """In-memory single-use magic-link tokens. Thread-safe via a Lock."""
    _tokens: dict[str, _PendingToken] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def issue(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = time.time() + TOKEN_TTL_SECONDS
        with self._lock:
            self._tokens[token] = _PendingToken(email=email.strip().lower(),
                                                 expires_at=expires)
            self._gc_locked()
        return token

    def consume(self, token: str) -> str | None:
        if not token:
            return None
        with self._lock:
            entry = self._tokens.pop(token, None)
            self._gc_locked()
        if entry is None:
            return None
        if entry.expires_at < time.time():
            return None
        return entry.email

    def _gc_locked(self) -> None:
        now = time.time()
        stale = [k for k, v in self._tokens.items() if v.expires_at < now]
        for k in stale:
            self._tokens.pop(k, None)


_token_store = TokenStore()


def issue_token(email: str) -> str:
    return _token_store.issue(email)


def consume_token(token: str) -> str | None:
    return _token_store.consume(token)


# ── Session cookie ──

def make_session_cookie(email: str) -> str:
    payload = {"email": email.strip().lower(), "issued_at": int(time.time())}
    return _serializer.dumps(payload)


def read_session_cookie(cookie_value: str) -> str | None:
    if not cookie_value:
        return None
    try:
        payload = _serializer.loads(cookie_value)
    except BadSignature:
        return None
    if not isinstance(payload, dict):
        return None
    issued = int(payload.get("issued_at", 0))
    if issued + SESSION_TTL_SECONDS < time.time():
        return None
    email = payload.get("email")
    return email if isinstance(email, str) and email else None


# ── Email sending (Fastmail SMTP) ──

def _verify_link_html(link: str) -> str:
    return f"""\
<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:560px;margin:24px auto">
  <h2 style="color:#5dd">Sign in to NachoMUD</h2>
  <p>Click the button below to sign in. The link is valid for 15 minutes.</p>
  <p><a href="{link}" style="display:inline-block;background:#5dd;color:#0a0a0a;
     padding:10px 18px;border-radius:4px;text-decoration:none;font-weight:600">
     Sign in to NachoMUD</a></p>
  <p style="color:#888;font-size:12px">If the button doesn't work, paste this
     URL into your browser:<br><code>{link}</code></p>
  <p style="color:#888;font-size:12px">If you didn't request this, ignore the
     email — no account is created until you click.</p>
</body></html>
"""


def _verify_link_text(link: str) -> str:
    return (
        "Sign in to NachoMUD\n\n"
        f"Click this link to sign in (valid 15 minutes):\n{link}\n\n"
        "If you didn't request this, ignore the email — no account is "
        "created until you click."
    )


def send_magic_link(email: str, link: str) -> None:
    """Email `link` to `email` via SMTP (Fastmail by default). In dev
    mode, log the link to stdout instead so the developer can click it
    from the terminal."""
    if DEV_ECHO_LINKS:
        log.warning("[DEV] magic link for %s -> %s", email, link)
        return
    if not SMTP_USER or not SMTP_PASSWORD:
        log.error("SMTP credentials not configured — set NACHOMUD_SMTP_USER "
                  "and NACHOMUD_SMTP_PASSWORD. Falling back to dev-echo.")
        log.warning("[DEV-FALLBACK] magic link for %s -> %s", email, link)
        return

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "Sign in to NachoMUD"
    msg["From"] = MAIL_FROM
    msg["To"] = email
    msg.set_content(_verify_link_text(link))
    msg.add_alternative(_verify_link_html(link), subtype="html")

    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
