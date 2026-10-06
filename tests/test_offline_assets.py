import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files that must never load anything from the network: every template plus
# the project's own static scripts and styles (vendor/ is third-party bundles).
OFFLINE_FILES = sorted(
    [p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").glob("*.html")]
    + [
        "static/style.css",
        "static/common.js",
        "static/format.js",
        "static/userlogic.js",
        "static/adminlogic.js",
        "static/library.js",
        "static/nowplaying.js",
        "static/main.js",
        "static/admin.js",
    ]
)


def test_offline_files_cover_every_template():
    assert {"templates/base.html", "templates/index.html", "templates/admin.html"} <= set(OFFLINE_FILES)

REMOTE_REF = re.compile(r"(src|href|url\()\s*=?\s*[\"']?(https?:)?//", re.I)
REMOTE_FETCH = re.compile(r"(fetch|import|XMLHttpRequest|open)\s*\(\s*[\"'`](https?:)?//", re.I)


def test_offline_files_reference_no_remote_urls():
    for rel in OFFLINE_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not REMOTE_REF.search(text), rel
        assert not REMOTE_FETCH.search(text), rel
        assert "http://" not in text and "https://" not in text, rel


ICONS = (
    "skip-forward-fill",
    "x-bold",
    "upload-simple-bold",
    "magnifying-glass-bold",
    "plus-bold",
    "dots-six-vertical-bold",
    "music-notes-fill",
)


def test_vendored_assets_exist():
    for p in ("static/vendor/lobster.woff2", "static/vendor/outfit.woff2"):
        assert (ROOT / p).stat().st_size > 1000, p
        assert (ROOT / p).read_bytes()[:4] == b"wOF2", p
    for name in ICONS:
        svg = (ROOT / f"static/vendor/icons/{name}.svg").read_text(encoding="utf-8")
        assert svg.lstrip().startswith("<svg") and "currentColor" in svg, name


def test_every_icon_used_in_css_is_vendored():
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    used = set(re.findall(r'vendor/icons/([a-z-]+)\.svg', css))
    assert used and used <= set(ICONS)


def test_ui_text_has_no_emoji_or_dash_separators():
    # The design rules ban emoji and em/en dashes in visible text (hyphen only).
    banned = re.compile("[–—🌀-🫿☀-➿]")
    for rel in OFFLINE_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not banned.search(text), rel


def test_static_assets_are_served(phone_a):
    for url in (
        "/static/style.css",
        "/static/format.js",
        "/static/common.js",
        "/static/nowplaying.js",
        "/static/favicon.svg",
        "/static/vendor/lobster.woff2",
        "/static/vendor/outfit.woff2",
        "/static/vendor/icons/skip-forward-fill.svg",
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
    assert "/static/favicon.svg" in html
    assert "/static/style.css" in html
    assert "/static/format.js" in html
    assert "/static/common.js" in html
    assert not re.search(r"(src|href)\s*=\s*[\"']\s*(https?:)?//", html, re.I)
    assert "http://" not in html and "https://" not in html
    # format.js and common.js load before the page's own scripts
    assert html.index("common.js") < html.index("<script>1</script>")
