# Fair Shared Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let many phones add music to one Raspberry Pi sound system through a single queue where nobody can jump, remove, or reorder anyone else's songs.

**Architecture:** Split the 215-line `app.py` into a small `caseta` package: a pure `FairQueue` (round-robin across owners), a `Library` (safe paths, uploads, durations), a `PlaybackEngine` (one thread, `Player` interface so tests never touch audio), and a Flask blueprint. Phones are identified by a cookie, the admin by a PIN-gated session. The UI is rebuilt on one shared `/api/state` endpoint, with every asset served locally so it works on a hotspot with no internet.

**Tech Stack:** Python 3.11, Flask 3.1, waitress, pygame (mixer), mutagen, pytest; vanilla JS (`fetch`) + vendored Bulma; `node --test` for pure JS helpers.

**Spec:** No separate spec document. The spec is the user's stated objective ("put music from different phones into the same sound system without jumping other people's music") plus the repo analysis below. The Raspberry Pi side (hotspot, captive portal, systemd) is a second plan: `docs/superpowers/plans/2026-10-05-pi-hotspot-deployment.md`.

## Repo Analysis (what is wrong today)

| # | Finding | Where | Why it matters for the objective |
|---|---|---|---|
| 1 | Anyone can jump the queue: `POST /api/queue` accepts `position`, and `/api/queue/move` is open to all | `app.py:130-157, 185-212` | Directly contradicts the goal |
| 2 | Anyone can delete anyone's song, including the one playing; "admin" is only an obscure URL, the API is unprotected | `app.py:159-183`, `/albertitoeselmejor` | Other people's music gets removed |
| 3 | Queue entries are identified by filename: the same song twice, or the playing song also queued, removes the wrong entry | `app.py:166-179` | Wrong song removed or stopped |
| 4 | Pure FIFO: one phone adding 20 songs blocks everybody for over an hour | `play_queue` | No fairness |
| 5 | Page loads axios, Bulma and Google Fonts from CDNs. On the Pi's hotspot there is no internet, so `axios` is undefined and the whole UI is dead | `templates/*.html:7-9` | The app cannot work in its real environment |
| 6 | `debug=True` serves the Werkzeug debugger on `0.0.0.0` of an open Wi-Fi: remote code execution for any guest | `app.py:215` | Security |
| 7 | `song` is joined to `SONG_FOLDER` without a containment check; `../../etc/passwd` passes `isfile` and is handed to the player | `app.py:135, 35` | Arbitrary file read/play |
| 8 | `request.get_json()` returns `None` on a bad body, so `data.get` raises 500 | every POST/DELETE | Crashes on malformed input |
| 9 | Upload: no size limit, `secure_filename` can return `"mp3"` for non-ASCII names (rejected or mangled), same name silently overwrites | `app.py:76-90` | Phones with accented/emoji names fail or clobber files |
| 10 | Wait estimate assumes 192 kbps and ignores how much of the current song already played | `app.py:101-128` | Misleading "time in queue" |
| 11 | `pygame.mixer.init()` at import time: the app (and any test) crashes on a machine without an audio device | `app.py:12` | Untestable |
| 12 | `main.js` and `admin.js` are ~80% duplicated; both build rows with `innerHTML` and two requests per 5 s poll; admin re-renders the whole page every 5 s, even mid-drag | `static/*.js` | Maintenance, XSS-prone, drag glitches |
| 13 | `venv/` (60 MB, 2645 files, a Windows venv) is committed; `.gitignore` and `requirements.txt` are UTF-16 (git ignores a UTF-16 `.gitignore`); unused `python-vlc`, `flask-cors` | repo root | Repo hygiene |

## Decisions made in this plan (change them before executing if you disagree)

- **Fairness policy:** round-robin by owner. Each phone's k-th pending song is "round k"; play order is by round, then arrival. A newcomer's first song plays after the current round-0 songs, not behind someone else's 20.
- **Cap:** at most 5 pending songs per phone (`CASETA_MAX_PENDING`). The same song cannot be pending twice.
- **Identity:** random cookie per phone. It is a courtesy, not security: clearing cookies resets a phone's identity. iOS's captive-portal mini-browser has a separate cookie jar from Safari, so a user can look like two phones.
- **Ownership:** you can remove only your own songs (including your own playing song, which skips it). The admin can remove, reorder, and skip anything.
- **Admin:** PIN from env `CASETA_ADMIN_PIN`, signed session cookie, 5 failed attempts means 60 s lockout. The admin page keeps the URL `/albertitoeselmejor`.
- **Uploads:** `.mp3 .wav .ogg`, 30 MB, saved to `songs/Subidas/` (was hard-coded `reggaeton`). Optionally enqueued right after upload.
- **Out of scope:** m4a/flac (needs ffmpeg transcoding), Spotify/streaming, queue persistence across restarts, per-user nicknames.

## Global Constraints

- All UI strings stay in Spanish.
- The app must work with zero internet: no `http://` or `https://` URL in any template or static file reference.
- Python 3.11; `Flask==3.1.0`, `pygame==2.6.1` (versions already in the repo).
- Production server is `waitress`; `debug=True` must never appear in `app.py`.
- Admin PIN comes only from env `CASETA_ADMIN_PIN`; it is never committed or logged.
- Env knobs: `CASETA_ADMIN_PIN`, `CASETA_MAX_PENDING` (default 5), `CASETA_MAX_UPLOAD_MB` (default 30), `CASETA_PORT` (default 5000), `CASETA_SONG_DIR` (default `songs`).
- Allowed audio extensions: `mp3`, `wav`, `ogg`.
- Run tests with `python -m pytest -q` and `node --test tests/frontend/`.
- Commit messages follow repo style: `Added ...`, `Fixed ...`.

## Review Focus

Failure modes the spec implies but no happy-path task covers, most likely first. Each has its test in the named task.

1. **Path traversal in `song`** (`../x.mp3`, `/etc/passwd`, `reggaeton/../../x.mp3`, `notes.txt`): must answer 404 and never reach the player. Tests in Task 3 and Task 6.
2. **Phone filenames** (`歌.mp3`, `🎵.mp3`, `Bad Bunny – Tití.mp3`, same name uploaded twice): saved under a safe unique name, never rejected for the name and never overwritten. Task 3.
3. **Malformed or oversized requests** (non-JSON body, `null`, missing fields, 40 MB upload): 400 / 413 JSON, never a 500 or an HTML error page. Task 6.
4. **Spam and duplicates** (same song twice, 6th pending song, one phone adding 20 songs while another adds 1): 409 with distinct `code` (`duplicate`/`full`), and the second phone's song plays second. Tasks 2 and 6.
5. **Playback edge cases** (owner removes the song playing, skip with an empty queue, unreadable or corrupt mp3, queue empties between ticks): no crash, the next song starts. Task 4.

---

## File Structure

```
app.py                     entry point: build app, serve with waitress (rewritten, Task 7)
caseta/__init__.py         create_app(config, player=None, start_engine=True)   (Task 6)
caseta/config.py           Config dataclass + from_env()                        (Task 3)
caseta/fair_queue.py       FairQueue, QueueItem, queue errors                   (Task 2)
caseta/library.py          Library: list/resolve/upload/duration/title          (Task 3)
caseta/player.py           Player protocol + PygamePlayer                       (Task 4)
caseta/engine.py           PlaybackEngine                                       (Task 4)
caseta/identity.py         client cookie + AdminAuth                            (Task 5)
caseta/routes.py           /api blueprint + pages                               (Task 6)
caseta/portal.py           unknown-Host redirect (captive portal)               (Task 7)
templates/base.html        shared head, local assets                            (Task 8)
templates/index.html, admin.html  extend base                                   (Tasks 9, 10)
static/style.css, vendor/  local CSS, Bulma, Lobster font                       (Task 8)
static/format.js           pure formatting helpers (node-testable)              (Task 8)
static/common.js           api(), el(), startPolling()                          (Task 8)
static/main.js, admin.js   thin page scripts                                    (Tasks 9, 10)
tests/                     pytest suite; tests/frontend/ node tests
```

---

### Task 1: Repo hygiene and test harness

**Files:**
- Modify: `.gitignore` (rewrite as UTF-8), `requirements.txt` (rewrite as UTF-8)
- Create: `requirements-dev.txt`
- Untrack: `venv/` (files stay on disk)

**Interfaces:**
- Produces: a clean repo where `python -m pytest` runs inside a fresh `.venv`.

- [ ] **Step 1: Untrack the committed venv**

Run: `git rm -r --cached venv -q`
Expected: no error; `git ls-files | wc -l` now prints fewer than 10. (History still contains the 60 MB; rewriting it is out of scope.)

- [ ] **Step 2: Rewrite `.gitignore` as UTF-8** with one pattern per line: `venv/`, `.venv/`, `songs/`, `__pycache__/`, `.pytest_cache/`, `instance/`, `*.env`.

- [ ] **Step 3: Rewrite `requirements.txt` as UTF-8** with exactly: `Flask==3.1.0`, `waitress==3.0.2`, `pygame==2.6.1`, `mutagen==1.47.0`. (Drops `python-vlc`, `flask-cors`, `colorama`, and other transitive pins; pip resolves them.) Create `requirements-dev.txt` with `-r requirements.txt` and `pytest==8.3.4`.

- [ ] **Step 4: Create the new env and verify**

Run: `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest --version`
Expected: prints `pytest 8.3.4`. (On Pi/Linux the interpreter is `.venv/bin/python`.)

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt requirements-dev.txt
git commit -m "Removed committed venv, fixed gitignore and requirements encoding"
```

---

### Task 2: FairQueue (pure logic)

**Files:**
- Create: `caseta/__init__.py` (empty for now), `caseta/fair_queue.py`
- Test: `tests/test_fair_queue.py`

**Interfaces:**
- Produces, in `caseta/fair_queue.py`:
  - `@dataclass(frozen=True) class QueueItem: id: str; song: str; owner: str; round: int` (`id` is `uuid4().hex`; `song` is a library-relative path)
  - Exceptions: `QueueFull`, `DuplicateSong`, `NotOwner`, `UnknownItem` (all subclass `Exception`)
  - `class FairQueue(max_pending_per_user: int)` with:
    - `add(song: str, owner: str) -> QueueItem`
    - `pop_next() -> QueueItem | None`
    - `remove(item_id: str, requester: str, is_admin: bool = False) -> QueueItem`
    - `move(item_id: str, position: int) -> None` (admin reorder; `position` is 1-based in `snapshot()`, clamped to range)
    - `snapshot() -> list[QueueItem]` (play order)
    - `pending_count(owner: str) -> int`
  - Not thread-safe; `PlaybackEngine` holds the lock.

Ordering rule (the algorithm the tests do not fully determine): `add` gives the item `round = 1 + max(round of the owner's pending items)`, or `0` if the owner has none, then inserts it immediately before the first pending item whose round is greater than its own (appends if none). `remove` of a pending item decrements the round of that owner's later items by 1.

- [ ] **Step 1: Write the failing tests**

```python
def order(q): return [i.song for i in q.snapshot()]

def test_newcomer_does_not_wait_behind_a_spammer():
    q = FairQueue(max_pending_per_user=5)
    for s in ("a1", "a2", "a3"): q.add(s, "A")
    q.add("b1", "B")
    assert order(q) == ["a1", "b1", "a2", "a3"]

def test_round_robin_three_users():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"): q.add(s, "A")
    q.add("b1", "B"); q.add("c1", "C"); q.add("b2", "B")
    assert order(q) == ["a1", "b1", "c1", "a2", "b2", "a3"]

def test_owner_who_just_got_played_does_not_jump_ahead():
    q = FairQueue(5)
    q.add("a1", "A"); q.add("a2", "A"); q.add("b1", "B")
    assert q.pop_next().song == "a1"
    assert order(q) == ["b1", "a2"]

def test_owners_own_songs_keep_their_order():
    q = FairQueue(5)
    for s in ("a1", "b1", "a2", "b2", "a3"): q.add(s, s[0].upper())
    assert [s for s in order(q) if s[0] == "a"] == ["a1", "a2", "a3"]

def test_cap_raises_queue_full():
    q = FairQueue(2); q.add("a1", "A"); q.add("a2", "A")
    with pytest.raises(QueueFull): q.add("a3", "A")

def test_cap_frees_up_after_pop():
    q = FairQueue(1); q.add("a1", "A"); q.pop_next(); q.add("a2", "A")

def test_duplicate_song_rejected_even_from_another_owner():
    q = FairQueue(5); q.add("x", "A")
    with pytest.raises(DuplicateSong): q.add("x", "B")

def test_only_owner_or_admin_can_remove():
    q = FairQueue(5); item = q.add("x", "A")
    with pytest.raises(NotOwner): q.remove(item.id, requester="B")
    assert q.remove(item.id, requester="B", is_admin=True) == item

def test_remove_unknown_item():
    with pytest.raises(UnknownItem): FairQueue(5).remove("nope", "A")

def test_remove_closes_the_gap_in_owner_rounds():
    q = FairQueue(5); a1 = q.add("a1", "A"); q.add("a2", "A"); q.add("b1", "B")
    q.remove(a1.id, "A")
    assert order(q) == ["a2", "b1"]   # a2 is now round 0, arrived first

def test_admin_move_overrides_fairness_and_clamps():
    q = FairQueue(5); a1 = q.add("a1", "A"); q.add("b1", "B"); q.add("a2", "A")
    q.move(a1.id, 99)
    assert order(q) == ["b1", "a2", "a1"]
    q.move(a1.id, 0)
    assert order(q)[0] == "a1"

def test_pop_next_on_empty_returns_none():
    assert FairQueue(5).pop_next() is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_fair_queue.py -q`
Expected: FAIL / collection error (`ModuleNotFoundError: caseta.fair_queue`).

- [ ] **Step 3: Implement `FairQueue` and `QueueItem` in `caseta/fair_queue.py`** per the Interfaces block and ordering rule. Store a plain `list[QueueItem]` in play order.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_fair_queue.py -q`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add caseta/__init__.py caseta/fair_queue.py tests/test_fair_queue.py
git commit -m "Added FairQueue with round-robin ordering"
```

---

### Task 3: Config and Library

**Files:**
- Create: `caseta/config.py`, `caseta/library.py`, `tests/conftest.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Produces, in `caseta/config.py`:
  - `@dataclass(frozen=True) class Config` with fields and defaults: `song_folder: Path = Path("songs")`, `upload_category: str = "Subidas"`, `allowed_extensions: frozenset[str] = frozenset({"mp3","wav","ogg"})`, `max_upload_bytes: int = 30*1024*1024`, `max_pending_per_user: int = 5`, `admin_pin: str | None = None`, `secret_key: str` (default `secrets.token_hex(32)` per process), `portal_url: str = "http://10.42.0.1/"`, `allowed_hosts: frozenset[str] = frozenset({"10.42.0.1","caseta.local","localhost","127.0.0.1"})`.
  - `Config.from_env(environ: Mapping[str,str] = os.environ) -> Config` reading the Global Constraints env vars.
- Produces, in `caseta/library.py`: exceptions `SongNotFound`, `InvalidUpload`; `class Library(config: Config)` with:
  - `list_songs() -> list[str]` sorted, `/`-separated paths relative to `song_folder`, allowed extensions only
  - `resolve(song: str) -> Path` raises `SongNotFound` if empty, outside `song_folder` after `Path.resolve()`, extension not allowed, or not a file
  - `save_upload(file: werkzeug.datastructures.FileStorage) -> str` returns the relative path inside `upload_category`; raises `InvalidUpload` on a bad extension. Name = `secure_filename(stem)` + original extension; if the sanitized stem is empty use `cancion-<8 hex>`; if the name exists append `-1`, `-2`, …
  - `duration(song: str) -> float` seconds via `mutagen.File(path).info.length`, cached per path; `180.0` when unreadable
  - `@staticmethod title(song: str) -> str` basename without extension
- `tests/conftest.py` produces fixtures: `config(tmp_path)` (a `Config` with `song_folder=tmp_path/"songs"`, `admin_pin="1234"`), `library(config)`, and helper `make_wav(path: Path, seconds: float) -> Path` writing a silent mono 8 kHz WAV with the `wave` module (creating parent dirs).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("bad", ["../secret.mp3", "/etc/passwd", "reggaeton/../../secret.mp3",
                                 "notes.txt", "missing.mp3", "", "reggaeton"])
def test_resolve_rejects_unsafe_or_unknown(library, config, bad):
    make_wav(config.song_folder.parent / "secret.mp3", 1)   # exists, but outside the folder
    make_wav(config.song_folder / "reggaeton" / "ok.mp3", 1)
    with pytest.raises(SongNotFound): library.resolve(bad)

def test_resolve_accepts_nested_song(library, config):
    p = make_wav(config.song_folder / "reggaeton" / "ok.wav", 1)
    assert library.resolve("reggaeton/ok.wav") == p.resolve()

def test_list_songs_relative_sorted_allowed_only(library, config):
    make_wav(config.song_folder / "b.wav", 1); make_wav(config.song_folder / "Rock" / "a.wav", 1)
    (config.song_folder / "readme.txt").write_text("x")
    assert library.list_songs() == ["Rock/a.wav", "b.wav"]

def upload(name, data=b"x"):
    return FileStorage(stream=io.BytesIO(data), filename=name)

def test_upload_same_name_twice_gets_unique_names(library):
    assert library.save_upload(upload("a.mp3")) == "Subidas/a.mp3"
    assert library.save_upload(upload("a.mp3")) == "Subidas/a-1.mp3"

@pytest.mark.parametrize("name", ["歌.mp3", "🎵.mp3"])
def test_upload_non_ascii_name_gets_generated_name(library, name):
    assert re.fullmatch(r"Subidas/cancion-[0-9a-f]{8}\.mp3", library.save_upload(upload(name)))

def test_upload_keeps_readable_part_of_accented_name(library):
    assert library.save_upload(upload("Bad Bunny – Tití.mp3")) == "Subidas/Bad_Bunny_Titi.mp3"

@pytest.mark.parametrize("name", ["x.exe", "noext", "../../evil.mp3.sh"])
def test_upload_rejects_bad_extension(library, name):
    with pytest.raises(InvalidUpload): library.save_upload(upload(name))

def test_duration_reads_wav_length(library, config):
    make_wav(config.song_folder / "t.wav", 2.0)
    assert library.duration("t.wav") == pytest.approx(2.0, abs=0.05)

def test_duration_falls_back_for_garbage_file(library, config):
    p = config.song_folder / "bad.mp3"; p.parent.mkdir(parents=True); p.write_bytes(b"not audio")
    assert library.duration("bad.mp3") == 180.0

def test_title_strips_folder_and_extension():
    assert Library.title("reggaeton/Bad Bunny - Tití.mp3") == "Bad Bunny - Tití"

def test_from_env_reads_knobs():
    c = Config.from_env({"CASETA_ADMIN_PIN": "9", "CASETA_MAX_PENDING": "3", "CASETA_MAX_UPLOAD_MB": "5"})
    assert (c.admin_pin, c.max_pending_per_user, c.max_upload_bytes) == ("9", 3, 5 * 1024 * 1024)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_library.py -q`
Expected: FAIL with `ModuleNotFoundError: caseta.config`.

- [ ] **Step 3: Implement `Config` and `Library`** per the Interfaces block (`pathlib` containment check via `Path.resolve()` + `is_relative_to`).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_library.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add caseta/config.py caseta/library.py tests/conftest.py tests/test_library.py
git commit -m "Added Config and Library with safe paths, unique uploads and real durations"
```

---

### Task 4: Player and PlaybackEngine

**Files:**
- Create: `caseta/player.py`, `caseta/engine.py`, `tests/fakes.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `FairQueue`, `QueueItem` and its errors (Task 2); `Library.resolve/duration/title`, `SongNotFound` (Task 3).
- Produces, in `caseta/player.py`:
  - `class Player(Protocol)`: `play(path: Path) -> None`, `stop() -> None`, `is_playing() -> bool`
  - `class PygamePlayer`: implements `Player`; calls `pygame.mixer.init()` lazily on the first `play`, so importing never needs an audio device.
- Produces, in `caseta/engine.py`: `class PlaybackEngine(queue: FairQueue, player: Player, library: Library, clock: Callable[[], float] = time.monotonic, poll_interval: float = 0.25)` with:
  - `start() -> None` / `stop() -> None` (daemon thread calling `tick()` then sleeping `poll_interval`; `stop` joins it)
  - `tick() -> None` one synchronous iteration (below)
  - `enqueue(song: str, owner: str) -> QueueItem` (calls `library.resolve` first, so `SongNotFound` propagates; then `queue.add`)
  - `remove(item_id: str, requester: str, is_admin: bool = False) -> None`: if `item_id` is the playing item, only its owner or an admin may remove it; that stops the player. Otherwise delegates to `queue.remove`. Raises `NotOwner`/`UnknownItem`.
  - `skip() -> None` stops the player if something is playing, else no-op
  - `move(item_id: str, position: int) -> None`
  - `snapshot(viewer: str) -> dict` with shape `{"now_playing": {"id","song","title","mine","elapsed","duration"} | None, "queue": [{"id","song","title","mine","eta_seconds"}], "total_seconds": float, "me": {"pending": int, "max": int}}`. `eta_seconds` of `queue[i]` = remaining time of the playing song (`max(0, duration - elapsed)`, or 0 if none) + durations of `queue[:i]`. `total_seconds` = remaining + all queued durations. `me.pending` counts the viewer's queued (not playing) songs.
  - All state and queue access guarded by one `threading.RLock`.
- `tick()` rules: if a song is playing and `player.is_playing()` is false, mark it finished. If nothing is playing, `pop_next()`; if it returned an item, `player.play(library.resolve(item.song))` and record `started_at = clock()`. If `resolve` or `play` raises, log the error, drop that item, and leave nothing playing (the next `tick` takes the next item).
- `tests/fakes.py` produces `FakePlayer`: records `played: list[Path]`; `play` sets `playing = True` (raises `RuntimeError` if `fail_next` is set); `stop` sets `playing = False`; `finish()` sets `playing = False`; `is_playing()` returns `playing`.

- [ ] **Step 1: Write the failing tests** (real `Library` over `make_wav` files, `FakePlayer`, a fake clock `t = [0.0]`)

```python
def test_tick_starts_first_song_and_reports_it(engine, player, add):
    add("a.wav", "A"); engine.tick()
    assert player.played == [lib_path("a.wav")]
    assert engine.snapshot("A")["now_playing"]["title"] == "a"
    assert engine.snapshot("A")["now_playing"]["mine"] is True

def test_next_song_starts_only_after_current_finishes(engine, player, add):
    add("a.wav", "A"); add("b.wav", "B"); engine.tick(); engine.tick()
    assert len(player.played) == 1
    player.finish(); engine.tick()
    assert len(player.played) == 2

def test_fairness_end_to_end(engine, player, add):
    for s in ("a1.wav", "a2.wav", "a3.wav"): add(s, "A")
    add("b1.wav", "B")
    played = drain(engine, player)            # tick/finish until empty
    assert [p.name for p in played] == ["a1.wav", "b1.wav", "a2.wav", "a3.wav"]

def test_eta_uses_remaining_time_of_current_song(engine, player, add, clock):
    add("a.wav", "A"); add("b.wav", "B"); add("c.wav", "C")   # 10s, 20s, 30s files
    engine.tick(); clock[0] = 4.0
    q = engine.snapshot("B")["queue"]
    assert [round(i["eta_seconds"]) for i in q] == [6, 26]
    assert round(engine.snapshot("B")["total_seconds"]) == 56
    assert q[0]["mine"] is True and q[1]["mine"] is False

def test_snapshot_me_counts_only_viewers_pending(engine, add):
    add("a.wav", "A"); add("b.wav", "A"); engine.tick()
    assert engine.snapshot("A")["me"] == {"pending": 1, "max": 5}

def test_owner_can_remove_own_playing_song_other_cannot(engine, player, add):
    add("a.wav", "A"); engine.tick(); now = engine.snapshot("A")["now_playing"]["id"]
    with pytest.raises(NotOwner): engine.remove(now, "B")
    engine.remove(now, "A"); assert player.playing is False

def test_admin_can_remove_playing_song(engine, player, add): ...  # same with is_admin=True

def test_skip_with_nothing_playing_is_a_noop(engine): engine.skip()

def test_skip_advances_to_next(engine, player, add):
    add("a.wav", "A"); add("b.wav", "B"); engine.tick(); engine.skip(); engine.tick()
    assert [p.name for p in player.played] == ["a.wav", "b.wav"]

def test_unreadable_song_is_dropped_and_next_plays(engine, player, add):
    add("a.wav", "A"); add("b.wav", "B"); player.fail_next = True
    engine.tick(); engine.tick()
    assert [p.name for p in player.played] == ["b.wav"]

def test_song_deleted_from_disk_after_queueing_is_skipped(engine, player, add, songs):
    add("a.wav", "A"); add("b.wav", "B"); (songs / "a.wav").unlink()
    engine.tick(); assert [p.name for p in player.played] == ["b.wav"]

def test_enqueue_unknown_song_raises_song_not_found(engine):
    with pytest.raises(SongNotFound): engine.enqueue("../x.mp3", "A")

def test_start_and_stop_thread_plays_a_song(engine_factory):  # real thread, poll_interval=0.01
    ...  # enqueue, start(), poll up to 2 s for player.played, stop(); assert thread not alive
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_engine.py -q`
Expected: FAIL with `ModuleNotFoundError: caseta.engine`.

- [ ] **Step 3: Implement `Player`/`PygamePlayer` and `PlaybackEngine`** per the Interfaces block.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_engine.py -q`
Expected: all pass, no test takes more than 2 s.

- [ ] **Step 5: Commit**

```bash
git add caseta/player.py caseta/engine.py tests/fakes.py tests/test_engine.py
git commit -m "Added PlaybackEngine behind a Player interface"
```

---

### Task 5: Identity and admin auth

**Files:**
- Create: `caseta/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Produces, in `caseta/identity.py`:
  - `CLIENT_COOKIE = "caseta_client"`
  - `init_identity(app: Flask) -> None`: `before_request` sets `flask.g.client_id` to the cookie value if it matches `^[0-9a-f]{32}$`, else a new `uuid4().hex`; `after_request` sets the cookie when new (`HttpOnly`, `SameSite=Lax`, `max_age` one year).
  - `class AdminAuth(pin: str | None, max_failures: int = 5, lockout_seconds: float = 60, clock: Callable[[], float] = time.monotonic)` with `attempt(pin: str, key: str) -> Literal["ok","bad","locked","disabled"]` (`hmac.compare_digest`; `key` is the caller's remote address; failures counted per key; a lockout rejects even the right PIN until it expires; success resets the count).
  - `is_admin() -> bool` reads `flask.session.get("admin") is True`; `set_admin(on: bool) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_new_visitor_gets_cookie_and_keeps_it(app_client):
    r1 = app_client.get("/_whoami"); r2 = app_client.get("/_whoami")
    assert re.fullmatch(r"[0-9a-f]{32}", r1.text) and r1.text == r2.text
    assert "caseta_client=" in r1.headers["Set-Cookie"] and "HttpOnly" in r1.headers["Set-Cookie"]

def test_garbage_cookie_is_replaced(app):
    c = app.test_client(); c.set_cookie("caseta_client", "../../x")
    assert re.fullmatch(r"[0-9a-f]{32}", c.get("/_whoami").text)

def test_two_clients_get_different_ids(app): ...

def test_admin_auth_ok_bad_disabled():
    a = AdminAuth("1234")
    assert a.attempt("1234", "ip") == "ok" and a.attempt("0000", "ip") == "bad"
    assert AdminAuth(None).attempt("1234", "ip") == "disabled"

def test_admin_auth_locks_out_then_recovers():
    t = [0.0]; a = AdminAuth("1234", max_failures=5, lockout_seconds=60, clock=lambda: t[0])
    for _ in range(5): a.attempt("x", "ip")
    assert a.attempt("1234", "ip") == "locked"
    assert a.attempt("1234", "other-ip") == "ok"
    t[0] = 61; assert a.attempt("1234", "ip") == "ok"
```

(`app_client` here is a tiny test-local Flask app with `init_identity` and a `/_whoami` route returning `g.client_id`.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_identity.py -q`
Expected: FAIL with `ModuleNotFoundError: caseta.identity`.

- [ ] **Step 3: Implement `identity.py`** per the Interfaces block.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_identity.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add caseta/identity.py tests/test_identity.py
git commit -m "Added per-phone identity cookie and PIN admin auth with lockout"
```

---

### Task 6: HTTP API and `create_app`

**Files:**
- Create: `caseta/routes.py`; fill in `caseta/__init__.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: everything from Tasks 2-5.
- Produces:
  - `create_app(config: Config | None = None, player: Player | None = None, start_engine: bool = True) -> Flask`. Defaults: `Config.from_env()`, `PygamePlayer()`. Sets `app.secret_key = config.secret_key` and `app.config["MAX_CONTENT_LENGTH"] = config.max_upload_bytes`; stores `app.extensions["engine"]` (`PlaybackEngine`) and `app.extensions["library"]`; starts the engine only if `start_engine`. Registers `init_identity` and the blueprint. Registers JSON error handlers (400, 404, 405, 413, 500) returning `{"error": str}`.
  - Routes (all errors are `{"error": "<Spanish message>", "code": "<slug>"}`):
    - `GET /` renders `index.html`; `GET /albertitoeselmejor` renders `admin.html`
    - `GET /api/songs` returns `list[str]`
    - `GET /api/state` returns `engine.snapshot(g.client_id)`
    - `POST /api/queue` body `{"song": str}`: 201 `{"id","song","title"}`; 400 `bad_request` for a non-object body or missing/non-string `song`; 404 `not_found`; 409 `duplicate` / `full`. Any `position` field is ignored.
    - `DELETE /api/queue/<id>`: 200 `{"status":"removed"}`; 403 `forbidden`; 404 `not_found`. Admin session may remove anything.
    - `POST /api/queue/<id>/move` body `{"position": int}`: admin only (401 `unauthorized`); 400 on a non-int; 404 unknown id.
    - `POST /api/skip`: admin only; 200.
    - `POST /api/upload` multipart `song` and optional `enqueue=1`: 201 `{"song": str, "item": {...} | null}`; 400 `bad_request` (missing file, empty filename, `InvalidUpload`); 409 if `enqueue=1` hits the cap or duplicate (the file is still saved; response includes `"song"`).
    - `POST /api/admin/login` body `{"pin": str}`: 200 sets session; 401 `bad_pin`; 429 `locked`; 503 `admin_disabled`. `GET /api/admin/session` returns `{"admin": bool}`.

- [ ] **Step 1: Write the failing tests** (fixtures: `app = create_app(config, player=FakePlayer(), start_engine=False)`; two phones = two `app.test_client()` instances with separate cookie jars; songs made with `make_wav`)

```python
def post(c, url, body): return c.post(url, json=body)

def test_two_phones_cannot_jump_each_other(app, phone_a, phone_b, songs):
    for s in ("a1.wav", "a2.wav", "a3.wav"): assert post(phone_a, "/api/queue", {"song": s}).status_code == 201
    post(phone_b, "/api/queue", {"song": "b1.wav"})
    q = phone_b.get("/api/state").json["queue"]
    assert [i["title"] for i in q] == ["a1", "b1", "a2", "a3"]
    assert [i["mine"] for i in q] == [False, True, False, False]

def test_position_field_cannot_be_used_to_jump(phone_a, phone_b, songs):
    post(phone_a, "/api/queue", {"song": "a1.wav"})
    post(phone_b, "/api/queue", {"song": "b1.wav", "position": 1})
    assert [i["title"] for i in phone_a.get("/api/state").json["queue"]] == ["a1", "b1"]

def test_cannot_remove_other_phones_song(phone_a, phone_b, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    assert phone_b.delete(f"/api/queue/{item['id']}").status_code == 403
    assert phone_a.delete(f"/api/queue/{item['id']}").status_code == 200

def test_move_and_skip_require_admin(phone_a, songs):
    item = post(phone_a, "/api/queue", {"song": "a1.wav"}).json
    assert post(phone_a, f"/api/queue/{item['id']}/move", {"position": 1}).status_code == 401
    assert phone_a.post("/api/skip").status_code == 401

def test_admin_login_then_everything_allowed(app, phone_a, phone_b, songs):
    assert post(phone_a, "/api/admin/login", {"pin": "0000"}).status_code == 401
    assert post(phone_a, "/api/admin/login", {"pin": "1234"}).status_code == 200
    item = post(phone_b, "/api/queue", {"song": "b1.wav"}).json
    assert phone_a.delete(f"/api/queue/{item['id']}").status_code == 200
    assert phone_a.get("/api/admin/session").json == {"admin": True}

def test_admin_login_locks_out_after_5_failures(phone_a):
    for _ in range(5): post(phone_a, "/api/admin/login", {"pin": "x"})
    assert post(phone_a, "/api/admin/login", {"pin": "1234"}).status_code == 429

def test_admin_disabled_without_pin(app_without_pin_client):
    assert post(app_without_pin_client, "/api/admin/login", {"pin": "1"}).status_code == 503

def test_sixth_song_and_duplicate_return_409_with_codes(phone_a, phone_b, songs):  # cap 5
    for i in range(5): post(phone_a, "/api/queue", {"song": f"s{i}.wav"})
    r = post(phone_a, "/api/queue", {"song": "s5.wav"})
    assert (r.status_code, r.json["code"]) == (409, "full")
    r = post(phone_b, "/api/queue", {"song": "s0.wav"})
    assert (r.status_code, r.json["code"]) == (409, "duplicate")

@pytest.mark.parametrize("bad", ["../x.mp3", "/etc/passwd", "reggaeton/../../x.mp3", "notes.txt"])
def test_traversal_returns_404_and_never_reaches_player(phone_a, player, app, bad):
    assert post(phone_a, "/api/queue", {"song": bad}).status_code == 404
    app.extensions["engine"].tick(); assert player.played == []

@pytest.mark.parametrize("body", [None, "just text", [1, 2], {}, {"song": 5}, {"song": None}])
def test_malformed_body_is_400_not_500(phone_a, body):
    r = phone_a.post("/api/queue", data=json.dumps(body), content_type="application/json")
    assert r.status_code == 400 and "error" in r.json

def test_non_json_content_type_is_400(phone_a):
    assert phone_a.post("/api/queue", data="song=a", content_type="text/plain").status_code == 400

def test_delete_unknown_id_is_404(phone_a): assert phone_a.delete("/api/queue/nope").status_code == 404

def test_upload_with_enqueue_adds_to_queue(phone_a):
    r = phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "n.mp3"), "enqueue": "1"})
    assert r.status_code == 201 and r.json["item"]["title"] == "n"

def test_upload_without_file_or_bad_type_is_400(phone_a):
    assert phone_a.post("/api/upload", data={}).status_code == 400
    assert phone_a.post("/api/upload", data={"song": (io.BytesIO(b"x"), "x.exe")}).status_code == 400

def test_oversized_upload_is_413_json(app_small_limit_client):  # max_upload_bytes = 1024
    r = app_small_limit_client.post("/api/upload", data={"song": (io.BytesIO(b"x" * 5000), "big.mp3")})
    assert r.status_code == 413 and "error" in r.json

def test_state_shape_and_unknown_route_json(phone_a):
    s = phone_a.get("/api/state").json
    assert set(s) == {"now_playing", "queue", "total_seconds", "me"}
    assert phone_a.get("/api/nope").json["error"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_api.py -q`
Expected: FAIL (`create_app` not defined).

- [ ] **Step 3: Implement `create_app` and `routes.py`**. Parse bodies with `request.get_json(silent=True)` and a single helper `json_object() -> dict` that raises a 400 for anything that is not a dict.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest -q`
Expected: all tests pass (Tasks 2-6).

- [ ] **Step 5: Commit**

```bash
git add caseta/__init__.py caseta/routes.py tests/test_api.py
git commit -m "Added fair queue HTTP API with ownership and admin rules"
```

---

### Task 7: Captive-portal redirect and production entry point

**Files:**
- Create: `caseta/portal.py`
- Modify: `caseta/__init__.py` (register portal), `app.py` (rewrite)
- Test: `tests/test_portal.py`

**Interfaces:**
- Consumes: `Config.allowed_hosts`, `Config.portal_url`.
- Produces: `init_portal(app: Flask, config: Config) -> None`: a `before_request` that takes `request.host` without its port, lowercased; if not in `config.allowed_hosts`, answers `302` to `config.portal_url`. Registered before identity, so such requests get no cookie. Phones' connectivity probes (`connectivitycheck.gstatic.com/generate_204`, `captive.apple.com/hotspot-detect.html`) hit unknown hosts, so the OS shows "sign in to network" and opens the app.
- `app.py` becomes: build `create_app()` and `waitress.serve(app, host="0.0.0.0", port=int(env CASETA_PORT or 5000), threads=8)` inside `if __name__ == "__main__":`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("host", ["connectivitycheck.gstatic.com", "captive.apple.com",
                                  "www.msftconnecttest.com", "example.org:80"])
def test_unknown_host_is_redirected_to_portal(app, host):
    r = app.test_client().get("/generate_204", headers={"Host": host})
    assert r.status_code == 302 and r.headers["Location"] == "http://10.42.0.1/"
    assert "Set-Cookie" not in r.headers

@pytest.mark.parametrize("host", ["localhost", "localhost:5000", "10.42.0.1", "CASETA.LOCAL"])
def test_known_hosts_are_served(app, host):
    assert app.test_client().get("/", headers={"Host": host}).status_code == 200

def test_entry_point_never_enables_debug():
    assert "debug=True" not in Path("app.py").read_text()
```

(`GET /` returns 200 once Task 9's `index.html` extends Task 8's base; until then render a plain placeholder template, `index.html` already exists and does not depend on the new base. The test passes at this point because the old template still renders.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_portal.py -q`
Expected: FAIL (redirect tests get 404/200).

- [ ] **Step 3: Implement `portal.py`, register it first in `create_app`, rewrite `app.py`.**

- [ ] **Step 4: Run to verify pass, then smoke-run the server**

Run: `python -m pytest -q`
Expected: all pass.
Run: `CASETA_ADMIN_PIN=1234 python app.py` (PowerShell: `$env:CASETA_ADMIN_PIN='1234'; python app.py`) then `curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/state`
Expected: `200`. Stop the server.

- [ ] **Step 5: Commit**

```bash
git add caseta/portal.py caseta/__init__.py app.py tests/test_portal.py
git commit -m "Added captive portal redirect and waitress entry point, removed debug server"
```

---

### Task 8: Offline assets and shared frontend modules

**Files:**
- Create: `templates/base.html`, `static/style.css`, `static/vendor/bulma.min.css`, `static/vendor/lobster.woff2`, `static/format.js`, `static/common.js`
- Test: `tests/test_offline_assets.py`, `tests/frontend/format.test.js`

**Interfaces:**
- Produces, `static/format.js` (classic script; defines global `Format`, and `module.exports = Format` when `module` exists):
  - `Format.formatEta(seconds: number) -> string`: `<60` gives `"menos de 1 min"`; `<3600` gives `"~N min"` (rounded); otherwise `"~H h MM min"` (minutes zero-padded to 2).
  - `Format.formatSummary(count: number, totalSeconds: number) -> string`: `count == 0` gives `"0 canciones en la cola"`; otherwise `"<count> canción|canciones en la cola | Quedan " + formatEta(totalSeconds)` (singular only for 1). E.g. `formatSummary(3, 3900)` is `"3 canciones en la cola | Quedan ~1 h 05 min"`.
- Produces, `static/common.js` (global `Common`):
  - `Common.api(method: string, url: string, body?: object | FormData) -> Promise<any>`: `fetch` wrapper; JSON bodies get `Content-Type: application/json`; resolves parsed JSON; on a non-2xx rejects with `ApiError` (`status: number`, `code: string`, `message: string` taken from the response's `code`/`error`).
  - `Common.el(tag: string, props?: object, ...children: (Node|string)[]) -> HTMLElement`: builds DOM with `textContent` only (never `innerHTML`); `props.class`, `props.onclick`, `props.dataset` supported.
  - `Common.startPolling(fn: () => Promise<void>, ms: number) -> () => void`: runs `fn` immediately and every `ms`; never overlaps runs; skips ticks while `document.hidden`; returns a stop function.
  - `Common.toast(message: string, kind: "info"|"danger"|"success" = "info") -> void`: Bulma `notification` pinned to the top, auto-dismiss after 4 s. Replaces every `alert()`.
- Produces `templates/base.html`: Jinja base with blocks `title`, `body`, `scripts`; links `/static/vendor/bulma.min.css`, `/static/style.css`, loads `format.js` and `common.js`; carries the red-circle background and `.header-title` styling moved out of the two inline `<style>` blocks into `style.css` (`@font-face` for `Lobster` from `/static/vendor/lobster.woff2`; body font is the system sans-serif stack).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_offline_assets.py
def test_templates_and_css_reference_no_remote_urls():
    for f in [*Path("templates").glob("*.html"), Path("static/style.css")]:
        assert not re.search(r"(src|href|url\()\s*=?\s*[\"']?https?://", f.read_text()), f

def test_vendored_assets_exist():
    for p in ("static/vendor/bulma.min.css", "static/vendor/lobster.woff2"):
        assert Path(p).stat().st_size > 1000
```

```js
// tests/frontend/format.test.js  (node:test + node:assert)
test("formatEta", () => {
  assert.equal(Format.formatEta(0), "menos de 1 min");
  assert.equal(Format.formatEta(59), "menos de 1 min");
  assert.equal(Format.formatEta(150), "~3 min");        // 2.5 rounds up
  assert.equal(Format.formatEta(3900), "~1 h 05 min");
  assert.equal(Format.formatEta(7200), "~2 h 00 min");
});
test("formatSummary", () => {
  assert.equal(Format.formatSummary(0, 0), "0 canciones en la cola");
  assert.equal(Format.formatSummary(1, 200), "1 canción en la cola | Quedan ~3 min");
  assert.equal(Format.formatSummary(3, 3900), "3 canciones en la cola | Quedan ~1 h 05 min");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_offline_assets.py -q` and `node --test tests/frontend/`
Expected: FAIL (existing templates still reference CDNs; `format.js` missing).

- [ ] **Step 3: Vendor the assets.**

Run: `curl -L -o static/vendor/bulma.min.css https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css`
Then fetch `https://fonts.googleapis.com/css2?family=Lobster` with a modern `User-Agent` header, take the `woff2` URL it contains, and save that file as `static/vendor/lobster.woff2`.

- [ ] **Step 4: Implement `format.js`, `common.js`, `style.css`, `base.html`.** Leave `index.html`/`admin.html` untouched until Tasks 9-10 (the CDN test stays red until then; Step 5 of Task 10 runs it green).

- [ ] **Step 5: Run the node test**

Run: `node --test tests/frontend/`
Expected: 2 passed. (`test_templates_and_css_reference_no_remote_urls` goes green in Task 10.)

- [ ] **Step 6: Commit**

```bash
git add templates/base.html static/style.css static/vendor static/format.js static/common.js tests/test_offline_assets.py tests/frontend
git commit -m "Added local assets and shared frontend modules"
```

---

### Task 9: User page (phones)

**Files:**
- Modify: `templates/index.html` (extends `base.html`), `static/main.js` (rewrite)

**Interfaces:**
- Consumes: `/api/songs`, `/api/state`, `POST /api/queue`, `DELETE /api/queue/<id>`, `POST /api/upload` (Task 6); `Common.*`, `Format.*` (Task 8).
- Page behavior (the contract; a checker should be able to verify each line in a browser):
  - Polls `/api/state` every 3 s via `Common.startPolling`; one request per tick. Songs list loads once and again after an upload.
  - Library table: search box, category buttons, pagination of 20 (existing behavior). A song already in `state.queue` or playing shows a disabled `"En la cola"` button instead of `"Añadir"`.
  - `"Añadir"` posts and refreshes state immediately. On 409 `full`: toast `"Ya tienes 5 canciones en la cola. Espera a que suene alguna."` (use `state.me.max`); on 409 `duplicate`: toast `"Esa canción ya está en la cola."`.
  - Queue box: the playing song on top with a `"Sonando"` tag; each row shows `Format.formatEta(eta_seconds)`; the viewer's own rows carry a `"Tuya"` tag and a `"Quitar"` button; other rows have no button. All rows built with `Common.el` (no `innerHTML`).
  - Banner above the queue: when the viewer has a pending song, `"Tu próxima canción suena en ~N min"` (first `mine` entry's ETA); if only their own song is playing, `"Tu canción está sonando"`; else hidden. A counter `"Tienes X de 5 canciones en la cola"` from `state.me`.
  - Footer line: `Format.formatSummary(queue.length + (now_playing ? 1 : 0), total_seconds)`.
  - Upload: file input + checkbox `"Añadir a la cola al subir"` (checked by default); button disables and shows `"Subiendo…"` during the request; on success a toast `"Canción subida"`, switch to category `Subidas`; on failure the server's `error` as a danger toast.
  - Polling failure (server unreachable) shows a persistent `"Sin conexión con la caseta"` notice that clears on the next success.

- [ ] **Step 1: Rewrite `index.html` and `main.js`** per the contract.

- [ ] **Step 2: Manual check with two "phones"**

Run: `CASETA_ADMIN_PIN=1234 python app.py` with some `.mp3`/`.wav` files under `songs/Rock/`. (`PygamePlayer` only touches the audio device when the first song plays, so the pages work even on a machine without one.)
Open `http://localhost:5000` in a normal window and a private window (separate cookies). Verify: A adds 3 songs, B adds 1: B's song is second in both windows; A has no `"Quitar"` on B's row and vice versa; the 6th add from one window shows the cap toast; adding a queued song is disabled.
Expected: all five behaviors observed. (Use the built-in browser tools to screenshot both.)

- [ ] **Step 3: Commit**

```bash
git add templates/index.html static/main.js
git commit -m "Rebuilt user page on shared state with ownership and ETAs"
```

---

### Task 10: Admin page

**Files:**
- Modify: `templates/admin.html` (extends `base.html`), `static/admin.js` (rewrite)

**Interfaces:**
- Consumes: `GET /api/admin/session`, `POST /api/admin/login`, `GET /api/state`, `DELETE /api/queue/<id>`, `POST /api/queue/<id>/move`, `POST /api/skip`.
- Page behavior:
  - On load calls `/api/admin/session`; if `admin` is false, shows only a PIN form (password input + `"Entrar"`). Wrong PIN shows `"PIN incorrecto"`; 429 shows `"Demasiados intentos. Espera un minuto."`; 503 shows `"El administrador no está configurado en el servidor"`.
  - Once admin: queue with `"Eliminar"` on every row (including the playing song), a `"Saltar canción"` button, and the same library/add panel as the user page (reuse `Common`, no copy of the logic).
  - Reorder by drag and drop (mouse HTML5 drag and touch events) of queued rows (not the playing one). Dropping a row on the row at index `i` of `state.queue` calls `POST /api/queue/<id>/move` with `{"position": i + 1}` (1-based among queued songs, playing song excluded).
  - While a drag is active, polling still runs but the queue DOM is not replaced (a `dragging` flag skips the re-render), then one refresh happens on drop.

- [ ] **Step 1: Rewrite `admin.html` and `admin.js`.**

- [ ] **Step 2: Manual check**

Run the app as in Task 9. Verify: the admin page shows the PIN form; a wrong PIN shows the error; `1234` shows the queue. As admin remove a song added from the other window; drag the last queued song to the top (position 1) and confirm both windows show the new order within 3 s; `"Saltar canción"` moves to the next song.
Expected: all observed.

- [ ] **Step 3: Run everything**

Run: `python -m pytest -q && node --test tests/frontend/`
Expected: all pass, including `test_templates_and_css_reference_no_remote_urls` (no CDN links left).

- [ ] **Step 4: Commit**

```bash
git add templates/admin.html static/admin.js
git commit -m "Rebuilt admin page with PIN login, skip and id-based reorder"
```

---

### Task 11: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`** (English; UI stays Spanish) covering: what the project is; how to add music (`songs/<Category>/file.mp3`); the env var table from Global Constraints; the fairness rules (round-robin, cap 5, no duplicates, own songs only, admin PIN); `python app.py` and test commands; a pointer to the Pi deployment plan.

- [ ] **Step 2: Verify the README's commands work from a clean clone**

Run (after the commit in Step 3, so everything is in HEAD): `git clone . ../caseta-check && cd ../caseta-check && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest -q`
Expected: tests pass in the clean clone (proves no dependency on the old committed venv). Delete `../caseta-check` afterwards.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Added README"
```

---

## Self-Review

- **Spec coverage:** no jumping (Tasks 2, 6: `position` ignored, move admin-only); no removing others' songs (2, 4, 6); same-song/spam control (2, 6); phones can upload (3, 6, 9); works offline (8, 10); wait estimates (3, 4, 9); security holes 6-8 (6, 7); hygiene (1). The Pi hotspot/captive portal/systemd side is the second plan, and the host redirect it relies on is Task 7.
- **Type consistency:** `QueueItem.id` is a `str` everywhere (Tasks 2, 4, 6, 9, 10); `snapshot(viewer)` keys match what Tasks 9 and 10 read (`now_playing`, `queue[].mine`, `eta_seconds`, `total_seconds`, `me.pending/max`); `move` position is 1-based among queued songs in Tasks 2, 4, 6, 10.
- **Known weak spot:** frontend behavior (Tasks 9, 10) is verified manually. There is no browser test harness; adding Playwright was judged out of proportion for ~350 lines of JS.
