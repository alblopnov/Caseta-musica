"""Test doubles shared by engine and (later) web tests."""
from pathlib import Path


class FakePlayer:
    """Records what was played; the test decides when a song 'finishes'."""

    def __init__(self):
        self.played: list[Path] = []
        self.playing = False
        self.fail_next = False

    def play(self, path: Path) -> None:
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
