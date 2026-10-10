import dataclasses
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


SONG_NAMES = ["a1", "a2", "a3", "b1", *(f"s{i}" for i in range(6))]


@pytest.fixture
def songs(config):
    for name in SONG_NAMES:
        make_wav(config.song_folder / f"{name}.wav", 1)
    return config.song_folder


@pytest.fixture
def player():
    from tests.fakes import FakePlayer

    return FakePlayer()


@pytest.fixture
def app(config, player):
    from caseta import create_app

    return create_app(config, player=player, start_engine=False)


@pytest.fixture
def phone_a(app):
    return app.test_client()


@pytest.fixture
def phone_b(app):
    return app.test_client()


@pytest.fixture
def app_without_pin_client(config, player):
    from caseta import create_app

    cfg = dataclasses.replace(config, admin_pin=None)
    return create_app(cfg, player=player, start_engine=False).test_client()


@pytest.fixture
def app_small_limit_client(config, player):
    from caseta import create_app

    cfg = dataclasses.replace(config, max_upload_bytes=1024)
    return create_app(cfg, player=player, start_engine=False).test_client()
