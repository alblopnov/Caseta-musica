import re


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
