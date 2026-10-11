# Caseta

Caseta is a shared jukebox for a party or a small venue. One machine (the target is a Raspberry Pi) plays music through its speakers, and everyone on the same network picks songs from their own phone's browser. The queue is first come, first served: songs play in the order they were added, whoever added them.

The web UI is in Spanish. This README is in English.

## Hardware and OS context

- Target: a Raspberry Pi with built-in Wi-Fi (3B+, 4, 5 or Zero 2 W) running Raspberry Pi OS Bookworm or newer, with speakers on its audio output.
- Planned (see the deployment plan below, not set up by this repo yet): the Pi runs its own Wi-Fi hotspot at `10.42.0.1` and, because the app answers unknown host names with a redirect to the jukebox page, phones show the "sign in to network" popup automatically. Until then, phones on any shared Wi-Fi can open the app by the machine's IP address.
- Audio is played by `pygame.mixer`; the app is served by `waitress`. It works with zero internet: no external URL is referenced by any page.

The planned Pi-side setup (hotspot, DNS, systemd unit) is described in [`docs/superpowers/plans/2026-10-05-pi-hotspot-deployment.md`](docs/superpowers/plans/2026-10-05-pi-hotspot-deployment.md). The design of the app itself is in [`docs/superpowers/plans/2026-10-05-fair-shared-queue.md`](docs/superpowers/plans/2026-10-05-fair-shared-queue.md) (the round-robin ordering described there was replaced by first come, first served; see Queue rules below).

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
- If an uploaded file is byte for byte the same as a song the library already has, the new file is discarded and the existing song is used instead (with "add to queue" ticked, that existing song is queued). The upload answer has `"existing": true` and the page says "Esa canción ya estaba en la biblioteca".
- To look for repeated songs, see [Finding repeated songs](#finding-repeated-songs).

## Finding repeated songs

```
python -m tools.find_duplicates                 # audit the library
python -m tools.find_duplicates --all           # also list the same title by other artists
python -m tools.find_duplicates --check NEW...  # are these files or folders already in the library?
```

Run it with the virtual environment's Python from the project folder. It only reports; it never deletes or moves anything. The folder is `CASETA_SONG_DIR` (default `songs`), or `--songs <folder>`.

- **Exact copies**: files with identical content, for example the same song in two section folders. The app already treats these as one song (see Queue rules), so they are harmless to playback, but you may want to keep only one.
- **Probably the same song**: same artist and title once case, accents and decoration such as "(Letra)" or "[Video Oficial]" are ignored. These are different files (for example two downloads of the same song), so the app plays them as two songs. Delete the one you do not want by hand. Check each one first: a "(Versión Salsa)" and an original are different recordings.
- **Same title, different artists** (only with `--all`): usually different songs that happen to share a name.
- `--check` compares new music with the library *before* you copy it in. It prints `EXACT` (same content) or `SIMILAR` (same artist and title) for each file and exits with status 1 if there is any, so it can be used in a script.

## Configuration

All settings are environment variables. Only `CASETA_ADMIN_PIN` is needed for a normal setup.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CASETA_ADMIN_PIN` | unset | PIN for the admin page. If unset, admin mode is disabled (login answers 503) and the app prints a warning at startup. Never commit it. |
| `CASETA_MAX_PENDING` | `5` | Maximum songs one phone can have waiting in the queue at once. Must be an integer >= 1. |
| `CASETA_MAX_UPLOAD_MB` | `30` | Maximum upload size in MB. Larger uploads get a 413 JSON error. Must be an integer >= 1. |
| `CASETA_REPLAY_BLOCK_MINUTES` | `120` | How long a song that just played cannot be added again, in minutes. `0` turns the block off. Must be an integer >= 0. |
| `CASETA_PORT` | `5000` | TCP port the server listens on (all interfaces). The planned Pi setup uses 80. |
| `CASETA_SONG_DIR` | `songs` | Folder that holds the music, relative to the working directory or absolute. |
| `CASETA_ALLOWED_HOSTS` | unset | Extra host names to serve instead of redirecting, comma-separated (for example `jukebox.lan,mi-pc`). Spaces are trimmed, case is ignored, empty items are skipped. They are added to the built-in `localhost`, `127.0.0.1`, `10.42.0.1` and `caseta.local`. IP addresses never need listing. |

An invalid value (for example `CASETA_PORT=abc`) makes `app.py` print an error and exit with status 2.

## Queue rules

- **First come, first served.** Songs play in the order they were added. If you add 5 songs and someone else then adds 5 more, yours are positions 1 to 5 and theirs are 6 to 10. Nobody's song is ever placed in front of one that was added earlier.
- **Cap per phone.** A phone can have at most `CASETA_MAX_PENDING` (default 5) songs waiting. The next attempt gets a 409 with code `full`. The song currently playing no longer counts, so you can add another one as soon as yours starts. **The admin has no cap**: once logged in on the admin page, adding songs, uploading with "add to queue" and shuffling are not limited.
- **No duplicates.** A song that is already waiting in the queue cannot be added again (409, code `duplicate`). Two files with exactly the same content count as the same song, even in different folders or under different names.
- **No repeats tonight.** A song that has started playing, whether someone added it or shuffle picked it, cannot be added again for `CASETA_REPLAY_BLOCK_MINUTES` (default 120, so 2 hours): 409, code `recently_played`, with `remaining_seconds` and a message saying how many minutes are left. A copy of that song is blocked too. The admin is not limited. A song that fails to play does not count as played. Shuffle prefers songs that did not play recently; if every song in the section did (a small section, or a long night), it plays the one that rested longest instead of stopping.
- **Remove only your own songs.** You can remove or stop only songs your phone added. Other phones' songs answer 403. Removing a song just closes the gap; everyone else keeps their order.
- **Shuffle ("Aleatorio") is a mode, not a button that adds a few songs.** Press it once and random songs keep playing, endlessly, until it is turned off. It plays the section that is selected: with "Todas" it draws from the whole library, with a specific section (for example "Flamenquito") only from that section. The search box is ignored.
  - **Turning it off.** The button is a toggle: while it is on it reads "Aleatorio activo" and is filled red, and pressing it again stops it. A bar above the player ("Aleatorio activo: Flamenquito") with a "Detener" button is visible on both pages for as long as the mode runs, so on a phone you never have to scroll to the library to stop it. The song that is playing finishes, then nothing new starts.
  - **Songs added by hand always come first.** A random song is picked only when the queue is empty, so the queue stays first come, first served and shuffle never delays anyone's song.
  - **No repeats until the section is used up.** Every song in the section plays once, in random order, before any song plays again, and the same song never plays twice in a row.
  - **One shuffle at a time, owned by whoever started it.** Only the phone that started it (or the admin) can stop it or switch it to another section; other phones see the bar without the button, and starting it from another phone answers 409 `shuffle_locked`. Once it is off, anyone can start it again.
  - **Random songs do not use the cap** (they are never in the queue). The starter can skip a random song they dislike with "Quitar", like any song of their own, and the loop carries on with the next one.
  - If the audio output is unavailable, shuffle waits like the rest of the queue. If the section runs out of songs (files deleted), shuffle turns itself off. The mode is kept in memory only and ends when the server restarts.
- **No cutting in line.** Clients cannot choose a position; any `position` sent when adding is ignored. Only the admin can reorder.
- **Admin.** The admin page is at `/albertitoeselmejor` (it is not linked from the main page). Logging in needs `CASETA_ADMIN_PIN`. After 5 wrong PINs from the same IP address, that address is locked out for 60 seconds. The admin can skip the current song, remove any song, and move a song to any position. Songs added later always go to the end. The admin login is a browser-session cookie: it ends when the browser is closed or the server restarts.

## API summary

All API errors are JSON: `{"error": "<Spanish message>", "code": "<code>"}`.

| Method | Path | Who may call it |
| --- | --- | --- |
| GET | `/` | anyone (user page) |
| GET | `/albertitoeselmejor` | anyone (admin page; login happens inside it) |
| GET | `/api/songs` | anyone (list of available songs) |
| GET | `/api/state` | anyone (now playing, queue with ETAs, your pending count and cap (`null` for the admin), `audio_ok`, and `shuffle`: `null` or `{category, can_stop}`) |
| POST | `/api/queue` | anyone (body `{"song": "<Category>/file.mp3"}`) |
| DELETE | `/api/queue/<id>` | the phone that added it, or the admin |
| POST | `/api/shuffle` | anyone when shuffle is off; when it is on, only the phone that started it or the admin (body `{"category": "Todas"}` or a section name; turns shuffle on or switches its section) |
| DELETE | `/api/shuffle` | the phone that started shuffle, or the admin (turns it off; fine if it is already off) |
| POST | `/api/upload` | anyone (multipart field `song`; optional form field `enqueue=1`; the answer has `existing: true` when the library already had that exact song, and `song` then names that one) |
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

On a machine without a usable audio device the server still starts. While the audio output is unavailable (no sound device, or the mixer cannot start), songs are not dropped: they wait in the queue in the same order, the server logs the problem once and retries every 5 seconds, `/api/state` reports `"audio_ok": false`, and both pages show "Sin salida de audio: las canciones esperan". Playback resumes with the first waiting song as soon as the device works. A single file that cannot be decoded is still dropped, and the next song starts.

## Testing

```
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/frontend/
```

Run these with the virtual environment's Python (`.venv/Scripts/python -m pytest -q` on Windows, `.venv/bin/python -m pytest -q` on Linux). The Python tests use a fake audio player, so they need no sound hardware. The frontend tests use Node's built-in test runner, so they need Node.js 18 or newer and no `npm install`.

## Known limitations

- **Identity is a cookie.** A "phone" is a random id stored in a cookie (`caseta_client`, valid one year). Clearing cookies, using a private tab or switching browsers creates a new identity, which bypasses the per-phone cap (the order is always first come, first served). The cap is for a friendly crowd, not a defence against someone determined to cheat.
- **iOS captive-portal mini-browser has its own cookie jar** (relevant once the planned hotspot is set up). A phone that adds songs in the popup and then in Safari looks like two different phones, so it can reach the cap twice and cannot remove songs it added from the other browser. Opening the page in the full browser from the start avoids this.
- **Unknown host names are redirected.** A request whose `Host` is a host name other than `localhost`, `127.0.0.1`, `10.42.0.1`, `caseta.local` or one listed in `CASETA_ALLOWED_HOSTS` is redirected (302) to `http://10.42.0.1/` (the planned hotspot address). A `Host` that is an IP address (for example `http://192.168.1.20:5000/` or `http://[fe80::1]:5000/`) is always served, so on a home or venue Wi-Fi open the app by the machine's IP. Reaching it by a router or mDNS name that is not in the list needs that name in `CASETA_ALLOWED_HOSTS`.
- **Unsupported formats.** `m4a` (the default for many iPhone recordings) and `flac` are rejected at upload and not listed.
- **The queue is not persisted.** It lives in memory; restarting the server empties it and stops the current song. Admin logins also end on restart, and so does the memory of what played tonight, so every song can be added again right after a restart.
- **Only identical files count as the same song.** The same song downloaded twice from different places is two different files, so the queue and the replay block treat them as two songs. `python -m tools.find_duplicates` lists these as "probably the same song". Remixes, covers and live versions are different recordings and are never merged.
- **Admin lockout is per IP address.** Phones behind the same address share the counter.
- **Song durations and ETAs are estimates.** Durations are read from file metadata; if a file's length cannot be read, 180 seconds is assumed.
