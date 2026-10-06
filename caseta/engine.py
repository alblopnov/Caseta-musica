"""PlaybackEngine: drives a Player from a SongQueue and reports queue state."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from caseta.song_queue import NotOwner, QueueItem, SongQueue
from caseta.library import Library
from caseta.player import Player, PlayerUnavailable

log = logging.getLogger(__name__)


class PlaybackEngine:
    # After PlayerUnavailable, wait this long before trying the audio output again.
    AUDIO_RETRY_SECONDS = 5.0

    def __init__(
        self,
        queue: SongQueue,
        player: Player,
        library: Library,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = 0.25,
        audio_retry_seconds: float | None = None,
    ):
        self._queue = queue
        self._player = player
        self._library = library
        self._clock = clock
        self._poll_interval = poll_interval
        self._audio_retry_seconds = (
            self.AUDIO_RETRY_SECONDS if audio_retry_seconds is None else audio_retry_seconds
        )
        self._audio_down = False  # a PlayerUnavailable is outstanding
        self._audio_retry_at = 0.0
        self._lock = threading.RLock()
        self._current: QueueItem | None = None
        self._started_at = 0.0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # -- background thread -------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="playback-engine", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None:
            thread.join()  # outside the lock: the thread may be waiting for it in tick()
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def _run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("Playback tick failed")
            if self._stop_event.wait(self._poll_interval):
                return

    # -- playback ----------------------------------------------------------

    def tick(self) -> None:
        with self._lock:
            if self._current is not None and not self._player.is_playing():
                self._current = None
            if self._current is not None:
                return
            if self._audio_down and self._clock() < self._audio_retry_at:
                return  # backing off: the songs wait in the queue
            item = self._queue.pop_next()
            if item is None:
                return
            try:
                path = self._library.resolve(item.song)
            except Exception:  # deleted or moved since it was queued: says nothing about audio
                log.exception("Could not find %r (queued by %s); dropping it", item.song, item.owner)
                return
            try:
                self._player.play(path)
            except PlayerUnavailable as exc:
                # The device is the problem, not the song: keep it first in line.
                self._queue.push_front(item)
                if not self._audio_down:
                    log.error("Audio output unavailable (%s); songs stay queued, retrying every %.0f s",
                              exc, self._audio_retry_seconds)
                self._audio_down = True
                self._audio_retry_at = self._clock() + self._audio_retry_seconds
                return
            except Exception:
                self._audio_ok_again()
                log.exception("Could not play %r (queued by %s); dropping it", item.song, item.owner)
                return
            self._audio_ok_again()
            self._current = item
            self._started_at = self._clock()

    def _audio_ok_again(self) -> None:
        """The player got past opening the device: any outage is over."""
        if self._audio_down:
            log.info("Audio output is back")
        self._audio_down = False

    def _stop_current(self) -> None:
        self._player.stop()
        self._current = None

    # -- commands ----------------------------------------------------------

    def enqueue(self, song: str, owner: str) -> QueueItem:
        with self._lock:
            self._library.resolve(song)  # raises SongNotFound before the queue is touched
            return self._queue.add(song, owner)

    def remove(self, item_id: str, requester: str, is_admin: bool = False) -> None:
        with self._lock:
            current = self._current
            if current is not None and current.id == item_id:
                if current.owner != requester and not is_admin:
                    raise NotOwner(item_id)
                self._stop_current()
                return
            self._queue.remove(item_id, requester, is_admin)

    def skip(self) -> None:
        with self._lock:
            if self._current is not None:
                self._stop_current()

    def move(self, item_id: str, position: int) -> None:
        with self._lock:
            self._queue.move(item_id, position)

    # -- state -------------------------------------------------------------

    def snapshot(self, viewer: str) -> dict:
        with self._lock:
            lib = self._library
            now_playing = None
            remaining = 0.0
            if self._current is not None:
                cur = self._current
                duration = lib.duration(cur.song)
                elapsed = max(0.0, self._clock() - self._started_at)
                remaining = max(0.0, duration - elapsed)
                now_playing = {
                    "id": cur.id,
                    "song": cur.song,
                    "title": lib.title(cur.song),
                    "mine": cur.owner == viewer,
                    "elapsed": elapsed,
                    "duration": duration,
                }
            queue = []
            eta = remaining
            for item in self._queue.snapshot():
                queue.append(
                    {
                        "id": item.id,
                        "song": item.song,
                        "title": lib.title(item.song),
                        "mine": item.owner == viewer,
                        "eta_seconds": eta,
                    }
                )
                eta += lib.duration(item.song)
            return {
                "now_playing": now_playing,
                "queue": queue,
                "total_seconds": eta,
                "me": {
                    "pending": self._queue.pending_count(viewer),
                    "max": self._queue.max_pending_per_user,
                },
                "audio_ok": not self._audio_down,
            }
