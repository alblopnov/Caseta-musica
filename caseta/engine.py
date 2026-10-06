"""PlaybackEngine: drives a Player from a SongQueue and reports queue state."""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable
from uuid import uuid4

from caseta.song_queue import NotOwner, QueueFull, QueueItem, SongQueue
from caseta.library import Library
from caseta.player import Player, PlayerUnavailable

log = logging.getLogger(__name__)


class EmptyCategory(Exception):
    """Shuffle asked for a section that has no songs (or does not exist)."""


class ShuffleLocked(Exception):
    """Shuffle was started by another phone; only that phone or the admin can change it."""


class PlaybackEngine:
    # After PlayerUnavailable, wait this long before trying the audio output again.
    AUDIO_RETRY_SECONDS = 5.0
    ALL_SECTIONS = "Todas"

    def __init__(
        self,
        queue: SongQueue,
        player: Player,
        library: Library,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = 0.25,
        audio_retry_seconds: float | None = None,
        rng: random.Random | None = None,
    ):
        self._queue = queue
        self._player = player
        self._library = library
        self._clock = clock
        self._poll_interval = poll_interval
        self._audio_retry_seconds = (
            self.AUDIO_RETRY_SECONDS if audio_retry_seconds is None else audio_retry_seconds
        )
        self._rng = rng if rng is not None else random.Random()
        # Shuffle mode: {"category", "owner", "bag"}. While it is on and nothing is
        # queued, the next song is drawn from `bag` (a shuffled copy of the section
        # that is used up before it is reshuffled). Shuffle songs are never queued.
        self._shuffle: dict | None = None
        self._last_song: str | None = None
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
            from_shuffle = False
            if item is None and self._shuffle is not None:
                item = self._next_shuffle_item()
                from_shuffle = item is not None
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
                if from_shuffle:
                    if self._shuffle is not None:
                        self._shuffle["bag"].insert(0, item.song)
                else:
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
            self._last_song = item.song
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

    def enqueue(self, song: str, owner: str, is_admin: bool = False) -> QueueItem:
        with self._lock:
            self._library.resolve(song)  # raises SongNotFound before the queue is touched
            return self._queue.add(song, owner, is_admin)

    # -- shuffle mode ----------------------------------------------------------

    def _pool(self, category: str) -> list[str]:
        songs = self._library.list_songs()
        if category == self.ALL_SECTIONS:
            return songs
        prefix = category + "/"
        return [song for song in songs if category and song.startswith(prefix)]

    def _shuffle_info(self, viewer: str, is_admin: bool) -> dict | None:
        if self._shuffle is None:
            return None
        return {
            "category": self._shuffle["category"],
            "can_stop": is_admin or self._shuffle["owner"] == viewer,
        }

    def start_shuffle(self, category: str, owner: str, is_admin: bool = False) -> dict:
        """Play random songs from one section ("Todas" = everything) until stopped.

        Songs added by hand always play first; a random one is drawn only when the
        queue is empty. If shuffle is already on, only the phone that started it
        (or the admin) may change the section (ShuffleLocked otherwise)."""
        with self._lock:
            current = self._shuffle
            if current is not None and current["owner"] != owner and not is_admin:
                raise ShuffleLocked(current["category"])
            if not self._pool(category):
                raise EmptyCategory(category)
            # A different phone's mode keeps its starter when the admin merely changes it.
            starter = current["owner"] if current is not None and is_admin else owner
            self._shuffle = {"category": category, "owner": starter, "bag": []}
            return self._shuffle_info(owner, is_admin)

    def stop_shuffle(self, requester: str, is_admin: bool = False) -> None:
        with self._lock:
            if self._shuffle is None:
                return
            if self._shuffle["owner"] != requester and not is_admin:
                raise NotOwner(self._shuffle["category"])
            self._shuffle = None

    def _next_shuffle_item(self) -> QueueItem | None:
        """The next random song as a (never queued) item owned by the shuffle's starter."""
        shuffle = self._shuffle
        pool = self._pool(shuffle["category"])
        if not pool:
            log.warning("Shuffle section %r has no songs left; turning shuffle off", shuffle["category"])
            self._shuffle = None
            return None
        bag = [song for song in shuffle["bag"] if song in pool]  # drop files that disappeared
        if not bag:
            bag = list(pool)
            self._rng.shuffle(bag)
            if len(bag) > 1 and bag[0] == self._last_song:
                bag.append(bag.pop(0))  # never the same song twice in a row
        shuffle["bag"] = bag
        return QueueItem(id=uuid4().hex, song=bag.pop(0), owner=shuffle["owner"])

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

    def snapshot(self, viewer: str, is_admin: bool = False) -> dict:
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
                    "max": None if is_admin else self._queue.max_pending_per_user,  # None = no limit
                },
                "audio_ok": not self._audio_down,
                "shuffle": self._shuffle_info(viewer, is_admin),
            }
