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
    volume_percent: int = 100  # starting volume, 0 to 100
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
            volume_percent=_percent(environ, "CASETA_VOLUME", defaults.volume_percent),
            admin_pin=environ.get("CASETA_ADMIN_PIN") or None,
            allowed_hosts=defaults.allowed_hosts | _host_list(environ.get("CASETA_ALLOWED_HOSTS", "")),
        )


def _host_list(raw: str) -> frozenset[str]:
    """Comma-separated host names, trimmed and lowercased; empty items ignored."""
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _integer(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    value = _integer(environ, name, default)
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}")
    return value


def _percent(environ: Mapping[str, str], name: str, default: int) -> int:
    value = _integer(environ, name, default)
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100, got {value}")
    return value
