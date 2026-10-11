"""What has played tonight: a song that just played cannot be asked for again right away."""
from __future__ import annotations

import time
from typing import Callable


class PlayHistory:
    """Remembers when each song (by content key) last started, in memory only.

    Not thread-safe: the engine calls it with its lock held. With a cooldown of 0
    nothing is ever blocked."""

    def __init__(self, cooldown_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._played_at: dict[str, float] = {}

    def record(self, key: str) -> None:
        self._played_at[key] = self._clock()

    def remaining(self, key: str) -> float:
        """Seconds until `key` may be requested again; 0 when it is free now."""
        played_at = self._played_at.get(key)
        if played_at is None:
            return 0.0
        return max(0.0, played_at + self._cooldown - self._clock())
