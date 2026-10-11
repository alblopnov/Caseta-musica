"""The song library: safe path resolution, listing, uploads and durations."""
from __future__ import annotations

import hashlib
import secrets
import shutil
import threading
from pathlib import Path, PurePosixPath

import mutagen
from werkzeug.utils import secure_filename

from caseta.config import Config

FALLBACK_DURATION = 180.0
MAX_STEM_LENGTH = 100
HASH_CHUNK = 1024 * 1024


def hash_file(path: Path) -> str:
    """Content hash of a file: equal exactly when the bytes are equal."""
    digest = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        while chunk := f.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class SongNotFound(Exception):
    """The requested song is empty, unsafe, not allowed or does not exist."""


class InvalidUpload(Exception):
    """The uploaded file has a missing or disallowed extension."""


class Library:
    def __init__(self, config: Config):
        self._config = config
        self._durations: dict[Path, float] = {}
        self._keys: dict[Path, tuple[int, int, str]] = {}  # path -> (size, mtime_ns, key)
        self._dedupe_lock = threading.Lock()

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
        try:
            root = self._root
            path = (root / song).resolve()
            ok = path.is_relative_to(root) and self._allowed(path.name) and path.is_file()
        except (OSError, ValueError, RuntimeError):  # NUL byte, bad chars, symlink loop (3.11)
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
        stem = secure_filename(stem)[:MAX_STEM_LENGTH].strip("._") or f"cancion-{secrets.token_hex(4)}"

        try:
            folder = self._root / self._config.upload_category
            folder.mkdir(parents=True, exist_ok=True)
            n = 0
            while True:
                name = f"{stem}.{ext}" if n == 0 else f"{stem}-{n}.{ext}"
                target = folder / name
                try:
                    out = open(target, "xb")  # exclusive: never overwrite
                except FileExistsError:
                    n += 1
                    continue
                break
        except OSError as e:
            raise InvalidUpload(file.filename) from e
        try:
            with out:
                shutil.copyfileobj(file.stream, out)
        except BaseException:
            target.unlink(missing_ok=True)  # never leave a truncated song behind
            raise
        return f"{self._config.upload_category}/{name}"

    def content_key(self, song: str) -> str:
        """Identity of the recording: equal for byte-identical files wherever they are.

        Hashed once per file and remembered until its size or modification time changes."""
        return self._key_of(self.resolve(song))

    def _key_of(self, path: Path) -> str:
        stat = path.stat()
        cached = self._keys.get(path)
        if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return cached[2]
        key = hash_file(path)
        self._keys[path] = (stat.st_size, stat.st_mtime_ns, key)
        return key

    def find_identical(self, song: str) -> str | None:
        """Another song in the library with exactly the same content, or None.

        Only files of the same size are hashed, so the rest of the library is not read."""
        path = self.resolve(song)
        size = path.stat().st_size
        key = self._key_of(path)
        for other in self.list_songs():
            candidate = self.resolve(other)
            if candidate == path or candidate.stat().st_size != size:
                continue
            if self._key_of(candidate) == key:
                return other
        return None

    def drop_if_duplicate(self, song: str) -> str | None:
        """Delete `song` if the library already holds the same recording; name that one.

        None (and the file stays) when nothing else matches. Serialized, so two
        identical uploads at the same moment cannot each delete themselves."""
        with self._dedupe_lock:
            other = self.find_identical(song)
            if other is not None:
                self.resolve(song).unlink()
            return other

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
