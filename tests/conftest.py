import wave
from pathlib import Path

import pytest

from caseta.config import Config
from caseta.library import Library


def make_wav(path: Path, seconds: float) -> Path:
    """Write a silent mono 8 kHz 16-bit WAV of the given length, creating parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 8000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


@pytest.fixture
def config(tmp_path):
    return Config(song_folder=tmp_path / "songs", admin_pin="1234")


@pytest.fixture
def library(config):
    return Library(config)
