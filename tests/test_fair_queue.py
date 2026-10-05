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


# -- virtual-time rounds: being served does not reset your place -------------


def drain_rounds(q):
    return [(i.song, i.round) for i in q.snapshot()]


def test_readd_after_being_played_does_not_cut_ahead():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    q.add("b1", "B")
    assert [q.pop_next().song for _ in range(2)] == ["a1", "b1"]
    q.add("b2", "B")
    assert order(q) == ["a2", "b2", "a3"]


def test_one_at_a_time_trickle_never_starves_a_multi_song_owner():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    q.add("b1", "B")
    played = []
    n = 1
    for _ in range(8):
        item = q.pop_next()
        played.append(item.song)
        if item.owner == "B":  # B re-adds one song each time theirs starts
            n += 1
            q.add(f"b{n}", "B")
    assert played == ["a1", "b1", "a2", "b2", "a3", "b3", "b4", "b5"]


def test_newcomer_after_trickle_still_goes_before_later_rounds():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    q.add("b1", "B")
    q.pop_next()  # a1
    q.pop_next()  # b1
    q.add("b2", "B")
    q.pop_next()  # a2 (round 1)
    q.pop_next()  # b2
    q.add("b3", "B")
    assert order(q) == ["a3", "b3"]
    q.add("c1", "C")  # never served: current round, ahead of the round-2 songs
    assert order(q) == ["c1", "a3", "b3"]


def test_add_after_admin_move_does_not_jump_the_moved_song():
    q = FairQueue(5)
    q.add("a1", "A")
    q.add("b1", "B")
    q.add("a2", "A")
    a3 = q.add("a3", "A")
    assert order(q) == ["a1", "b1", "a2", "a3"]
    q.move(a3.id, 1)
    assert order(q) == ["a3", "a1", "b1", "a2"]
    q.add("d1", "D")
    q.add("b2", "B")
    assert order(q) == ["a3", "a1", "b1", "d1", "a2", "b2"]


def test_move_keeps_rounds_sorted():
    q = FairQueue(5)
    for s, o in (("a1", "A"), ("b1", "B"), ("a2", "A"), ("a3", "A"), ("c1", "C")):
        q.add(s, o)
    ids = {i.song: i.id for i in q.snapshot()}
    for song, pos in (("a3", 1), ("a1", 99), ("b1", 3), ("c1", 2)):
        q.move(ids[song], pos)
        rounds = [i.round for i in q.snapshot()]
        assert rounds == sorted(rounds), (song, drain_rounds(q))


def test_move_to_same_position_changes_nothing():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    before = drain_rounds(q)
    for item in q.snapshot():
        q.move(item.id, before.index((item.song, item.round)) + 1)
    assert drain_rounds(q) == before


def test_remove_then_readd_returns_to_the_old_place():
    q = FairQueue(5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    q.add("b1", "B")
    q.pop_next()  # a1
    q.pop_next()  # b1
    b2 = q.add("b2", "B")
    assert order(q) == ["a2", "b2", "a3"]
    q.remove(b2.id, "B")
    q.add("b3", "B")  # neither penalised behind a3 nor promoted before a2
    assert order(q) == ["a2", "b3", "a3"]


def test_remove_then_newcomer_joins_current_round():
    q = FairQueue(5)
    a1 = q.add("a1", "A")
    q.add("a2", "A")
    q.add("b1", "B")
    q.remove(a1.id, "A")
    q.add("c1", "C")
    assert order(q) == ["b1", "a2", "c1"]
    assert [i.round for i in q.snapshot()] == [0, 0, 0]


def test_remove_middle_song_shifts_owner_later_songs_forward():
    q = FairQueue(5)
    q.add("a1", "A")
    a2 = q.add("a2", "A")
    q.add("a3", "A")
    q.add("b1", "B")
    q.add("b2", "B")
    q.remove(a2.id, "A")
    assert drain_rounds(q) == [("a1", 0), ("b1", 0), ("b2", 1), ("a3", 1)]
    q.add("a4", "A")
    assert order(q) == ["a1", "b1", "b2", "a3", "a4"]


def test_round_never_negative_after_move_and_remove():
    q = FairQueue(5)
    a1 = q.add("a1", "A")
    q.add("b1", "B")
    a2 = q.add("a2", "A")
    q.move(a1.id, 99)
    assert order(q) == ["b1", "a2", "a1"]
    q.remove(a2.id, "A")
    assert order(q) == ["b1", "a1"]
    assert all(i.round >= 0 for i in q.snapshot())


def test_last_round_memory_stays_bounded_as_owners_come_and_go():
    q = FairQueue(5)
    played = []
    for n in range(300):
        q.add(f"t{n}", f"T{n}")  # a different phone every time
        q.add(f"p{n}", "P")  # one regular keeps the rounds moving
        played += [q.pop_next().song, q.pop_next().song]
        assert len(q._last_round) <= 3
    assert played[:4] == ["t0", "p0", "t1", "p1"]
    assert q.pop_next() is None


def test_push_front_restores_a_popped_item_with_its_round():
    q = FairQueue(5)
    for s in ("a1", "a2"):
        q.add(s, "A")
    q.add("b1", "B")
    q.pop_next()  # a1
    item = q.pop_next()  # b1
    q.push_front(item)
    assert drain_rounds(q) == [("b1", 0), ("a2", 1)]
    q.add("c1", "C")
    assert order(q) == ["b1", "c1", "a2"]
    assert q.pop_next() is item


def test_random_operations_keep_the_round_invariants():
    import random

    rng = random.Random(1234)
    q = FairQueue(3)
    owners = ["A", "B", "C", "D"]
    n = 0
    for _ in range(3000):
        op = rng.random()
        items = q.snapshot()
        before = q._current_round
        if op < 0.45:
            n += 1
            try:
                q.add(f"s{n}", rng.choice(owners))
            except QueueFull:
                pass
        elif op < 0.7:
            q.pop_next()
        elif op < 0.85 and items:
            victim = rng.choice(items)
            q.remove(victim.id, victim.owner)
        elif items:
            q.move(rng.choice(items).id, rng.randint(0, len(items) + 1))
        rounds = [i.round for i in q.snapshot()]
        assert rounds == sorted(rounds)
        assert all(r >= q._current_round >= 0 for r in rounds)
        assert q._current_round >= before
        assert all(r >= q._current_round for r in q._last_round.values())
