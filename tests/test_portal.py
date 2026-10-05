from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "host",
    ["connectivitycheck.gstatic.com", "captive.apple.com", "www.msftconnecttest.com", "example.org:80"],
)
def test_unknown_host_is_redirected_to_portal(app, host):
    r = app.test_client().get("/generate_204", headers={"Host": host})
    assert r.status_code == 302 and r.headers["Location"] == "http://10.42.0.1/"
    assert "Set-Cookie" not in r.headers


@pytest.mark.parametrize("host", ["localhost", "localhost:5000", "10.42.0.1", "CASETA.LOCAL"])
def test_known_hosts_are_served(app, host):
    assert app.test_client().get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("method", ["get", "post", "head", "put", "delete"])
@pytest.mark.parametrize("path", ["/", "/api/state", "/api/queue", "/generate_204", "/static/x.js"])
def test_any_path_and_method_from_unknown_host_redirects(app, method, path):
    r = getattr(app.test_client(), method)(path, headers={"Host": "captive.apple.com"})
    assert r.status_code == 302 and r.headers["Location"] == "http://10.42.0.1/"
    assert "Set-Cookie" not in r.headers


def test_api_state_from_unknown_host_never_leaks_state(app):
    r = app.test_client().get("/api/state", headers={"Host": "evil.example"})
    assert r.status_code == 302
    assert r.headers["Location"] == "http://10.42.0.1/"


@pytest.mark.parametrize(
    "host",
    ["[", "", pytest.param("x" * 5000, id="very-long"), "[::1]", "[::1]:5000", ":80", "a b", "caseta.local.evil.com"],
)
def test_weird_host_headers_redirect_without_error(app, host):
    r = app.test_client().get("/api/state", headers={"Host": host})
    assert r.status_code == 302
    assert r.headers["Location"] == "http://10.42.0.1/"
    assert "Set-Cookie" not in r.headers


def test_known_host_still_gets_identity_cookie(app):
    r = app.test_client().get("/api/state", headers={"Host": "localhost"})
    assert r.status_code == 200
    assert "caseta_client=" in r.headers.get("Set-Cookie", "")


def test_entry_point_never_enables_debug():
    assert "debug=True" not in (ROOT / "app.py").read_text(encoding="utf-8")


# -- entry point ------------------------------------------------------------


@pytest.fixture
def entry(monkeypatch, tmp_path, player):
    """The app module with waitress and pygame replaced, plus a record of serve() calls."""
    import app as entry_module
    import caseta

    for name in ("CASETA_ADMIN_PIN", "CASETA_PORT", "CASETA_MAX_PENDING", "CASETA_MAX_UPLOAD_MB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CASETA_SONG_DIR", str(tmp_path / "songs"))

    real_create_app = caseta.create_app
    calls = {}
    monkeypatch.setattr(
        entry_module, "create_app", lambda config=None: real_create_app(config, player=player)
    )

    def fake_serve(wsgi_app, **kwargs):
        calls["app"] = wsgi_app
        calls["kwargs"] = kwargs
        calls["engine_alive"] = wsgi_app.extensions["engine"]._thread.is_alive()

    monkeypatch.setattr(entry_module.waitress, "serve", fake_serve)
    return entry_module, calls


def test_main_serves_with_waitress_on_all_interfaces(entry, monkeypatch):
    module, calls = entry
    module.main()
    assert calls["kwargs"] == {"host": "0.0.0.0", "port": 5000, "threads": 8}
    assert calls["engine_alive"] is True


def test_main_honours_port_env(entry, monkeypatch):
    module, calls = entry
    monkeypatch.setenv("CASETA_PORT", "8081")
    module.main()
    assert calls["kwargs"]["port"] == 8081


def test_main_stops_engine_and_music_on_shutdown(entry, monkeypatch, player, songs):
    module, calls = entry

    def serve_and_play(wsgi_app, **kwargs):
        calls["app"] = wsgi_app
        wsgi_app.extensions["engine"].enqueue("a1.wav", "A")
        wsgi_app.extensions["engine"].tick()
        assert player.playing is True

    monkeypatch.setattr(module.waitress, "serve", serve_and_play)
    module.main()
    assert calls["app"].extensions["engine"]._thread is None
    assert player.playing is False


def test_main_stops_engine_even_if_serve_raises(entry, monkeypatch):
    module, calls = entry

    def boom(wsgi_app, **kwargs):
        calls["app"] = wsgi_app
        raise KeyboardInterrupt

    monkeypatch.setattr(module.waitress, "serve", boom)
    with pytest.raises(KeyboardInterrupt):
        module.main()
    assert calls["app"].extensions["engine"]._thread is None


def test_main_rejects_bad_env_with_exit_2(entry, monkeypatch, capsys):
    module, calls = entry
    monkeypatch.setenv("CASETA_MAX_PENDING", "lots")
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("Configuración inválida: ") and "CASETA_MAX_PENDING" in err
    assert "kwargs" not in calls


def test_main_warns_when_admin_pin_unset_and_never_prints_pin(entry, monkeypatch, capsys):
    module, calls = entry
    module.main()
    err = capsys.readouterr().err
    assert "CASETA_ADMIN_PIN" in err and len(err.strip().splitlines()) == 1

    monkeypatch.setenv("CASETA_ADMIN_PIN", "s3cretpin")
    module.main()
    captured = capsys.readouterr()
    assert "s3cretpin" not in captured.err + captured.out
    assert "CASETA_ADMIN_PIN" not in captured.err


def test_main_rejects_non_integer_port_with_exit_2(entry, monkeypatch, capsys):
    module, calls = entry
    monkeypatch.setenv("CASETA_PORT", "http")
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    assert capsys.readouterr().err.startswith("Configuración inválida: ")
    assert "kwargs" not in calls
