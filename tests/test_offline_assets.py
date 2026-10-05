import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files that must never load anything from the network. Task 10 widens this to
# every template once index.html / admin.html are rewritten.
OFFLINE_FILES = [
    "templates/base.html",
    "templates/index.html",
    "static/style.css",
    "static/common.js",
    "static/format.js",
    "static/userlogic.js",
    "static/main.js",
]

REMOTE_REF = re.compile(r"(src|href|url\()\s*=?\s*[\"']?(https?:)?//", re.I)
REMOTE_FETCH = re.compile(r"(fetch|import|XMLHttpRequest|open)\s*\(\s*[\"'`](https?:)?//", re.I)


def test_offline_files_reference_no_remote_urls():
    for rel in OFFLINE_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not REMOTE_REF.search(text), rel
        assert not REMOTE_FETCH.search(text), rel
        assert "http://" not in text and "https://" not in text, rel


def test_vendored_assets_exist():
    for p in ("static/vendor/bulma.min.css", "static/vendor/lobster.woff2"):
        assert (ROOT / p).stat().st_size > 1000, p
    assert (ROOT / "static/vendor/lobster.woff2").read_bytes()[:4] == b"wOF2"


def test_static_assets_are_served(phone_a):
    for url in (
        "/static/vendor/bulma.min.css",
        "/static/style.css",
        "/static/format.js",
        "/static/common.js",
        "/static/vendor/lobster.woff2",
    ):
        r = phone_a.get(url)
        assert r.status_code == 200, url
        r.close()


def test_base_template_renders_with_local_assets_only(app):
    from flask import render_template_string

    tpl = (
        '{% extends "base.html" %}'
        "{% block title %}T{% endblock %}"
        "{% block body %}<p>hola</p>{% endblock %}"
        "{% block scripts %}<script>1</script>{% endblock %}"
    )
    with app.test_request_context("/"):
        html = render_template_string(tpl)
    assert '<html lang="es">' in html
    assert "<p>hola</p>" in html
    assert "/static/vendor/bulma.min.css" in html
    assert "/static/style.css" in html
    assert "/static/format.js" in html
    assert "/static/common.js" in html
    assert not re.search(r"(src|href)\s*=\s*[\"']\s*(https?:)?//", html, re.I)
    assert "http://" not in html and "https://" not in html
    # format.js and common.js load before the page's own scripts
    assert html.index("common.js") < html.index("<script>1</script>")
