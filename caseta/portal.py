"""Captive-portal redirect: unknown Host headers are sent to the jukebox page."""
from __future__ import annotations

from flask import Flask, redirect, request

from caseta.config import Config


def _hostname(raw: str) -> str:
    """Lowercased host without its port; bracketed IPv6 literals keep their brackets."""
    host = raw.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    return host.rpartition(":")[0] if ":" in host else host


def init_portal(app: Flask, config: Config) -> None:
    """Answer 302 to ``config.portal_url`` for any request whose Host is not ours.

    Phones probe hosts like ``connectivitycheck.gstatic.com``; the redirect makes the
    OS offer "sign in to network" and open the app. Register this before identity so
    redirected requests never get a client cookie.
    """
    allowed = frozenset(h.lower() for h in config.allowed_hosts)
    portal_url = config.portal_url

    @app.before_request
    def _redirect_unknown_host():
        try:
            raw = request.host
        except Exception:  # a malformed Host header must redirect, not 500
            raw = ""
        if _hostname(raw).rstrip(".") not in allowed:
            return redirect(portal_url, code=302)
        return None
