# Caseta

Caseta is a shared jukebox for a party or a small venue. A Raspberry Pi plays music through its speakers, and everyone who joins the Pi's Wi-Fi hotspot picks songs from their own phone. The queue is fair: each phone gets a turn in rotation, so one person cannot monopolise the speakers.

The web UI is in Spanish. This README is in English.

## Hardware and OS context

- Target: a Raspberry Pi with built-in Wi-Fi (3B+, 4, 5 or Zero 2 W) running Raspberry Pi OS Bookworm or newer, with speakers on its audio output.
- The Pi runs its own Wi-Fi hotspot (`10.42.0.1`), and the app answers every other hostname with a redirect to the jukebox page, so phones show the "sign in to network" popup automatically.
- Audio is played by `pygame.mixer`; the app is served by `waitress`. It works with zero internet: no external URL is referenced by any page.

The Pi-side setup (hotspot, DNS, systemd unit) is described in [`docs/superpowers/plans/2026-10-05-pi-hotspot-deployment.md`](docs/superpowers/plans/2026-10-05-pi-hotspot-deployment.md). The design of the app itself is in [`docs/superpowers/plans/2026-10-05-fair-shared-queue.md`](docs/superpowers/plans/2026-10-05-fair-shared-queue.md).

## Adding music

Put audio files in category folders under `songs/`:

```
songs/
  Reggaeton/
    some-song.mp3
  Rock/
    another-song.ogg
```

- Supported formats: `mp3`, `wav`, `ogg`. `m4a` and `flac` are not supported.
- Each subfolder is a category in the UI. The folder is scanned on every request, so new files appear without a restart.
- `songs/` is not committed to git (it is in `.gitignore`).
- Songs uploaded from a phone land in `songs/Subidas/`. They are saved under a safe name; if the name is taken, a numeric suffix is added and nothing is overwritten.

## Configuration

All settings are environment variables. Only `CASETA_ADMIN_PIN` is needed for a normal setup.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CASETA_ADMIN_PIN` | unset | PIN for the admin page. If unset, admin mode is disabled (login answers 503) and the app prints a warning at startup. Never commit it. |
| `CASETA_MAX_PENDING` | `5` | Maximum songs one phone can have waiting in the queue at once. Must be an integer >= 1. |
| `CASETA_MAX_UPLOAD_MB` | `30` | Maximum upload size in MB. Larger uploads get a 413 JSON error. Must be an integer >= 1. |
| `CASETA_PORT` | `5000` | TCP port the server listens on (all interfaces). On the Pi it is set to 80. |
| `CASETA_SONG_DIR` | `songs` | Folder that holds the music, relative to the working directory or absolute. |

An invalid value (for example `CASETA_PORT=abc`) makes `app.py` print an error and exit with status 2.

## Fairness rules

- **Round-robin by phone.** Each phone's first queued song goes in round 1, its second in round 2, and so on. Songs play round by round, so a phone that adds 20 songs does not delay another phone's first song past the current round.
- **Cap per phone.** A phone can have at most `CASETA_MAX_PENDING` (default 5) songs waiting. The next attempt gets a 409 with code `full`. The song currently playing no longer counts.
- **No duplicates.** A song that is already waiting in the queue cannot be added again (409, code `duplicate`).
- **Remove only your own songs.** You can remove or stop only songs your phone added. Other phones' songs answer 403. The admin can remove anything.
- **No cutting in line.** Clients cannot choose a position; any `position` sent when adding is ignored. Only the admin can reorder.
- **Admin.** The admin page is at `/albertitoeselmejor` (it is not linked from the main page). Logging in needs `CASETA_ADMIN_PIN`. After 5 wrong PINs from the same IP address, that address is locked out for 60 seconds. The admin can skip the current song, remove any song, and move songs to a position. The admin login is a browser-session cookie: it ends when the browser is closed or the server restarts.

## API summary

All API errors are JSON: `{"error": "<Spanish message>", "code": "<code>"}`.

| Method | Path | Who may call it |
| --- | --- | --- |
| GET | `/` | anyone (user page) |
| GET | `/albertitoeselmejor` | anyone (admin page; login happens inside it) |
| GET | `/api/songs` | anyone (list of available songs) |
| GET | `/api/state` | anyone (now playing, queue with ETAs, your pending count and cap) |
| POST | `/api/queue` | anyone (body `{"song": "<Category>/file.mp3"}`) |
| DELETE | `/api/queue/<id>` | the phone that added it, or the admin |
| POST | `/api/upload` | anyone (multipart field `song`; optional form field `enqueue=1`) |
| POST | `/api/admin/login` | anyone who knows the PIN (body `{"pin": "..."}`) |
| GET | `/api/admin/session` | anyone (reports whether this browser is admin) |
| POST | `/api/queue/<id>/move` | admin only (body `{"position": <int>}`, 1 = next) |
| POST | `/api/skip` | admin only |

## Running

Create a virtual environment and install the dependencies:

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows
.venv/bin/python -m pip install -r requirements.txt         # Linux / Raspberry Pi
```

Start the server (Python 3.11):

```
.venv/Scripts/python app.py      # Windows
.venv/bin/python app.py          # Linux / Raspberry Pi
```

Then open `http://localhost:5000/`. To enable the admin page, set the PIN first, for example `CASETA_ADMIN_PIN=1234 .venv/bin/python app.py` (bash) or `$env:CASETA_ADMIN_PIN = "1234"` (PowerShell).

On a machine without an audio device the server still starts; a song that cannot be played is dropped from the queue and the next one starts.

## Testing

```
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/frontend/
```

Run these with the virtual environment's Python (`.venv/Scripts/python -m pytest -q` on Windows, `.venv/bin/python -m pytest -q` on Linux). The Python tests use a fake audio player, so they need no sound hardware. The frontend tests use Node's built-in test runner, so they need Node.js 18 or newer and no `npm install`.

## Known limitations

- **Identity is a cookie.** A "phone" is a random id stored in a cookie (`caseta_client`, valid one year). Clearing cookies, using a private tab or switching browsers creates a new identity, which bypasses the per-phone cap and the round-robin. Fairness is for a friendly crowd, not a defence against someone determined to cheat.
- **iOS captive-portal mini-browser has its own cookie jar.** A phone that adds songs in the popup and then in Safari looks like two different phones, so it can reach the cap twice and cannot remove songs it added from the other browser. Opening the page in the full browser from the start avoids this.
- **Host redirect affects testing.** Any request whose `Host` is not `localhost`, `127.0.0.1`, `10.42.0.1` or `caseta.local` is redirected (302) to `http://10.42.0.1/`. Opening the app from another machine by its LAN IP (for example `http://192.168.1.20:5000/`) therefore bounces to the portal URL instead of loading. Test with `localhost`, or on the Pi's hotspot.
- **Unsupported formats.** `m4a` (the default for many iPhone recordings) and `flac` are rejected at upload and not listed.
- **The queue is not persisted.** It lives in memory; restarting the server empties it and stops the current song. Admin logins also end on restart.
- **Admin lockout is per IP address.** Phones behind the same address share the counter.
- **Song durations and ETAs are estimates.** Durations are read from file metadata; if a file's length cannot be read, 180 seconds is assumed.
