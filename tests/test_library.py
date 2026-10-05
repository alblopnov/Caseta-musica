import io
import os
import re

import pytest
from werkzeug.datastructures import FileStorage

from caseta.config import Config
from caseta.library import InvalidUpload, Library, SongNotFound
from tests.conftest import make_wav


@pytest.mark.parametrize("bad", ["../secret.mp3", "/etc/passwd", "reggaeton/../../secret.mp3",
                                 "..\\secret.mp3", "reggaeton\\..\\..\\secret.mp3",
                                 "notes.txt", "missing.mp3", "", "reggaeton"])
def test_resolve_rejects_unsafe_or_unknown(library, config, bad):
    make_wav(config.song_folder.parent / "secret.mp3", 1)   # exists, but outside the folder
    make_wav(config.song_folder / "reggaeton" / "ok.mp3", 1)
    (config.song_folder / "notes.txt").write_text("x")
    with pytest.raises(SongNotFound):
        library.resolve(bad)


def test_resolve_rejects_absolute_path_to_real_file(library, config):
    outside = make_wav(config.song_folder.parent / "secret.mp3", 1)
    make_wav(config.song_folder / "ok.mp3", 1)
    with pytest.raises(SongNotFound):
        library.resolve(str(outside))


def test_resolve_rejects_symlink_escape(library, config):
    outside_dir = config.song_folder.parent / "outside"
    make_wav(outside_dir / "secret.mp3", 1)
    config.song_folder.mkdir(parents=True)
    try:
        os.symlink(outside_dir, config.song_folder / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this platform/account")
    with pytest.raises(SongNotFound):
        library.resolve("link/secret.mp3")


def test_resolve_accepts_nested_song(library, config):
    p = make_wav(config.song_folder / "reggaeton" / "ok.wav", 1)
    assert library.resolve("reggaeton/ok.wav") == p.resolve()


def test_resolve_works_with_relative_song_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_wav(tmp_path / "songs" / "a.wav", 1)
    lib = Library(Config(song_folder="songs"))
    assert lib.resolve("a.wav") == (tmp_path / "songs" / "a.wav").resolve()
    assert lib.list_songs() == ["a.wav"]


def test_list_songs_empty_when_folder_missing(library, config):
    assert not config.song_folder.exists()
    assert library.list_songs() == []


def test_list_songs_relative_sorted_allowed_only(library, config):
    make_wav(config.song_folder / "b.wav", 1)
    make_wav(config.song_folder / "Rock" / "a.wav", 1)
    (config.song_folder / "readme.txt").write_text("x")
    assert library.list_songs() == ["Rock/a.wav", "b.wav"]


def upload(name, data=b"x"):
    return FileStorage(stream=io.BytesIO(data), filename=name)


def test_upload_same_name_twice_gets_unique_names(library):
    assert library.save_upload(upload("a.mp3")) == "Subidas/a.mp3"
    assert library.save_upload(upload("a.mp3")) == "Subidas/a-1.mp3"
    assert library.save_upload(upload("a.mp3")) == "Subidas/a-2.mp3"


def test_upload_writes_content_and_is_listed(library, config):
    rel = library.save_upload(upload("a.mp3", b"hello"))
    assert (config.song_folder / rel).read_bytes() == b"hello"
    assert library.list_songs() == [rel]


@pytest.mark.parametrize("name", ["歌.mp3", "🎵.mp3"])
def test_upload_non_ascii_name_gets_generated_name(library, name):
    assert re.fullmatch(r"Subidas/cancion-[0-9a-f]{8}\.mp3", library.save_upload(upload(name)))


def test_upload_keeps_readable_part_of_accented_name(library):
    assert library.save_upload(upload("Bad Bunny – Tití.mp3")) == "Subidas/Bad_Bunny_Titi.mp3"


@pytest.mark.parametrize("name", ["x.exe", "noext", "../../evil.mp3.sh", "", None])
def test_upload_rejects_bad_extension(library, name):
    with pytest.raises(InvalidUpload):
        library.save_upload(upload(name))


def test_upload_traversal_name_stays_in_category_folder(library, config):
    rel = library.save_upload(upload("../../evil.mp3"))
    assert rel == "Subidas/evil.mp3"
    assert (config.song_folder / rel).is_file()


def test_duration_reads_wav_length(library, config):
    make_wav(config.song_folder / "t.wav", 2.0)
    assert library.duration("t.wav") == pytest.approx(2.0, abs=0.05)


def test_duration_falls_back_for_garbage_file(library, config):
    p = config.song_folder / "bad.mp3"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"not audio")
    assert library.duration("bad.mp3") == 180.0


def test_duration_is_cached_per_path(library, config, monkeypatch):
    import mutagen
    make_wav(config.song_folder / "t.wav", 1.0)
    calls = []
    real = mutagen.File
    monkeypatch.setattr(mutagen, "File", lambda *a, **k: calls.append(a) or real(*a, **k))
    first = library.duration("t.wav")
    assert library.duration("t.wav") == first
    assert len(calls) == 1


def test_title_strips_folder_and_extension():
    assert Library.title("reggaeton/Bad Bunny - Tití.mp3") == "Bad Bunny - Tití"


def test_from_env_reads_knobs():
    c = Config.from_env({"CASETA_ADMIN_PIN": "9", "CASETA_MAX_PENDING": "3", "CASETA_MAX_UPLOAD_MB": "5"})
    assert (c.admin_pin, c.max_pending_per_user, c.max_upload_bytes) == ("9", 3, 5 * 1024 * 1024)


def test_from_env_defaults():
    c = Config.from_env({})
    assert c.admin_pin is None
    assert c.max_pending_per_user == 5
    assert c.max_upload_bytes == 30 * 1024 * 1024
    assert str(c.song_folder) == "songs"
    assert c.secret_key


def test_from_env_song_dir_and_blank_pin():
    c = Config.from_env({"CASETA_SONG_DIR": "/music", "CASETA_ADMIN_PIN": ""})
    assert str(c.song_folder).replace("\\", "/") == "/music"
    assert c.admin_pin is None
