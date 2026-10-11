import shutil
from pathlib import Path

from tests.conftest import make_wav
from tools import find_duplicates as fd


def song(config, name):
    return make_wav(config.song_folder / name, 1)


def copy_of(config, src, dst):
    dst = Path(dst)
    target = dst if dst.is_absolute() else config.song_folder / dst
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(config.song_folder / src, target)
    return target


# -- the library audit ------------------------------------------------------------------------


def test_exact_copies_in_different_folders_are_grouped(library, config):
    song(config, "Flamenquito/Omar Montes - La Sevillana.wav")
    copy_of(config, "Flamenquito/Omar Montes - La Sevillana.wav", "Reggaeton/Omar Montes - La Sevillana.wav")
    song(config, "Reggaeton/Sech - Relacion.wav")
    report = fd.analyse(library)
    assert report.exact == [["Flamenquito/Omar Montes - La Sevillana.wav", "Reggaeton/Omar Montes - La Sevillana.wav"]]


def test_files_of_the_same_size_but_different_content_are_not_exact_copies(library, config):
    song(config, "a.wav")
    song(config, "b.wav")  # same length, so the same size
    assert fd.analyse(library).exact == []


def test_same_artist_and_title_under_different_decoration_is_probably_the_same_song(library, config):
    song(config, "KAROL G - Bichota (Letra).wav")
    song(config, "Karol G - Bichota [Video Oficial].wav")
    song(config, "Sech - Relacion.wav")
    assert fd.analyse(library).likely == [["KAROL G - Bichota (Letra).wav", "Karol G - Bichota [Video Oficial].wav"]]


def test_accents_and_case_do_not_hide_a_match(library, config):
    song(config, "Rosalía - Con Altura.wav")
    song(config, "ROSALIA - con altura.wav")
    assert len(fd.analyse(library).likely) == 1


def test_the_same_title_by_different_artists_is_not_called_the_same_song(library, config):
    song(config, "Alba Molina - Dicen.wav")
    song(config, "Maka - Dicen (Video Oficial).wav")
    report = fd.analyse(library)
    assert report.likely == []
    assert report.same_title == [["Alba Molina - Dicen.wav", "Maka - Dicen (Video Oficial).wav"]]


def test_exact_copies_are_not_listed_a_second_time_as_a_name_match(library, config):
    song(config, "Flamenquito/Sech - Relacion.wav")
    copy_of(config, "Flamenquito/Sech - Relacion.wav", "Reggaeton/Sech - Relacion.wav")
    report = fd.analyse(library)
    assert len(report.exact) == 1
    assert report.likely == []


def test_a_clean_library_has_nothing_to_report(library, config):
    song(config, "Sech - Relacion.wav")
    song(config, "Karol G - Bichota.wav")
    report = fd.analyse(library)
    assert (report.exact, report.likely, report.same_title) == ([], [], [])


# -- checking new music before it is added -----------------------------------------------------


def test_a_new_file_identical_to_a_library_song_is_flagged_as_exact(library, config, tmp_path):
    song(config, "Flamenquito/Sech - Relacion.wav")
    new = copy_of(config, "Flamenquito/Sech - Relacion.wav", tmp_path / "incoming" / "whatever.wav")
    assert fd.check_new(library, [new]) == [fd.Finding(new, "exact", ("Flamenquito/Sech - Relacion.wav",))]


def test_a_new_file_named_like_a_library_song_is_flagged_as_similar(library, config, tmp_path):
    song(config, "Flamenquito/Sech - Relacion.wav")
    new = song(config, "elsewhere/SECH - Relación (Letra).wav")  # other content, same artist and title
    assert fd.check_new(library, [new]) == [fd.Finding(new, "similar", ("Flamenquito/Sech - Relacion.wav",))]


def test_a_new_song_the_library_does_not_have_is_not_flagged(library, config, tmp_path):
    song(config, "Flamenquito/Sech - Relacion.wav")
    new = song(config, "elsewhere/Karol G - Bichota.wav")
    assert fd.check_new(library, [new]) == []


def test_checking_a_folder_looks_at_every_audio_file_inside(library, config, tmp_path):
    song(config, "Flamenquito/Sech - Relacion.wav")
    incoming = tmp_path / "incoming"
    dup = copy_of(config, "Flamenquito/Sech - Relacion.wav", incoming / "deep" / "x.wav")
    make_wav(incoming / "fresh.wav", 1)
    (incoming / "notes.txt").write_text("not music")
    assert [f.path for f in fd.check_new(library, [incoming])] == [dup]


# -- command line --------------------------------------------------------------------------------


def test_check_exits_1_and_names_the_library_song_when_something_is_already_there(config, tmp_path, capsys):
    song(config, "Flamenquito/Sech - Relacion.wav")
    new = copy_of(config, "Flamenquito/Sech - Relacion.wav", tmp_path / "x.wav")
    code = fd.main(["--songs", str(config.song_folder), "--check", str(new)])
    assert code == 1
    assert "Flamenquito/Sech - Relacion.wav" in capsys.readouterr().out


def test_check_exits_0_when_everything_is_new(config, tmp_path, capsys):
    song(config, "Flamenquito/Sech - Relacion.wav")
    new = make_wav(tmp_path / "Karol G - Bichota.wav", 1)
    assert fd.main(["--songs", str(config.song_folder), "--check", str(new)]) == 0


def test_the_audit_lists_exact_copies_and_exits_0(config, capsys):
    song(config, "Flamenquito/Sech - Relacion.wav")
    copy_of(config, "Flamenquito/Sech - Relacion.wav", "Reggaeton/Sech - Relacion.wav")
    assert fd.main(["--songs", str(config.song_folder)]) == 0
    out = capsys.readouterr().out
    assert "Flamenquito/Sech - Relacion.wav" in out and "Reggaeton/Sech - Relacion.wav" in out


def test_same_title_other_artist_groups_only_show_with_all(config, capsys):
    song(config, "Alba Molina - Dicen.wav")
    song(config, "Maka - Dicen.wav")
    fd.main(["--songs", str(config.song_folder)])
    assert "Maka - Dicen.wav" not in capsys.readouterr().out
    fd.main(["--songs", str(config.song_folder), "--all"])
    assert "Maka - Dicen.wav" in capsys.readouterr().out
