import time

import pytest

from caseta.engine import PlaybackEngine
from caseta.fair_queue import DuplicateSong, FairQueue, NotOwner, QueueFull, UnknownItem
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
    def build(player, clock=None, poll_interval=0.25):
        t = clock if clock is not None else [0.0]
        queue = FairQueue(config.max_pending_per_user)
        return PlaybackEngine(queue, player, library, clock=lambda: t[0], poll_interval=poll_interval)

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


def test_fairness_end_to_end(engine, player, add):
    for s in ("a1.wav", "a2.wav", "a3.wav"):
        add(s, "A")
    add("b1.wav", "B")
    played = drain(engine, player)
    assert [p.name for p in played] == ["a1.wav", "b1.wav", "a2.wav", "a3.wav"]


def test_readding_while_own_song_plays_does_not_cut_ahead(engine, player, add):
    for s in ("a1.wav", "a2.wav", "a3.wav"):
        add(s, "A")
    add("b1.wav", "B")
    engine.tick()  # a1
    player.finish()
    engine.tick()  # b1 starts; B queues another song right away
    add("d.wav", "B")
    played = drain(engine, player)
    assert [p.name for p in played] == ["a1.wav", "b1.wav", "a2.wav", "d.wav", "a3.wav"]


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


def test_pygame_player_imports_and_constructs_without_audio_device():
    from caseta.player import PygamePlayer

    p = PygamePlayer()
    assert p.is_playing() is False
