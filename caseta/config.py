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
    replay_block_minutes: int = 120  # a song that just played cannot be added again for this long (0 = off)
    admin_pin: str | None = field(default=None, repr=False)
    secret_key: str = field(default_factory=lambda: secrets.token_hex(32), repr=False)
    portal_url: str = "http://10.42.0.1/"
    allowed_hosts: frozenset[str] = frozenset({"10.42.0.1", "caseta.local", "localhost", "127.0.0.1"})

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Config":
        defaults = cls()
        return cls(
            song_folder=Path(environ.get("CASETA_SONG_DIR") or defaults.song_folder),
            max_upload_bytes=_positive_int(environ, "CASETA_MAX_UPLOAD_MB", 30) * 1024 * 1024,
            max_pending_per_user=_positive_int(environ, "CASETA_MAX_PENDING", defaults.max_pending_per_user),
            replay_block_minutes=_int_at_least(
                environ, "CASETA_REPLAY_BLOCK_MINUTES", defaults.replay_block_minutes, 0
            ),
            admin_pin=environ.get("CASETA_ADMIN_PIN") or None,
            allowed_hosts=defaults.allowed_hosts | _host_list(environ.get("CASETA_ALLOWED_HOSTS", "")),
        )


def _host_list(raw: str) -> frozenset[str]:
    """Comma-separated host names, trimmed and lowercased; empty items ignored."""
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    return _int_at_least(environ, name, default, 1)


def _int_at_least(environ: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value
