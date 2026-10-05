import pytest

from caseta.fair_queue import FairQueue, QueueItem, QueueFull, DuplicateSong, NotOwner, UnknownItem


def order(q):
    return [i.song for i in q.snapshot()]


def test_newcomer_does_not_wait_behind_a_spammer():
    q = FairQueue(max_pending_per_user=5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    q.add("b1", "B")
    assert order(q) == ["a1", "b1", "a2", "a3"]


def test_round_robin_three_users():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    q.add("b1", "B")
    q.add("c1", "C")
    q.add("b2", "B")
    assert order(q) == ["a1", "b1", "c1", "a2", "b2", "a3"]


def test_owner_who_just_got_played_does_not_jump_ahead():
    q = FairQueue(5)
    q.add("a1", "A")
    q.add("a2", "A")
    q.add("b1", "B")
    assert q.pop_next().song == "a1"
    assert order(q) == ["b1", "a2"]


def test_owners_own_songs_keep_their_order():
    q = FairQueue(5)
    for s in ("a1", "b1", "a2", "b2", "a3"):
        q.add(s, s[0].upper())
    assert [s for s in order(q) if s[0] == "a"] == ["a1", "a2", "a3"]


def test_cap_raises_queue_full():
    q = FairQueue(2)
    q.add("a1", "A")
    q.add("a2", "A")
    with pytest.raises(QueueFull):
        q.add("a3", "A")


def test_cap_frees_up_after_pop():
    q = FairQueue(1)
    q.add("a1", "A")
    q.pop_next()
    q.add("a2", "A")


def test_duplicate_song_rejected_even_from_another_owner():
    q = FairQueue(5)
    q.add("x", "A")
    with pytest.raises(DuplicateSong):
        q.add("x", "B")


def test_only_owner_or_admin_can_remove():
    q = FairQueue(5)
    item = q.add("x", "A")
    with pytest.raises(NotOwner):
        q.remove(item.id, requester="B")
    assert q.remove(item.id, requester="B", is_admin=True) == item


def test_remove_unknown_item():
    with pytest.raises(UnknownItem):
        FairQueue(5).remove("nope", "A")


def test_remove_closes_the_gap_in_owner_rounds():
    q = FairQueue(5)
    a1 = q.add("a1", "A")
    q.add("a2", "A")
    q.add("b1", "B")
    q.remove(a1.id, "A")
    assert order(q) == ["b1", "a2"]
    assert q.snapshot()[1].round == 0  # a2 was round 1, decremented to 0


def test_admin_move_overrides_fairness_and_clamps():
    q = FairQueue(5)
    a1 = q.add("a1", "A")
    q.add("b1", "B")
    q.add("a2", "A")
    q.move(a1.id, 99)
    assert order(q) == ["b1", "a2", "a1"]
    q.move(a1.id, 0)
    assert order(q)[0] == "a1"


def test_move_unknown_item():
    with pytest.raises(UnknownItem):
        FairQueue(5).move("nope", 1)


def test_pop_next_on_empty_returns_none():
    assert FairQueue(5).pop_next() is None
