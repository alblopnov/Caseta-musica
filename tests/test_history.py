import pytest

from caseta.history import PlayHistory


@pytest.fixture
def now():
    return [0.0]


def history(now, cooldown):
    return PlayHistory(cooldown, clock=lambda: now[0])


def test_a_song_that_never_played_is_not_blocked(now):
    assert history(now, 100).remaining("k") == 0


def test_a_played_song_is_blocked_for_the_rest_of_the_cooldown(now):
    h = history(now, 100)
    h.record("k")
    now[0] = 30.0
    assert h.remaining("k") == 70


def test_the_block_ends_exactly_when_the_cooldown_has_passed(now):
    h = history(now, 100)
    h.record("k")
    now[0] = 99.0
    assert h.remaining("k") == 1
    now[0] = 100.0
    assert h.remaining("k") == 0


def test_blocking_one_song_leaves_others_free(now):
    h = history(now, 100)
    h.record("k")
    assert h.remaining("other") == 0


def test_playing_a_song_again_restarts_its_cooldown(now):
    h = history(now, 100)
    h.record("k")
    now[0] = 60.0
    h.record("k")
    now[0] = 120.0
    assert h.remaining("k") == 40


def test_a_zero_cooldown_blocks_nothing(now):
    h = history(now, 0)
    h.record("k")
    assert h.remaining("k") == 0
