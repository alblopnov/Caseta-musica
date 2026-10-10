"""Test doubles shared by engine and (later) web tests."""
from pathlib import Path

from caseta.player import PlayerUnavailable


class FakePlayer:
    """Records what was played; the test decides when a song 'finishes'."""

    def __init__(self):
        self.played: list[Path] = []
        self.playing = False
        self.fail_next = False
        self.unavailable = False  # True: every play raises PlayerUnavailable (no audio device)
        self.attempts = 0

    def play(self, path: Path) -> None:
        self.attempts += 1
        if self.unavailable:
            raise PlayerUnavailable("no audio device")
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("unreadable song")
        self.played.append(path)
        self.playing = True

    def stop(self) -> None:
        self.playing = False

    def finish(self) -> None:
        self.playing = False

    def is_playing(self) -> bool:
        return self.playing
