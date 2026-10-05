"""The song library: safe path resolution, listing, uploads and durations."""
from __future__ import annotations

import secrets
import shutil
from pathlib import Path, PurePosixPath

import mutagen
from werkzeug.utils import secure_filename

from caseta.config import Config

FALLBACK_DURATION = 180.0


class SongNotFound(Exception):
    """The requested song is empty, unsafe, not allowed or does not exist."""


class InvalidUpload(Exception):
    """The uploaded file has a missing or disallowed extension."""


class Library:
    def __init__(self, config: Config):
        self._config = config
        self._durations: dict[Path, float] = {}

    @property
    def _root(self) -> Path:
        return Path(self._config.song_folder).resolve()

    def _allowed(self, name: str) -> bool:
        return Path(name).suffix.lstrip(".").lower() in self._config.allowed_extensions

    def list_songs(self) -> list[str]:
        root = self._root
        if not root.is_dir():
            return []
        songs = []
        for path in root.rglob("*"):
            if not (self._allowed(path.name) and path.is_file()):
                continue
            if not path.resolve().is_relative_to(root):  # symlink pointing outside
                continue
            songs.append(path.relative_to(root).as_posix())
        return sorted(songs)

    def resolve(self, song: str) -> Path:
        if not isinstance(song, str) or not song:
            raise SongNotFound(song)
        root = self._root
        try:
            path = (root / song).resolve()
            ok = path.is_relative_to(root) and self._allowed(path.name) and path.is_file()
        except (OSError, ValueError):  # e.g. embedded NUL, invalid characters
            raise SongNotFound(song) from None
        if not ok:
            raise SongNotFound(song)
        return path

    def save_upload(self, file) -> str:
        original = (file.filename or "").replace("\\", "/")
        original = PurePosixPath(original).name
        stem, dot, ext = original.rpartition(".")
        ext = ext.lower()
        if not dot or ext not in self._config.allowed_extensions:
            raise InvalidUpload(file.filename)
        stem = secure_filename(stem) or f"cancion-{secrets.token_hex(4)}"

        folder = self._root / self._config.upload_category
        folder.mkdir(parents=True, exist_ok=True)
        n = 0
        while True:
            name = f"{stem}.{ext}" if n == 0 else f"{stem}-{n}.{ext}"
            try:
                with open(folder / name, "xb") as out:  # exclusive: never overwrite
                    shutil.copyfileobj(file.stream, out)
                break
            except FileExistsError:
                n += 1
        return f"{self._config.upload_category}/{name}"

    def duration(self, song: str) -> float:
        try:
            path = self.resolve(song)
        except SongNotFound:
            return FALLBACK_DURATION
        if path not in self._durations:
            self._durations[path] = self._read_length(path)
        return self._durations[path]

    @staticmethod
    def _read_length(path: Path) -> float:
        try:
            length = float(mutagen.File(path).info.length)
        except Exception:
            return FALLBACK_DURATION
        return length if length > 0 else FALLBACK_DURATION

    @staticmethod
    def title(song: str) -> str:
        return PurePosixPath(song.replace("\\", "/")).stem
