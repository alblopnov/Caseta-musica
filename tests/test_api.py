import io
import json

import pytest


def post(c, url, body):
    return c.post(url, json=body)


def login(c, pin="1234"):
    return post(c, "/api/admin/login", {"pin": pin})


def test_two_phones_cannot_jump_each_other(app, phone_a, phone_b, songs):
    for s in ("a1.wav", "a2.wav", "a3.wav"):
        assert post(phone_a, "/api/queue", {"song": s}).status_code == 201
    post(phone_b, "/api/queue", {"song": "b1.wav"})
    q = phone_b.get("/api/state").json["queue"]
    assert [i["title"] for i in q] == ["a1", "b1", "a2", "a3"]
    assert [i["mine"] for i in q] == [False, True, False, False]


def test_enqueue_returns_id_song_and_title(phone_a, songs):
    r = post(phone_a, "/api/queue", {"song": "a1.wav"})
    assert r.status_code == 201
    assert set(r.json) == {"id", "song", "title"}
    assert (r.json["song"], r.json["title"]) == ("a1.wav", "a1")


def test_position_field_cannot_be_used_to_jump(phone_a, phone_b, songs):
    post(phone_a, "/api/queue", {"song": "a1.wav"})
    post(phone_b, "/api/queue", {"song": "b1.wav", "position": 1})
    assert [i["title"] for i in phone_a.get("/api/state").json["queue"]] == ["a1", "b1"]


def test_cannot_remove_other_phones_song(phone_a, phone_b, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    r = phone_b.delete(f"/api/queue/{item['id']}")
    assert (r.status_code, r.json["code"]) == (403, "forbidden")
    r = phone_a.delete(f"/api/queue/{item['id']}")
    assert (r.status_code, r.json) == (200, {"status": "removed"})
    assert phone_a.get("/api/state").json["queue"] == []


def test_move_and_skip_require_admin(phone_a, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    r = post(phone_a, f"/api/queue/{item['id']}/move", {"position": 1})
    assert (r.status_code, r.json["code"]) == (401, "unauthorized")
    r = phone_a.post("/api/skip")
    assert (r.status_code, r.json["code"]) == (401, "unauthorized")


def test_admin_can_move_and_skip(app, phone_a, phone_b, player, songs):
    post(phone_a, "/api/queue", {"song": "a1.wav"})
    post(phone_a, "/api/queue", {"song": "a2.wav"})
    last = post(phone_b, "/api/queue", {"song": "b1.wav"}).json
    assert login(phone_a).status_code == 200
    r = post(phone_a, f"/api/queue/{last['id']}/move", {"position": 1})
    assert r.status_code == 200
    q = phone_a.get("/api/state").json["queue"]
    assert [i["title"] for i in q] == ["b1", "a1", "a2"]

    app.extensions["engine"].tick()
    assert player.playing
    assert phone_a.post("/api/skip").status_code == 200
    assert not player.playing


def test_move_validates_position_and_id(phone_a, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    login(phone_a)
    for bad in ({"position": "1"}, {"position": True}, {"position": 1.5}, {"position": None}, {}):
        r = post(phone_a, f"/api/queue/{item['id']}/move", bad)
        assert (r.status_code, r.json["code"]) == (400, "bad_request"), bad
    assert post(phone_a, f"/api/queue/{item['id']}/move", [1]).status_code == 400
    r = post(phone_a, "/api/queue/nope/move", {"position": 1})
    assert (r.status_code, r.json["code"]) == (404, "not_found")


def test_admin_login_then_everything_allowed(app, phone_a, phone_b, songs):
    assert phone_a.get("/api/admin/session").json == {"admin": False}
    assert post(phone_a, "/api/admin/login", {"pin": "0000"}).status_code == 401
    assert post(phone_a, "/api/admin/login", {"pin": "1234"}).status_code == 200
    item = post(phone_b, "/api/queue", {"song": "b1.wav"}).json
    assert phone_a.delete(f"/api/queue/{item['id']}").status_code == 200
    assert phone_a.get("/api/admin/session").json == {"admin": True}
    assert phone_b.get("/api/admin/session").json == {"admin": False}


def test_bad_pin_is_401_bad_pin(phone_a):
    r = login(phone_a, "0000")
    assert (r.status_code, r.json["code"]) == (401, "bad_pin")
    assert phone_a.get("/api/admin/session").json == {"admin": False}


def test_admin_login_locks_out_after_5_failures(phone_a):
    for _ in range(4):
        assert post(phone_a, "/api/admin/login", {"pin": "x"}).status_code == 401
    assert post(phone_a, "/api/admin/login", {"pin": "x"}).status_code == 401  # the 5th still answers bad
    r = post(phone_a, "/api/admin/login", {"pin": "1234"})
    assert (r.status_code, r.json["code"]) == (429, "locked")
    assert phone_a.get("/api/admin/session").json == {"admin": False}


@pytest.mark.parametrize("pin", [None, 1234, ["1234"], {"a": 1}, True, "\ud800"])
def test_login_with_weird_pin_values_is_401_not_500(phone_a, pin):
    assert post(phone_a, "/api/admin/login", {"pin": pin}).status_code == 401


@pytest.mark.parametrize("body", [None, [1], "1234"])
def test_login_with_non_object_body_is_400(phone_a, body):
    r = phone_a.post("/api/admin/login", data=json.dumps(body), content_type="application/json")
    assert (r.status_code, r.json["code"]) == (400, "bad_request")


@pytest.mark.parametrize("body", [{}, {"other": "1234"}])
def test_login_without_pin_is_401_bad_pin(phone_a, body):
    r = post(phone_a, "/api/admin/login", body)
    assert (r.status_code, r.json["code"]) == (401, "bad_pin")


@pytest.mark.parametrize("url", ["/api/queue", "/api/admin/login"])
def test_deeply_nested_json_is_400_not_500(phone_a, url):
    body = "[" * 100000 + "]" * 100000
    r = phone_a.post(url, data=body, content_type="application/json")
    assert (r.status_code, r.json["code"]) == (400, "bad_request")


def test_move_playing_item_is_404(app, phone_a, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    app.extensions["engine"].tick()
    login(phone_a)
    r = post(phone_a, f"/api/queue/{item['id']}/move", {"position": 1})
    assert (r.status_code, r.json["code"]) == (404, "not_found")


def test_bare_api_path_is_json_404(phone_a):
    r = phone_a.get("/api")
    assert (r.status_code, r.json["code"]) == (404, "not_found")


def test_other_http_errors_under_api_are_json(app, phone_a):
    from werkzeug.exceptions import abort

    app.add_url_rule("/api/teapot", "teapot", lambda: abort(418))
    r = phone_a.get("/api/teapot")
    assert r.status_code == 418
    assert r.json["code"] == "i_m_a_teapot" and r.json["error"]


def test_admin_disabled_without_pin(app_without_pin_client):
    r = post(app_without_pin_client, "/api/admin/login", {"pin": "1"})
    assert (r.status_code, r.json["code"]) == (503, "admin_disabled")


def test_sixth_song_and_duplicate_return_409_with_codes(phone_a, phone_b, songs):  # cap 5
    for i in range(5):
        assert post(phone_a, "/api/queue", {"song": f"s{i}.wav"}).status_code == 201
    r = post(phone_a, "/api/queue", {"song": "s5.wav"})
    assert (r.status_code, r.json["code"]) == (409, "full")
    assert "5" in r.json["error"]
    r = post(phone_b, "/api/queue", {"song": "s0.wav"})
    assert (r.status_code, r.json["code"]) == (409, "duplicate")


def test_second_phone_song_plays_second_after_spam(phone_a, phone_b, songs):
    for i in range(5):
        post(phone_a, "/api/queue", {"song": f"s{i}.wav"})
    post(phone_b, "/api/queue", {"song": "b1.wav"})
    titles = [i["title"] for i in phone_b.get("/api/state").json["queue"]]
    assert titles[:2] == ["s0", "b1"]


@pytest.mark.parametrize("bad", ["../x.mp3", "/etc/passwd", "reggaeton/../../x.mp3", "notes.txt"])
def test_traversal_returns_404_and_never_reaches_player(phone_a, player, app, bad):
    r = post(phone_a, "/api/queue", {"song": bad})
    assert (r.status_code, r.json["code"]) == (404, "not_found")
    app.extensions["engine"].tick()
    assert player.played == []


@pytest.mark.parametrize("body", [None, "just text", [1, 2], {}, {"song": 5}, {"song": None}])
def test_malformed_body_is_400_not_500(phone_a, body):
    r = phone_a.post("/api/queue", data=json.dumps(body), content_type="application/json")
    assert r.status_code == 400 and "error" in r.json
    assert r.json["code"] == "bad_request"


def test_invalid_json_syntax_is_400(phone_a):
    r = phone_a.post("/api/queue", data="{not json", content_type="application/json")
    assert r.status_code == 400 and "error" in r.json


def test_non_json_content_type_is_400(phone_a):
    r = phone_a.post("/api/queue", data="song=a", content_type="text/plain")
    assert r.status_code == 400 and "error" in r.json


def test_delete_unknown_id_is_404(phone_a):
    r = phone_a.delete("/api/queue/nope")
    assert (r.status_code, r.json["code"]) == (404, "not_found")


def test_removing_the_playing_song(app, phone_a, phone_b, player, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    app.extensions["engine"].tick()
    assert phone_b.delete(f"/api/queue/{item['id']}").status_code == 403
    assert player.playing
    assert phone_a.delete(f"/api/queue/{item['id']}").status_code == 200
    assert not player.playing


def test_upload_with_enqueue_adds_to_queue(phone_a):
    r = phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "n.mp3"), "enqueue": "1"})
    assert r.status_code == 201 and r.json["item"]["title"] == "n"
    assert r.json["song"] == "Subidas/n.mp3"
    assert [i["title"] for i in phone_a.get("/api/state").json["queue"]] == ["n"]


def test_upload_without_enqueue_only_saves(phone_a):
    r = phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "n.mp3")})
    assert r.status_code == 201 and r.json["item"] is None
    assert "Subidas/n.mp3" in phone_a.get("/api/songs").json
    assert phone_a.get("/api/state").json["queue"] == []


def test_upload_twice_never_overwrites(phone_a):
    one = phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "n.mp3")}).json["song"]
    two = phone_a.post("/api/upload", data={"song": (io.BytesIO(b"y"), "n.mp3")}).json["song"]
    assert one != two


def test_upload_enqueue_when_full_is_409_but_file_is_kept(phone_a, songs):
    for i in range(5):
        post(phone_a, "/api/queue", {"song": f"s{i}.wav"})
    r = phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "n.mp3"), "enqueue": "true"})
    assert (r.status_code, r.json["code"]) == (409, "full")
    assert r.json["song"] == "Subidas/n.mp3"
    assert "Subidas/n.mp3" in phone_a.get("/api/songs").json


def test_upload_without_file_or_bad_type_is_400(phone_a):
    r = phone_a.post("/api/upload", data={})
    assert (r.status_code, r.json["code"]) == (400, "bad_request")
    assert phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "x.exe")}).status_code == 400
    assert phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "")}).status_code == 400
    assert phone_a.post("/api/upload", json={"song": "x"}).status_code == 400


def test_oversized_upload_is_413_json(app_small_limit_client):  # max_upload_bytes = 1024
    r = app_small_limit_client.post("/api/upload", data={"song": (io.BytesIO(b"x" * 5000), "big.mp3")})
    assert r.status_code == 413 and "error" in r.json
    assert r.json["code"] == "too_large"


def test_songs_lists_library(phone_a, songs):
    names = phone_a.get("/api/songs").json
    assert "a1.wav" in names and names == sorted(names)


def test_state_shape_and_unknown_route_json(phone_a):
    s = phone_a.get("/api/state").json
    assert set(s) == {"now_playing", "queue", "total_seconds", "me"}
    assert phone_a.get("/api/nope").json["error"]
    r = phone_a.get("/api/nope")
    assert (r.status_code, r.json["code"]) == (404, "not_found")


def test_method_not_allowed_is_json(phone_a):
    r = phone_a.put("/api/queue")
    assert (r.status_code, r.json["code"]) == (405, "method_not_allowed")


def test_unhandled_error_is_json_500(app, phone_a, monkeypatch):
    def boom(viewer):
        raise RuntimeError("boom")

    monkeypatch.setattr(app.extensions["engine"], "snapshot", boom)
    r = phone_a.get("/api/state")
    assert (r.status_code, r.json["code"]) == (500, "server_error")
    assert "boom" not in r.json["error"]


def test_pages_render(phone_a):
    assert phone_a.get("/").status_code == 200
    assert phone_a.get("/albertitoeselmejor").status_code == 200


def test_state_me_counts_pending(phone_a, songs):
    post(phone_a, "/api/queue", {"song": "a1.wav"})
    assert phone_a.get("/api/state").json["me"] == {"pending": 1, "max": 5}
