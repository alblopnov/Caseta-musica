import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _page_ids_used_by(*scripts):
    ids = set()
    for rel in scripts:
        text = (ROOT / rel).read_text(encoding="utf-8")
        ids.update(re.findall(r'getElementById\("([^"]+)"\)', text))
    return ids


def test_user_page_renders_with_local_assets(phone_a):
    r = phone_a.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "/static/main.js" in html
    assert "/static/userlogic.js" in html
    # helpers and common modules load before the page script
    assert html.index("/static/common.js") < html.index("/static/userlogic.js") < html.index("/static/main.js")
    for element_id in (
        "upload-input",
        "upload-btn",
        "upload-enqueue",
        "categories",
        "search",
        "song-list",
        "prev-page",
        "next-page",
        "page-info",
        "queue",
        "queue-banner",
        "queue-counter",
        "queue-info",
        "offline-notice",
    ):
        assert f'id="{element_id}"' in html, element_id
    assert 'accept=".mp3,.wav,.ogg"' in html
    assert re.search(r'id="upload-enqueue"[^>]*\bchecked\b', html)
    assert "Añadir a la cola al subir" in html
    assert not re.search(r"(src|href)\s*=\s*[\"']\s*(https?:)?//", html, re.I)
    assert "http://" not in html and "https://" not in html


def test_user_page_loads_library_panel_between_userlogic_and_main(phone_a):
    html = phone_a.get("/").get_data(as_text=True)
    assert (
        html.index("/static/userlogic.js")
        < html.index("/static/library.js")
        < html.index("/static/main.js")
    )
    for element_id in _page_ids_used_by("static/main.js", "static/library.js"):
        assert f'id="{element_id}"' in html, element_id


def test_admin_page_renders_with_local_assets(phone_a):
    r = phone_a.get("/albertitoeselmejor")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    order = [
        "/static/common.js",
        "/static/userlogic.js",
        "/static/adminlogic.js",
        "/static/library.js",
        "/static/admin.js",
    ]
    for src in order:
        assert src in html, src
    positions = [html.index(src) for src in order]
    assert positions == sorted(positions)
    assert html.index("/static/format.js") < html.index("/static/userlogic.js")
    ids = _page_ids_used_by("static/admin.js", "static/library.js")
    assert ids, "admin.js should look elements up by id"
    for element_id in ids:
        assert f'id="{element_id}"' in html, element_id
    for element_id in ("pin-form", "pin-input", "pin-error", "skip-btn", "queue", "offline-notice"):
        assert f'id="{element_id}"' in html, element_id
    assert "Entrar" in html and "Saltar canción" in html
    assert re.search(r'href="/"[^>]*>\s*Volver a Usuario', html)
    assert 'type="password"' in html
    assert "cdn.jsdelivr" not in html
    assert not re.search(r"(src|href)\s*=\s*[\"']\s*(https?:)?//", html, re.I)
    assert "http://" not in html and "https://" not in html
