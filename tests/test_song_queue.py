import random

import pytest

from caseta.song_queue import DuplicateSong, NotOwner, QueueFull, SongQueue, UnknownItem


def order(q):
    return [i.song for i in q.snapshot()]


def test_songs_play_in_the_order_they_were_added():
    q = SongQueue(max_pending_per_user=5)
    for s in ("a1", "a2", "a3"):
        q.add(s, "A")
    assert order(q) == ["a1", "a2", "a3"]


def test_five_songs_then_five_from_another_phone_are_positions_1_to_5_and_6_to_10():
    q = SongQueue(5)
    for n in range(1, 6):
        q.add(f"a{n}", "A")
    for n in range(1, 6):
        q.add(f"b{n}", "B")
    assert order(q) == [f"a{n}" for n in range(1, 6)] + [f"b{n}" for n in range(1, 6)]


def test_interleaved_adds_keep_arrival_order():
    q = SongQueue(5)
    for song, owner in (("a1", "A"), ("b1", "B"), ("a2", "A"), ("c1", "C"), ("b2", "B")):
        q.add(song, owner)
    assert order(q) == ["a1", "b1", "a2", "c1", "b2"]


def test_a_song_added_after_another_has_started_playing_still_goes_last():
    q = SongQueue(5)
    q.add("a1", "A")
    q.add("a2", "A")
    q.add("b1", "B")
    assert q.pop_next().song == "a1"
    q.add("a3", "A")  # A was just served; that does not matter, arrival order rules
    q.add("c1", "C")
    assert order(q) == ["a2", "b1", "a3", "c1"]


def test_cap_raises_queue_full():
    q = SongQueue(2)
    q.add("a1", "A")
    q.add("a2", "A")
    with pytest.raises(QueueFull):
        q.add("a3", "A")
    q.add("b1", "B")  # the cap is per phone


def test_cap_frees_up_after_pop():
    q = SongQueue(1)
    q.add("a1", "A")
    q.pop_next()
    q.add("a2", "A")


def test_duplicate_song_rejected_even_from_another_owner():
    q = SongQueue(5)
    q.add("x", "A")
    with pytest.raises(DuplicateSong):
        q.add("x", "B")


def test_duplicate_is_reported_before_the_cap():
    q = SongQueue(1)
    q.add("x", "A")
    with pytest.raises(DuplicateSong):
        q.add("x", "A")


def test_only_owner_or_admin_can_remove():
    q = SongQueue(5)
    item = q.add("x", "A")
    with pytest.raises(NotOwner):
        q.remove(item.id, requester="B")
    assert q.remove(item.id, requester="B", is_admin=True) == item
    assert q.snapshot() == []


def test_remove_unknown_item():
    with pytest.raises(UnknownItem):
        SongQueue(5).remove("nope", "A")


def test_removing_a_song_keeps_everyone_elses_order():
    q = SongQueue(5)
    q.add("a1", "A")
    b1 = q.add("b1", "B")
    q.add("a2", "A")
    q.add("c1", "C")
    q.remove(b1.id, "B")
    assert order(q) == ["a1", "a2", "c1"]


def test_admin_move_reorders_and_clamps():
    q = SongQueue(5)
    q.add("a1", "A")
    q.add("b1", "B")
    c1 = q.add("c1", "C")
    q.move(c1.id, 1)
    assert order(q) == ["c1", "a1", "b1"]
    q.move(c1.id, 99)
    assert order(q) == ["a1", "b1", "c1"]
    q.move(c1.id, 0)
    assert order(q) == ["c1", "a1", "b1"]
    q.move(c1.id, 2)
    assert order(q) == ["a1", "c1", "b1"]


def test_songs_added_after_an_admin_move_still_go_last():
    q = SongQueue(5)
    q.add("a1", "A")
    q.add("b1", "B")
    q.add("a2", "A")
    a2 = q.snapshot()[2]
    q.move(a2.id, 1)
    q.add("d1", "D")
    q.add("b2", "B")
    assert order(q) == ["a2", "a1", "b1", "d1", "b2"]


def test_move_unknown_item():
    with pytest.raises(UnknownItem):
        SongQueue(5).move("nope", 1)


def test_pop_next_on_empty_returns_none():
    assert SongQueue(5).pop_next() is None


def test_push_front_puts_a_popped_song_back_at_the_head():
    q = SongQueue(5)
    q.add("a1", "A")
    q.add("b1", "B")
    item = q.pop_next()
    q.push_front(item)
    assert order(q) == ["a1", "b1"]
    assert q.pop_next() == item


def test_pending_count_is_per_owner_and_excludes_popped_songs():
    q = SongQueue(5)
    q.add("a1", "A")
    q.add("a2", "A")
    q.add("b1", "B")
    q.pop_next()
    assert (q.pending_count("A"), q.pending_count("B"), q.pending_count("Z")) == (1, 1, 0)


def test_snapshot_is_a_copy():
    q = SongQueue(5)
    q.add("a1", "A")
    q.snapshot().clear()
    assert order(q) == ["a1"]


def test_random_operations_match_a_plain_list_model():
    rng = random.Random(7)
    for _ in range(100):
        q = SongQueue(3)
        model = []  # (song, owner, id) in play order
        serial = 0
        for _ in range(150):
            action = rng.choice(["add", "add", "add", "pop", "remove", "move"])
            owner = rng.choice("ABCD")
            if action == "add":
                serial += 1
                song = f"s{rng.randint(1, 12)}"
                dup = any(m[0] == song for m in model)
                full = sum(1 for m in model if m[1] == owner) >= 3
                if dup:
                    with pytest.raises(DuplicateSong):
                        q.add(song, owner)
                elif full:
                    with pytest.raises(QueueFull):
                        q.add(song, owner)
                else:
                    item = q.add(song, owner)
                    model.append((song, owner, item.id))
            elif action == "pop":
                item = q.pop_next()
                expected = model.pop(0) if model else None
                assert (item.id if item else None) == (expected[2] if expected else None)
            elif action == "remove" and model:
                victim = rng.choice(model)
                q.remove(victim[2], victim[1])
                model.remove(victim)
            elif action == "move" and model:
                victim = rng.choice(model)
                position = rng.randint(0, len(model) + 2)
                q.move(victim[2], position)
                model.remove(victim)
                model.insert(max(1, min(position, len(model) + 1)) - 1, victim)
            assert [i.id for i in q.snapshot()] == [m[2] for m in model]
