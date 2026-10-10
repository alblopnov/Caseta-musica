# Raspberry Pi Hotspot Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Raspberry Pi that boots unattended, opens its own Wi-Fi, makes phones pop up the music page automatically, and plays through the connected speakers.

**Architecture:** NetworkManager's built-in hotspot (shared mode, so it provides DHCP and DNS through its own dnsmasq) gives the Pi a fixed address `10.42.0.1`. A wildcard DNS rule sends every hostname to the Pi, and the app's host-redirect (Task 7 of the app plan) turns phones' internet-connectivity probes into the "sign in to network" popup. A systemd unit runs `app.py` under waitress on port 80.

**Tech Stack:** Raspberry Pi OS Bookworm (NetworkManager), nmcli, dnsmasq (via NetworkManager), systemd, ALSA/SDL audio, bash.

**Spec:** The user's objective (phones join the Pi's Wi-Fi and control the sound system) and the repo analysis in `docs/superpowers/plans/2026-10-05-fair-shared-queue.md`. **Prerequisite:** that plan is implemented (the app runs with `python app.py`, honours `CASETA_PORT`, `CASETA_ADMIN_PIN`, `CASETA_SONG_DIR`, and redirects unknown hosts to `http://10.42.0.1/`).

## Global Constraints

- Hardware: a Pi with built-in Wi-Fi (3B+, 4, 5, or Zero 2 W) running **Raspberry Pi OS Bookworm or newer** (earlier releases use dhcpcd/hostapd and these files do not apply). Use the Lite image: no desktop audio server in the way.
- Hotspot SSID `CasetaMusica`, address `10.42.0.1/24`, WPA2 password supplied by the owner in `/etc/caseta.env` (`CASETA_WIFI_PASSWORD`), never committed.
- The service runs as the non-root user that owns the repo, with `AudioDevice` access via the `audio` group; port 80 is bound through `AmbientCapabilities=CAP_NET_BIND_SERVICE`, not by running as root.
- All secrets live in `/etc/caseta.env` (mode `600`): `CASETA_ADMIN_PIN`, `CASETA_WIFI_PASSWORD`.
- Everything here is verified on the Pi or on phones. There is no way to unit-test it on the dev machine; each task ends with an on-device check and its expected result.
- Deliverables are plain files under `deploy/` so the setup is reproducible from a fresh SD card.

## Review Focus

1. **Audio device wrong or missing at boot** (HDMI vs headphone jack vs USB DAC vs Bluetooth): the service must still start and the page must work; the owner must be able to pick the device with one env var. Task 2.
2. **Pi boots before the hotspot is up**, or the Wi-Fi interface is blocked by `rfkill`/country not set: the hotspot must come back on every boot without a keyboard. Task 3.
3. **Phones that connect but never show the popup** (iOS captive mini-browser dismissed, Android keeps traffic on mobile data): a printed/QR fallback URL must exist. Tasks 3 and 4.
4. **Power pulled during playback or an upload** (SD card corruption): note the risk and keep `songs/` writes small. Task 4.
5. **Many phones at once** (10-20 on the Pi's radio) while a song plays: audio must not stutter. Task 4 load check.

---

## File Structure

```
deploy/install.sh            one-shot installer (venv, deps, unit, hotspot)
deploy/caseta.service        systemd unit
deploy/caseta.env.example    env template (copied to /etc/caseta.env)
deploy/hotspot.sh            creates/updates the NetworkManager hotspot profile
deploy/caseta-dns.conf       wildcard DNS for NetworkManager's dnsmasq
deploy/README.md             owner's guide: flashing, setup, QR codes, troubleshooting
```

---

### Task 1: Install the app on the Pi

**Files:**
- Create: `deploy/install.sh`

**Interfaces:**
- Produces: `deploy/install.sh` (run as the normal user with `sudo` available) that: installs apt packages `python3-venv python3-dev libsdl2-mixer-2.0-0 alsa-utils qrencode`; creates `.venv` in the repo and installs `requirements.txt`; creates `songs/` if missing; copies `deploy/caseta.env.example` to `/etc/caseta.env` only if absent (mode 600); installs the unit and hotspot files (Tasks 2-3) and enables them. Idempotent: running it twice changes nothing the second time.

- [ ] **Step 1: Write `deploy/install.sh`** per the Interfaces block (`set -euo pipefail`; guard each step with an existence check).

- [ ] **Step 2: Run on the Pi**

Run: `git clone <repo> ~/Caseta-musica && cd ~/Caseta-musica && bash deploy/install.sh`
Expected: finishes without error; `.venv/bin/python -c "import flask, pygame, mutagen, waitress"` exits 0.

- [ ] **Step 3: Run it a second time**

Run: `bash deploy/install.sh`
Expected: no errors, `/etc/caseta.env` content unchanged (`sudo md5sum /etc/caseta.env` identical before and after).

- [ ] **Step 4: Commit**

```bash
git add deploy/install.sh
git commit -m "Added Pi install script"
```

---

### Task 2: systemd service and audio output

**Files:**
- Create: `deploy/caseta.service`, `deploy/caseta.env.example`

**Interfaces:**
- Produces `deploy/caseta.service`: `User=<owner>` (install.sh substitutes it), `WorkingDirectory=<repo>`, `EnvironmentFile=/etc/caseta.env`, `ExecStart=<repo>/.venv/bin/python app.py`, `Restart=always`, `RestartSec=3`, `AmbientCapabilities=CAP_NET_BIND_SERVICE`, `SupplementaryGroups=audio`, `After=network.target sound.target`.
- Produces `deploy/caseta.env.example` with: `CASETA_PORT=80`, `CASETA_ADMIN_PIN=change-me`, `CASETA_WIFI_PASSWORD=change-me-8chars-min`, `SDL_AUDIODRIVER=alsa`, `AUDIODEV=default` (comment lists how to find the device: `aplay -l`, then `hw:<card>,<device>` for USB DAC/HDMI), `CASETA_MAX_PENDING=5`.

- [ ] **Step 1: Write both files** per the Interfaces block.

- [ ] **Step 2: Start it and check it serves**

Run: `sudo systemctl enable --now caseta && sleep 3 && curl -s -o /dev/null -w "%{http_code}" http://localhost/api/state`
Expected: `200`. `systemctl is-active caseta` prints `active`.

- [ ] **Step 3: Check real audio** (Review Focus 1)

Copy a short `.mp3` into `songs/Test/`, add it from a browser at `http://<pi-ip>/`.
Expected: sound from the intended output. If silent: `aplay -l`, set `AUDIODEV=hw:<card>,<device>` in `/etc/caseta.env`, `sudo systemctl restart caseta`, retry. Then unplug the speaker/DAC and reboot: `systemctl is-active caseta` must still say `active` and `/api/state` must answer.

- [ ] **Step 4: Commit**

```bash
git add deploy/caseta.service deploy/caseta.env.example
git commit -m "Added systemd service and audio configuration"
```

---

### Task 3: Hotspot and captive portal

**Files:**
- Create: `deploy/hotspot.sh`, `deploy/caseta-dns.conf`

**Interfaces:**
- Produces `deploy/hotspot.sh` (run with `sudo`; reads `CASETA_WIFI_PASSWORD` from `/etc/caseta.env`, aborts if shorter than 8 characters): sets the Wi-Fi country (`raspi-config nonint do_wifi_country ES` unless `WIFI_COUNTRY` is set), runs `rfkill unblock wifi`, then creates or replaces the NetworkManager connection named `CasetaMusica`: `nmcli connection add type wifi ifname wlan0 con-name CasetaMusica ssid CasetaMusica mode ap ipv4.method shared ipv4.addresses 10.42.0.1/24 wifi-sec.key-mgmt wpa-psk wifi-sec.psk <password> connection.autoconnect yes connection.autoconnect-priority 100`, and brings it up. Idempotent (deletes the existing profile of that name first).
- Produces `deploy/caseta-dns.conf` installed to `/etc/NetworkManager/dnsmasq-shared.d/caseta.conf`: `address=/#/10.42.0.1` (every hostname resolves to the Pi).

- [ ] **Step 1: Write both files** per the Interfaces block; have `install.sh` copy the DNS file and call `hotspot.sh`.

- [ ] **Step 2: Bring the hotspot up**

Run: `sudo bash deploy/hotspot.sh && nmcli -f GENERAL.STATE,IP4.ADDRESS connection show CasetaMusica`
Expected: state `activated`, address `10.42.0.1/24`. (If SSH was over Wi-Fi it drops here: use Ethernet or a console for setup.)

- [ ] **Step 3: Verify from a phone** (Review Focus 3)

Join `CasetaMusica` from an Android phone and an iPhone.
Expected: both show a "sign in to network" prompt that opens the music page; opening `http://anything.example` in the browser also lands on the page. If the iPhone's popup closes without showing the app, `http://10.42.0.1/` in Safari works.

- [ ] **Step 4: Verify it survives a reboot** (Review Focus 2)

Run: `sudo reboot`, wait 60 s with no keyboard attached.
Expected: the `CasetaMusica` SSID appears again on the phone and the page loads without anyone logging into the Pi.

- [ ] **Step 5: Commit**

```bash
git add deploy/hotspot.sh deploy/caseta-dns.conf deploy/install.sh
git commit -m "Added NetworkManager hotspot and wildcard DNS captive portal"
```

---

### Task 4: Owner's guide and acceptance run

**Files:**
- Create: `deploy/README.md`

**Interfaces:**
- Produces `deploy/README.md`: flashing Bookworm Lite with Raspberry Pi Imager (enable SSH, set Wi-Fi country); `git clone` and `bash deploy/install.sh`; editing `/etc/caseta.env`; copying music to `songs/<Category>/`; generating two QR codes with `qrencode -t ANSIUTF8` / `-o caseta-wifi.png` (`WIFI:T:WPA;S:CasetaMusica;P:<password>;;` and `http://10.42.0.1/`) to print and stick on the speaker; troubleshooting (no sound, no popup, forgot PIN, how to read logs: `journalctl -u caseta -f`); a warning that cutting power during an upload can corrupt the SD card and that `sudo shutdown now` is the safe stop.

- [ ] **Step 1: Write `deploy/README.md`** per the Interfaces block.

- [ ] **Step 2: Acceptance run** (Review Focus 4 and 5)

With 3+ real phones on `CasetaMusica`, playing a song:
1. Phone A adds 4 songs, phone B adds 1: B's song is second. Expected: confirmed on both screens within 3 s.
2. Phone B tries to remove A's song: no button shown; `curl -X DELETE http://10.42.0.1/api/queue/<A's id>` returns 403.
3. Phone C uploads a 10 MB mp3 over Wi-Fi while A, B, D keep the page open: the current song does not stutter.
4. Admin page `http://10.42.0.1/albertitoeselmejor` with the PIN: skip and reorder work.
5. Run `sudo shutdown now` mid-song, power-cycle: everything returns by itself within 60 s, queue empty.
Expected: all five pass. Record any failure as a bug against the matching task before closing this plan.

- [ ] **Step 3: Commit**

```bash
git add deploy/README.md
git commit -m "Added owner's guide for the Pi deployment"
```

---

## Self-Review

- **Spec coverage:** own Wi-Fi (Task 3), reach the app from a phone with no typing (Task 3 captive portal + Task 4 QR), plays through the speakers (Task 2), starts unattended (Tasks 2, 3), reproducible install (Task 1).
- **Dependencies:** the redirect target `http://10.42.0.1/` and `CASETA_PORT`, `CASETA_ADMIN_PIN`, `CASETA_SONG_DIR` match the Config defaults in the app plan.
- **Known weak spot:** nothing here is automated; correctness is established only by the on-device checks. The Bookworm/NetworkManager hotspot commands and the `address=/#/` dnsmasq syntax should be confirmed against the installed OS version on first run (`nmcli --version`).
