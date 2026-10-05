import re

import pytest
from flask import Flask, g

from caseta.identity import CLIENT_COOKIE, AdminAuth, init_identity, is_admin, set_admin

ID_RE = r"[0-9a-f]{32}"


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    init_identity(app)

    @app.get("/_whoami")
    def whoami():
        return g.client_id

    @app.get("/_set_admin/<int:on>")
    def _set_admin(on):
        set_admin(bool(on))
        return "ok"

    @app.get("/_is_admin")
    def _is_admin():
        return "yes" if is_admin() else "no"

    return app


@pytest.fixture
def app_client(app):
    return app.test_client()


def _set_cookie_headers(response):
    return response.headers.getlist("Set-Cookie")


def test_new_visitor_gets_cookie_and_keeps_it(app_client):
    r1 = app_client.get("/_whoami")
    r2 = app_client.get("/_whoami")
    assert re.fullmatch(ID_RE, r1.text) and r1.text == r2.text
    assert "caseta_client=" in r1.headers["Set-Cookie"] and "HttpOnly" in r1.headers["Set-Cookie"]


def test_cookie_name_constant():
    assert CLIENT_COOKIE == "caseta_client"


def test_cookie_attributes(app_client):
    r = app_client.get("/_whoami")
    header = next(h for h in _set_cookie_headers(r) if h.startswith("caseta_client="))
    assert header.startswith(f"caseta_client={r.text};")
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header
    assert f"Max-Age={365 * 24 * 3600}" in header


def test_cookie_not_resent_when_valid(app_client):
    app_client.get("/_whoami")
    r2 = app_client.get("/_whoami")
    assert not any(h.startswith("caseta_client=") for h in _set_cookie_headers(r2))


def test_valid_cookie_is_adopted_and_not_resent(app):
    c = app.test_client()
    mine = "ab" * 16
    c.set_cookie(CLIENT_COOKIE, mine)
    r = c.get("/_whoami")
    assert r.text == mine
    assert not any(h.startswith("caseta_client=") for h in _set_cookie_headers(r))


@pytest.mark.parametrize("bad", ["../../x", "", "AB" * 16, "ab" * 15, "ab" * 17, "g" * 32, "ab" * 16 + "\n"])
def test_garbage_cookie_is_replaced(app, bad):
    c = app.test_client()
    c.set_cookie(CLIENT_COOKIE, bad)
    r = c.get("/_whoami")
    assert re.fullmatch(ID_RE, r.text) and r.text != bad
    assert any(h.startswith("caseta_client=") for h in _set_cookie_headers(r))


def test_two_clients_get_different_ids(app):
    a, b = app.test_client(), app.test_client()
    ida, idb = a.get("/_whoami").text, b.get("/_whoami").text
    assert re.fullmatch(ID_RE, ida) and re.fullmatch(ID_RE, idb)
    assert ida != idb


def test_fresh_client_is_not_admin(app_client):
    assert app_client.get("/_is_admin").text == "no"


def test_set_admin_true_then_false(app_client):
    app_client.get("/_set_admin/1")
    assert app_client.get("/_is_admin").text == "yes"
    app_client.get("/_set_admin/0")
    assert app_client.get("/_is_admin").text == "no"


def test_admin_is_per_client(app):
    a, b = app.test_client(), app.test_client()
    a.get("/_set_admin/1")
    assert a.get("/_is_admin").text == "yes"
    assert b.get("/_is_admin").text == "no"


def test_is_admin_requires_exactly_true(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["admin"] = "yes"
    assert c.get("/_is_admin").text == "no"


def test_admin_auth_ok_bad_disabled():
    a = AdminAuth("1234")
    assert a.attempt("1234", "ip") == "ok" and a.attempt("0000", "ip") == "bad"
    assert AdminAuth(None).attempt("1234", "ip") == "disabled"


def test_admin_auth_empty_pin_is_disabled():
    assert AdminAuth("").attempt("", "ip") == "disabled"


def test_admin_auth_non_ascii_pin_attempt_is_bad_not_error():
    a = AdminAuth("1234")
    assert a.attempt("12é4", "ip") == "bad"
    assert a.attempt("🎵", "ip") == "bad"


def test_admin_auth_non_ascii_configured_pin_works():
    a = AdminAuth("pín-ñ")
    assert a.attempt("pín-ñ", "ip") == "ok"
    assert a.attempt("pin-n", "ip") == "bad"


def test_admin_auth_locks_out_then_recovers():
    t = [0.0]
    a = AdminAuth("1234", max_failures=5, lockout_seconds=60, clock=lambda: t[0])
    for _ in range(5):
        a.attempt("x", "ip")
    assert a.attempt("1234", "ip") == "locked"
    assert a.attempt("1234", "other-ip") == "ok"
    t[0] = 61
    assert a.attempt("1234", "ip") == "ok"


def test_admin_auth_lockout_boundary_and_not_extended_while_locked():
    t = [0.0]
    a = AdminAuth("1234", max_failures=3, lockout_seconds=60, clock=lambda: t[0])
    for _ in range(3):
        assert a.attempt("x", "ip") == "bad"
    t[0] = 30
    assert a.attempt("x", "ip") == "locked"  # does not count nor extend
    assert a.attempt("1234", "ip") == "locked"
    t[0] = 60
    assert a.attempt("1234", "ip") == "ok"  # expired exactly lockout_seconds after the lock


def test_admin_auth_success_resets_failure_count():
    a = AdminAuth("1234", max_failures=3)
    a.attempt("x", "ip")
    a.attempt("x", "ip")
    assert a.attempt("1234", "ip") == "ok"
    assert a.attempt("x", "ip") == "bad"
    assert a.attempt("x", "ip") == "bad"
    assert a.attempt("1234", "ip") == "ok"  # only 2 fresh failures, not locked


def test_admin_auth_failures_after_lockout_expiry_start_fresh():
    t = [0.0]
    a = AdminAuth("1234", max_failures=2, lockout_seconds=10, clock=lambda: t[0])
    a.attempt("x", "ip")
    a.attempt("x", "ip")
    t[0] = 11
    assert a.attempt("x", "ip") == "bad"  # one failure, not instantly relocked
    assert a.attempt("1234", "ip") == "ok"


def test_admin_auth_lockout_is_per_key():
    a = AdminAuth("1234", max_failures=2)
    a.attempt("x", "a")
    a.attempt("x", "a")
    assert a.attempt("1234", "a") == "locked"
    assert a.attempt("x", "b") == "bad"
    assert a.attempt("1234", "b") == "ok"


def test_admin_auth_does_not_expose_pin():
    a = AdminAuth("s3cr3t-pin")
    assert "s3cr3t-pin" not in repr(a) and "s3cr3t-pin" not in str(a)
