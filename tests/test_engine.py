import random
import time

import pytest

from caseta.engine import EmptyCategory, PlaybackEngine, ShuffleLocked
from caseta.song_queue import DuplicateSong, NotOwner, QueueFull, SongQueue, UnknownItem
from caseta.library import SongNotFound
from tests.conftest import make_wav
from tests.fakes import FakePlayer

DURATIONS = {"a.wav": 10, "b.wav": 20, "c.wav": 30}


@pytest.fixture
def songs(config):
    folder = config.song_folder
    for name in ("a1.wav", "a2.wav", "a3.wav", "b1.wav", "d.wav", "e.wav"):
        make_wav(folder / name, 1)
    for name, seconds in DURATIONS.items():
        make_wav(folder / name, seconds)
    return folder


@pytest.fixture
def lib_path(songs):
    return lambda name: (songs / name).resolve()


@pytest.fixture
def player():
    return FakePlayer()


@pytest.fixture
def clock():
    return [0.0]


@pytest.fixture
def engine_factory(config, library, songs):
    def build(player, clock=None, poll_interval=0.25, **kwargs):
        t = clock if clock is not None else [0.0]
        queue = SongQueue(config.max_pending_per_user)
        return PlaybackEngine(queue, player, library, clock=lambda: t[0], poll_interval=poll_interval, **kwargs)

    return build


@pytest.fixture
def engine(engine_factory, player, clock):
    return engine_factory(player, clock)


@pytest.fixture
def add(engine):
    return lambda song, owner: engine.enqueue(song, owner)


def drain(engine, player, limit=50):
    """tick/finish until nothing is queued or playing; return the played paths."""
    for _ in range(limit):
        engine.tick()
        snap = engine.snapshot("nobody")
        if snap["now_playing"] is None and not snap["queue"]:
            break
        player.finish()
    return list(player.played)


def test_tick_starts_first_song_and_reports_it(engine, player, add, lib_path):
    add("a.wav", "A")
    engine.tick()
    assert player.played == [lib_path("a.wav")]
    assert engine.snapshot("A")["now_playing"]["title"] == "a"
    assert engine.snapshot("A")["now_playing"]["mine"] is True
    assert engine.snapshot("B")["now_playing"]["mine"] is False


def test_enqueue_stores_relative_song_not_resolved_path(engine, add):
    item = add("a.wav", "A")
    assert item.song == "a.wav"
    assert engine.snapshot("A")["queue"][0]["song"] == "a.wav"


def test_next_song_starts_only_after_current_finishes(engine, player, add):
    add("a.wav", "A")
    add("b.wav", "B")
    engine.tick()
    engine.tick()
    assert len(player.played) == 1
    player.finish()
    engine.tick()
    assert len(player.played) == 2


def test_songs_play_in_the_order_they_were_added(engine, player, add):
    for s in ("a1.wav", "a2.wav", "a3.wav"):
        add(s, "A")
    add("b1.wav", "B")
    played = drain(engine, player)
    assert [p.name for p in played] == ["a1.wav", "a2.wav", "a3.wav", "b1.wav"]


def test_a_song_added_while_your_own_song_plays_goes_to_the_end(engine, player, add):
    for s in ("a1.wav", "a2.wav", "a3.wav"):
        add(s, "A")
    add("b1.wav", "B")
    engine.tick()  # a1
    player.finish()
    engine.tick()  # a2 starts; B queues another song right away
    add("d.wav", "B")
    played = drain(engine, player)
    assert [p.name for p in played] == ["a1.wav", "a2.wav", "a3.wav", "b1.wav", "d.wav"]


def test_eta_uses_remaining_time_of_current_song(engine, player, add, clock):
    add("a.wav", "A")
    add("b.wav", "B")
    add("c.wav", "C")  # 10s, 20s, 30s files
    engine.tick()
    clock[0] = 4.0
    snap = engine.snapshot("B")
    q = snap["queue"]
    assert [round(i["eta_seconds"]) for i in q] == [6, 26]
    assert round(snap["total_seconds"]) == 56
    assert q[0]["mine"] is True and q[1]["mine"] is False
    assert round(snap["now_playing"]["elapsed"]) == 4
    assert round(snap["now_playing"]["duration"]) == 10


def test_eta_with_nothing_playing_starts_at_zero(engine, add):
    add("a.wav", "A")
    add("b.wav", "B")
    snap = engine.snapshot("A")
    assert snap["now_playing"] is None
    assert [round(i["eta_seconds"]) for i in snap["queue"]] == [0, 10]
    assert round(snap["total_seconds"]) == 30


def test_eta_remaining_never_negative_when_song_overruns(engine, add, clock):
    add("a.wav", "A")
    add("b.wav", "B")
    engine.tick()
    clock[0] = 99.0  # past the 10 s duration, but the player still says playing
    snap = engine.snapshot("B")
    assert snap["queue"][0]["eta_seconds"] == 0
    assert round(snap["total_seconds"]) == 20


def test_snapshot_me_counts_only_viewers_pending(engine, add):
    add("a.wav", "A")
    add("b.wav", "A")
    engine.tick()
    assert engine.snapshot("A")["me"] == {"pending": 1, "max": 5}
    assert engine.snapshot("B")["me"] == {"pending": 0, "max": 5}


def test_empty_snapshot_shape(engine):
    assert engine.snapshot("A") == {
        "now_playing": None,
        "queue": [],
        "total_seconds": 0,
        "me": {"pending": 0, "max": 5},
        "audio_ok": True,
        "shuffle": None,
    }


def test_owner_can_remove_own_playing_song_other_cannot(engine, player, add):
    add("a.wav", "A")
    engine.tick()
    now = engine.snapshot("A")["now_playing"]["id"]
    with pytest.raises(NotOwner):
        engine.remove(now, "B")
    assert player.playing is True
    engine.remove(now, "A")
    assert player.playing is False
    assert engine.snapshot("A")["now_playing"] is None


def test_admin_can_remove_playing_song(engine, player, add):
    add("a.wav", "A")
    engine.tick()
    now = engine.snapshot("A")["now_playing"]["id"]
    engine.remove(now, "B", is_admin=True)
    assert player.playing is False
    assert engine.snapshot("A")["now_playing"] is None


def test_removing_playing_song_lets_next_start(engine, player, add):
    add("a.wav", "A")
    add("b.wav", "B")
    engine.tick()
    engine.remove(engine.snapshot("A")["now_playing"]["id"], "A")
    engine.tick()
    assert [p.name for p in player.played] == ["a.wav", "b.wav"]


def test_remove_queued_item_delegates_to_queue(engine, player, add):
    add("a.wav", "A")
    queued = add("b.wav", "B")
    engine.tick()
    with pytest.raises(NotOwner):
        engine.remove(queued.id, "A")
    engine.remove(queued.id, "B")
    assert engine.snapshot("B")["queue"] == []
    assert player.playing is True  # the playing song is untouched


def test_remove_unknown_item_raises(engine, add):
    add("a.wav", "A")
    engine.tick()
    with pytest.raises(UnknownItem):
        engine.remove("nope", "A")


def test_remove_when_nothing_playing_and_empty_queue(engine):
    with pytest.raises(UnknownItem):
        engine.remove("nope", "A")


def test_skip_with_nothing_playing_is_a_noop(engine, player):
    engine.skip()
    assert player.playing is False
    assert player.played == []


def test_skip_with_empty_queue_while_playing_leaves_nothing(engine, player, add):
    add("a.wav", "A")
    engine.tick()
    engine.skip()
    engine.tick()
    assert player.playing is False
    assert engine.snapshot("A")["now_playing"] is None
    assert [p.name for p in player.played] == ["a.wav"]


def test_skip_advances_to_next(engine, player, add):
    add("a.wav", "A")
    add("b.wav", "B")
    engine.tick()
    engine.skip()
    engine.tick()
    assert [p.name for p in player.played] == ["a.wav", "b.wav"]


def test_move_reorders_queue(engine, add):
    add("a1.wav", "A")
    add("b1.wav", "B")
    last = add("d.wav", "C")
    engine.move(last.id, 1)
    assert [i["song"] for i in engine.snapshot("A")["queue"]] == ["d.wav", "a1.wav", "b1.wav"]


def test_move_unknown_item_raises(engine):
    with pytest.raises(UnknownItem):
        engine.move("nope", 1)


def test_unreadable_song_is_dropped_and_next_plays(engine, player, add):
    add("a.wav", "A")
    add("b.wav", "B")
    player.fail_next = True
    engine.tick()  # must not raise
    assert engine.snapshot("A")["now_playing"] is None
    engine.tick()
    assert [p.name for p in player.played] == ["b.wav"]


def test_failing_play_is_logged(engine, player, add, caplog):
    add("a.wav", "A")
    player.fail_next = True
    with caplog.at_level("ERROR", logger="caseta.engine"):
        engine.tick()
    assert any("a.wav" in r.getMessage() and r.exc_info for r in caplog.records)


def test_song_deleted_from_disk_after_queueing_is_skipped(engine, player, add, songs):
    add("a.wav", "A")
    add("b.wav", "B")
    (songs / "a.wav").unlink()
    engine.tick()  # must not raise
    engine.tick()
    assert [p.name for p in player.played] == ["b.wav"]


def test_queue_empties_between_ticks(engine, player, add):
    add("a.wav", "A")
    engine.tick()
    player.finish()
    engine.tick()  # marks finished, nothing left to start
    engine.tick()
    assert engine.snapshot("A")["now_playing"] is None
    assert len(player.played) == 1
    add("b.wav", "B")
    engine.tick()
    assert [p.name for p in player.played] == ["a.wav", "b.wav"]


def test_finished_song_can_be_queued_again(engine, player, add):
    add("a.wav", "A")
    engine.tick()
    add("a.wav", "B")  # playing songs are not pending: no duplicate error
    player.finish()
    engine.tick()
    assert [p.name for p in player.played] == ["a.wav", "a.wav"]


def test_enqueue_unknown_song_raises_song_not_found(engine):
    with pytest.raises(SongNotFound):
        engine.enqueue("../x.mp3", "A")


def test_enqueue_unsafe_song_never_touches_queue_or_player(engine, player):
    for bad in ("../x.mp3", "/etc/passwd", "notes.txt", ""):
        with pytest.raises(SongNotFound):
            engine.enqueue(bad, "A")
    engine.tick()
    assert player.played == []
    assert engine.snapshot("A")["queue"] == []


def test_enqueue_propagates_queue_errors(engine, add):
    add("a.wav", "A")
    with pytest.raises(DuplicateSong):
        add("a.wav", "B")
    for name in ("a1.wav", "a2.wav", "a3.wav", "b1.wav"):
        add(name, "C")
    add("d.wav", "C")
    with pytest.raises(QueueFull):
        add("e.wav", "C")


def test_start_and_stop_thread_plays_a_song(engine_factory, player):
    engine = engine_factory(player, poll_interval=0.01)
    engine.enqueue("a.wav", "A")
    engine.start()
    try:
        deadline = time.monotonic() + 2
        while not player.played and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [p.name for p in player.played] == ["a.wav"]
    finally:
        engine.stop()
    assert engine._thread is None or not engine._thread.is_alive()


def test_stop_without_start_and_double_start_are_safe(engine_factory, player):
    engine = engine_factory(player, poll_interval=0.01)
    engine.stop()
    engine.start()
    thread = engine._thread
    engine.start()
    assert engine._thread is thread
    engine.stop()
    assert not thread.is_alive()


def test_thread_survives_failing_song(engine_factory, player):
    engine = engine_factory(player, poll_interval=0.01)
    engine.enqueue("a.wav", "A")
    engine.enqueue("b.wav", "B")
    player.fail_next = True
    engine.start()
    try:
        deadline = time.monotonic() + 2
        while not player.played and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [p.name for p in player.played] == ["b.wav"]
    finally:
        engine.stop()


# -- audio device unavailable --------------------------------------------------


def queued(engine):
    return [(i.song, i.owner) for i in engine._queue.snapshot()]


def test_unavailable_audio_device_keeps_the_queue(engine, player, add, clock):
    add("a.wav", "A")
    add("b.wav", "B")
    add("c.wav", "A")
    before = queued(engine)
    player.unavailable = True
    for t in (0.0, 1.0, 6.0, 12.0, 30.0):
        clock[0] = t
        engine.tick()
    assert queued(engine) == before
    snap = engine.snapshot("A")
    assert snap["now_playing"] is None
    assert [i["song"] for i in snap["queue"]] == ["a.wav", "b.wav", "c.wav"]
    assert snap["audio_ok"] is False
    assert player.played == []


def test_no_pop_during_audio_backoff(engine, player, add, clock):
    assert PlaybackEngine.AUDIO_RETRY_SECONDS == 5.0
    add("a.wav", "A")
    player.unavailable = True
    engine.tick()
    assert player.attempts == 1
    for t in (0.5, 2.0, 4.99):
        clock[0] = t
        engine.tick()
    assert player.attempts == 1
    clock[0] = 5.0
    engine.tick()
    assert player.attempts == 2


def test_playback_resumes_with_the_same_first_song_after_backoff(engine, player, add, clock, lib_path):
    add("a.wav", "A")
    add("b.wav", "B")
    player.unavailable = True
    engine.tick()
    player.unavailable = False
    clock[0] = 3.0
    engine.tick()  # still backing off
    assert player.played == []
    clock[0] = 5.0
    engine.tick()
    assert player.played == [lib_path("a.wav")]
    snap = engine.snapshot("A")
    assert snap["now_playing"]["song"] == "a.wav"
    assert [i["song"] for i in snap["queue"]] == ["b.wav"]
    assert snap["audio_ok"] is True


def test_audio_retry_interval_is_injectable(engine_factory, player, clock):
    engine = engine_factory(player, clock, audio_retry_seconds=1.0)
    engine.enqueue("a.wav", "A")
    player.unavailable = True
    engine.tick()
    clock[0] = 1.0
    engine.tick()
    assert player.attempts == 2


def test_audio_outage_is_logged_once(engine, player, add, clock, caplog):
    add("a.wav", "A")
    player.unavailable = True
    with caplog.at_level("WARNING", logger="caseta.engine"):
        for t in range(0, 60, 5):
            clock[0] = float(t)
            engine.tick()
    assert player.attempts == 12
    assert len([r for r in caplog.records if r.levelno >= 30]) == 1


def test_new_outage_after_recovery_is_logged_again(engine, player, add, clock, caplog):
    add("a.wav", "A")
    add("b.wav", "B")
    with caplog.at_level("WARNING", logger="caseta.engine"):
        player.unavailable = True
        engine.tick()
        player.unavailable = False
        clock[0] = 5.0
        engine.tick()  # a.wav plays
        player.finish()
        player.unavailable = True
        clock[0] = 6.0
        engine.tick()  # b.wav cannot play
    assert len([r for r in caplog.records if r.levelno >= 30]) == 2
    assert engine.snapshot("A")["audio_ok"] is False
    assert [i["song"] for i in engine.snapshot("A")["queue"]] == ["b.wav"]


def test_corrupt_file_during_normal_playback_still_drops_only_that_song(engine, player, add):
    add("a.wav", "A")
    add("b.wav", "B")
    add("c.wav", "C")
    player.fail_next = True
    engine.tick()
    assert engine.snapshot("A")["audio_ok"] is True
    assert [i["song"] for i in engine.snapshot("A")["queue"]] == ["b.wav", "c.wav"]
    engine.tick()
    assert [p.name for p in player.played] == ["b.wav"]


def test_song_deleted_during_outage_is_dropped_but_outage_stays(engine, player, add, clock, songs):
    add("a.wav", "A")
    add("b.wav", "B")
    player.unavailable = True
    engine.tick()
    (songs / "a.wav").unlink()
    clock[0] = 5.0
    engine.tick()  # a.wav is gone: dropped without touching the player
    assert player.attempts == 1
    snap = engine.snapshot("A")
    assert snap["audio_ok"] is False
    assert [i["song"] for i in snap["queue"]] == ["b.wav"]


def test_pygame_player_reports_missing_audio_device_as_unavailable(monkeypatch, songs):
    import pygame

    from caseta.player import PlayerUnavailable, PygamePlayer

    def no_device(*args, **kwargs):
        raise pygame.error("No available audio device")

    monkeypatch.setattr(pygame.mixer, "init", no_device)
    with pytest.raises(PlayerUnavailable):
        PygamePlayer().play(songs / "a.wav")


def test_pygame_player_unreadable_file_is_an_ordinary_error(monkeypatch, songs):
    import pygame

    from caseta.player import PlayerUnavailable, PygamePlayer

    def corrupt(*args, **kwargs):
        raise pygame.error("Unrecognized audio format")

    monkeypatch.setattr(pygame.mixer, "init", lambda *a, **k: None)
    monkeypatch.setattr(pygame.mixer.music, "load", corrupt)
    with pytest.raises(pygame.error) as exc:
        PygamePlayer().play(songs / "a.wav")
    assert not isinstance(exc.value, PlayerUnavailable)


def test_pygame_player_imports_and_constructs_without_audio_device():
    from caseta.player import PygamePlayer

    p = PygamePlayer()
    assert p.is_playing() is False


# -- admin is not limited by the cap -------------------------------------------


def test_admin_enqueue_ignores_the_per_phone_cap(engine, songs):
    for name in ("a1.wav", "a2.wav", "a3.wav", "b1.wav", "d.wav"):
        engine.enqueue(name, "ADMIN")
    with pytest.raises(QueueFull):
        engine.enqueue("e.wav", "ADMIN")
    engine.enqueue("e.wav", "ADMIN", is_admin=True)
    assert engine.snapshot("ADMIN")["me"]["pending"] == 6


def test_snapshot_reports_no_limit_for_the_admin(engine):
    assert engine.snapshot("A")["me"] == {"pending": 0, "max": 5}
    assert engine.snapshot("A", is_admin=True)["me"] == {"pending": 0, "max": None}


# -- shuffle mode: random songs keep playing until it is turned off ----------------


@pytest.fixture
def tree(songs):
    """Two sections next to the root songs the `songs` fixture already made."""
    for name in ("r1", "r2", "r3", "r4", "r5", "r6", "r7"):
        make_wav(songs / "Rock" / f"{name}.wav", 1)
    for name in ("p1", "p2", "p3"):
        make_wav(songs / "Pop" / f"{name}.wav", 1)
    return songs


def shuffle_engine(engine_factory, player, clock, seed=1):
    return engine_factory(player, clock, rng=random.Random(seed))


def play_n(engine, player, n):
    """Let n songs play to the end (nothing is queued by hand); return their paths."""
    before = len(player.played)
    for _ in range(n * 3 + 5):
        engine.tick()
        if len(player.played) - before >= n:
            break
        player.finish()
    return player.played[before:before + n]


def played_songs(engine, player, root, n):
    return [p.relative_to(root.resolve()).as_posix() for p in play_n(engine, player, n)]


def test_shuffle_keeps_playing_songs_from_the_section_until_stopped(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    songs_played = played_songs(engine, player, tree, 20)  # more than the 7 songs in Rock
    assert len(songs_played) == 20
    assert all(s.startswith("Rock/") for s in songs_played)


def test_shuffle_plays_every_song_once_before_any_repeat(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    songs_played = played_songs(engine, player, tree, 21)
    for start in (0, 7, 14):
        assert sorted(songs_played[start:start + 7]) == sorted(f"Rock/r{n}.wav" for n in range(1, 8))
    for a, b in zip(songs_played, songs_played[1:]):
        assert a != b  # never the same song twice in a row, also across a reshuffle


def test_shuffle_in_todas_draws_from_the_whole_library(engine_factory, player, clock, tree, library):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Todas", "A")
    total = len(library.list_songs())
    songs_played = played_songs(engine, player, tree, total)
    assert sorted(songs_played) == sorted(library.list_songs())
    assert any("/" not in s for s in songs_played) and any(s.startswith("Pop/") for s in songs_played)


def test_songs_added_by_hand_always_play_before_the_next_random_one(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    engine.tick()  # a random Rock song starts
    engine.enqueue("a1.wav", "B")
    engine.enqueue("a2.wav", "B")
    for _ in range(3):
        player.finish()
        engine.tick()
    names = [p.name for p in player.played]
    assert names[1:3] == ["a1.wav", "a2.wav"]
    assert names[3].startswith("r")  # then random again


def test_queue_stays_first_come_first_served_while_shuffle_is_on(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Pop", "A")
    engine.enqueue("a1.wav", "A")
    engine.enqueue("a2.wav", "B")
    snap = engine.snapshot("A")
    assert [i["song"] for i in snap["queue"]] == ["a1.wav", "a2.wav"]  # random songs are never queued ahead


def test_stopping_shuffle_ends_the_loop_after_the_current_song(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    engine.tick()
    assert len(player.played) == 1
    engine.stop_shuffle("A")
    player.finish()
    engine.tick()
    assert len(player.played) == 1  # nothing new starts
    assert engine.snapshot("A")["now_playing"] is None
    assert engine.snapshot("A")["shuffle"] is None


def test_stop_shuffle_when_it_is_off_is_a_noop(engine):
    engine.stop_shuffle("A")
    engine.stop_shuffle("A", is_admin=True)


def test_only_the_starter_or_the_admin_can_stop_or_change_shuffle(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    with pytest.raises(NotOwner):
        engine.stop_shuffle("B")
    with pytest.raises(ShuffleLocked):
        engine.start_shuffle("Pop", "B")
    assert engine.snapshot("B")["shuffle"]["category"] == "Rock"
    engine.start_shuffle("Pop", "A")  # the starter can switch section
    assert engine.snapshot("A")["shuffle"]["category"] == "Pop"
    engine.start_shuffle("Todas", "ADMIN", is_admin=True)  # and so can the admin
    engine.stop_shuffle("B", is_admin=True)
    assert engine.snapshot("A")["shuffle"] is None


def test_anyone_can_start_shuffle_when_it_is_off(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    engine.stop_shuffle("A")
    engine.start_shuffle("Pop", "B")
    assert engine.snapshot("B")["shuffle"] == {"category": "Pop", "can_stop": True}


def test_snapshot_tells_each_viewer_whether_they_can_stop_it(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    assert engine.snapshot("A")["shuffle"] is None
    engine.start_shuffle("Rock", "A")
    assert engine.snapshot("A")["shuffle"] == {"category": "Rock", "can_stop": True}
    assert engine.snapshot("B")["shuffle"] == {"category": "Rock", "can_stop": False}
    assert engine.snapshot("B", is_admin=True)["shuffle"] == {"category": "Rock", "can_stop": True}


def test_unknown_or_empty_section_cannot_start_shuffle_and_changes_nothing(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    for bad in ("Nope", "Ro", "rock", "Rock/", "../Rock", ""):
        with pytest.raises(EmptyCategory):
            engine.start_shuffle(bad, "A")
    assert engine.snapshot("A")["shuffle"]["category"] == "Rock"


def test_a_random_song_belongs_to_the_phone_that_started_shuffle(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    engine.tick()
    now = engine.snapshot("A")["now_playing"]
    assert now["mine"] is True and engine.snapshot("B")["now_playing"]["mine"] is False
    with pytest.raises(NotOwner):
        engine.remove(now["id"], "B")
    engine.remove(now["id"], "A")  # the starter can skip a random song they dislike
    engine.tick()
    assert len(player.played) == 2  # the loop continues with the next random song


def test_skipping_a_random_song_starts_the_next_random_one(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Pop", "A")
    engine.tick()
    engine.skip()
    engine.tick()
    assert len(player.played) == 2
    assert player.played[0] != player.played[1]


def test_random_songs_do_not_count_toward_the_cap(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Rock", "A")
    played_songs(engine, player, tree, 8)
    assert engine.snapshot("A")["me"]["pending"] == 0
    for name in ("a1.wav", "a2.wav", "a3.wav", "b1.wav", "d.wav"):
        engine.enqueue(name, "A")  # all five slots are still free


def test_shuffle_waits_for_the_audio_device_without_losing_its_song(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Pop", "A")
    player.unavailable = True
    engine.tick()
    assert player.played == []
    clock[0] = 5.0
    engine.tick()
    assert player.played == []
    assert engine.snapshot("A")["audio_ok"] is False
    player.unavailable = False
    clock[0] = 10.0
    engine.tick()
    assert len(player.played) == 1
    assert engine.snapshot("A")["queue"] == []  # the retried song never became a queued item


def test_shuffle_turns_itself_off_when_its_section_is_emptied(engine_factory, player, clock, tree):
    engine = shuffle_engine(engine_factory, player, clock)
    engine.start_shuffle("Pop", "A")
    for f in (tree / "Pop").glob("*.wav"):
        f.unlink()
    engine.tick()
    assert player.played == []
    assert engine.snapshot("A")["shuffle"] is None


def test_the_injected_rng_drives_the_order(engine_factory, player, clock, tree):
    one = shuffle_engine(engine_factory, player, clock, seed=1)
    one.start_shuffle("Rock", "A")
    first = played_songs(one, player, tree, 7)
    other_player = FakePlayer()
    same = engine_factory(other_player, clock, rng=random.Random(1))
    same.start_shuffle("Rock", "A")
    assert played_songs(same, other_player, tree, 7) == first
    third_player = FakePlayer()
    different = engine_factory(third_player, clock, rng=random.Random(2))
    different.start_shuffle("Rock", "A")
    assert played_songs(different, third_player, tree, 7) != first
