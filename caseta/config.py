"""Runtime configuration for the Caseta jukebox."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Config:
    song_folder: Path = Path("songs")
    upload_category: str = "Subidas"
    allowed_extensions: frozenset[str] = frozenset({"mp3", "wav", "ogg"})
    max_upload_bytes: int = 30 * 1024 * 1024
    max_pending_per_user: int = 5
    admin_pin: str | None = None
    secret_key: str = field(default_factory=lambda: secrets.token_hex(32))
    portal_url: str = "http://10.42.0.1/"
    allowed_hosts: frozenset[str] = frozenset({"10.42.0.1", "caseta.local", "localhost", "127.0.0.1"})

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Config":
        defaults = cls()
        return cls(
            song_folder=Path(environ.get("CASETA_SONG_DIR") or defaults.song_folder),
            max_upload_bytes=_positive_int(environ, "CASETA_MAX_UPLOAD_MB", 30) * 1024 * 1024,
            max_pending_per_user=_positive_int(environ, "CASETA_MAX_PENDING", defaults.max_pending_per_user),
            admin_pin=environ.get("CASETA_ADMIN_PIN") or None,
        )


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}")
    return value
