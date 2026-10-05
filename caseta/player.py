"""Audio output behind a small interface so the engine can be tested without sound."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Player(Protocol):
    def play(self, path: Path) -> None: ...

    def stop(self) -> None: ...

    def is_playing(self) -> bool: ...


class PygamePlayer:
    """Plays through pygame.mixer. The mixer is initialised on the first `play`,
    so importing this module or constructing the player needs no audio device."""

    def __init__(self) -> None:
        self._ready = False

    def _ensure_mixer(self):
        import pygame

        if not self._ready:
            pygame.mixer.init()
            self._ready = True
        return pygame

    def play(self, path: Path) -> None:
        pygame = self._ensure_mixer()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()

    def stop(self) -> None:
        if not self._ready:
            return
        import pygame

        pygame.mixer.music.stop()

    def is_playing(self) -> bool:
        if not self._ready:
            return False
        import pygame

        return bool(pygame.mixer.music.get_busy())
