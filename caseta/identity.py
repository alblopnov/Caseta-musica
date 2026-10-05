"""Per-phone identity cookie and PIN-based admin authentication."""
from __future__ import annotations

import hmac
import re
import threading
import time
import uuid
from typing import Callable, Literal

from flask import Flask, g, request, session

CLIENT_COOKIE = "caseta_client"
CLIENT_COOKIE_MAX_AGE = 365 * 24 * 3600
_CLIENT_ID_RE = re.compile(r"[0-9a-f]{32}")
_PRUNE_THRESHOLD = 1024


def init_identity(app: Flask) -> None:
    """Give every visitor a stable anonymous id in ``g.client_id``."""

    @app.before_request
    def _assign_client_id() -> None:
        cookie = request.cookies.get(CLIENT_COOKIE, "")
        if _CLIENT_ID_RE.fullmatch(cookie):
            g.client_id = cookie
            g.client_id_is_new = False
        else:
            g.client_id = uuid.uuid4().hex
            g.client_id_is_new = True

    @app.after_request
    def _persist_client_id(response):
        if g.get("client_id_is_new"):
            response.set_cookie(
                CLIENT_COOKIE,
                g.client_id,
                max_age=CLIENT_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
            )
        return response


def _encode(pin: str) -> bytes:
    # surrogatepass: a lone surrogate (e.g. from JSON "\ud800") must not raise.
    return pin.encode("utf-8", errors="surrogatepass")


AttemptResult =Literal["ok", "bad", "locked", "disabled"]


class AdminAuth:
    """Checks the admin PIN, locking out a caller after repeated failures."""

    def __init__(
        self,
        pin: str | None,
        max_failures: int = 5,
        lockout_seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pin = _encode(pin) if pin else None
        self._max_failures = max_failures
        self._lockout_seconds = lockout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def __repr__(self) -> str:
        return f"<AdminAuth enabled={self._pin is not None}>"

    def attempt(self, pin: str, key: str) -> AttemptResult:
        if self._pin is None:
            return "disabled"
        with self._lock:
            now = self._clock()
            if len(self._locked_until) > _PRUNE_THRESHOLD:
                self._prune(now)
            locked_until = self._locked_until.get(key)
            if locked_until is not None:
                if now < locked_until:
                    return "locked"
                del self._locked_until[key]
                self._failures.pop(key, None)
            if isinstance(pin, str) and hmac.compare_digest(_encode(pin), self._pin):
                self._failures.pop(key, None)
                return "ok"
            failures = self._failures.get(key, 0) + 1
            if failures >= self._max_failures:
                self._failures.pop(key, None)
                self._locked_until[key] = now + self._lockout_seconds
            else:
                self._failures[key] = failures
            return "bad"

    def _prune(self, now: float) -> None:
        for key in [k for k, until in self._locked_until.items() if now >= until]:
            del self._locked_until[key]


def is_admin() -> bool:
    return session.get("admin") is True


def set_admin(on: bool) -> None:
    if on:
        session["admin"] = True
    else:
        session.pop("admin", None)
