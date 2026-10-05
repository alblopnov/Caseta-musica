"""Fair round-robin queue. Pure logic, not thread-safe (the caller holds the lock).

Rounds work like virtual time. ``_current_round`` is the round of the last song
that left the queue to play. An owner's next song goes one round after their
previous one (``_last_round``), and never earlier than the current round, so
having a song played does not reset your place: a phone that re-adds one song
each time theirs starts cannot cut ahead of other people's waiting songs.
``_items`` is always in play order and sorted by round (stable): a song goes
after every pending song of its own round or earlier.
"""
from dataclasses import dataclass, replace
from uuid import uuid4


@dataclass(frozen=True)
class QueueItem:
    id: str
    song: str
    owner: str
    round: int


class QueueFull(Exception):
    pass


class DuplicateSong(Exception):
    pass


class NotOwner(Exception):
    pass


class UnknownItem(Exception):
    pass


class FairQueue:
    def __init__(self, max_pending_per_user: int):
        self.max_pending_per_user = max_pending_per_user
        self._items: list[QueueItem] = []
        self._current_round = 0
        # Round of each owner's most recent song. Entries below the current round
        # compute the same as no entry and are pruned, so this stays small.
        self._last_round: dict[str, int] = {}

    def _next_round(self, owner: str) -> int:
        last = self._last_round.get(owner)
        if last is None:
            return self._current_round
        return max(self._current_round, last + 1)

    def _claim(self, owner: str, rnd: int) -> None:
        if rnd >= self._last_round.get(owner, rnd):
            self._last_round[owner] = rnd

    def _prune(self) -> None:
        stale = [o for o, r in self._last_round.items() if r < self._current_round]
        for owner in stale:
            del self._last_round[owner]

    def _insert_by_round(self, item: QueueItem) -> None:
        index = len(self._items)
        for pos, other in enumerate(self._items):
            if other.round > item.round:
                index = pos
                break
        self._items.insert(index, item)

    def add(self, song: str, owner: str) -> QueueItem:
        if any(i.song == song for i in self._items):
            raise DuplicateSong(song)
        if self.pending_count(owner) >= self.max_pending_per_user:
            raise QueueFull(owner)
        self._prune()
        rnd = self._next_round(owner)
        item = QueueItem(id=uuid4().hex, song=song, owner=owner, round=rnd)
        self._insert_by_round(item)
        self._last_round[owner] = rnd
        return item

    def pop_next(self) -> QueueItem | None:
        if not self._items:
            return None
        item = self._items.pop(0)
        self._current_round = max(self._current_round, item.round)
        self._prune()
        return item

    def push_front(self, item: QueueItem) -> None:
        """Put back an item just taken by ``pop_next`` (it could not be played).

        It keeps its round and goes first again; no cap or duplicate checks, and
        neither ``_last_round`` nor ``_current_round`` changes."""
        self._items.insert(0, item)

    def _index_of(self, item_id: str) -> int:
        for pos, item in enumerate(self._items):
            if item.id == item_id:
                return pos
        raise UnknownItem(item_id)

    def remove(self, item_id: str, requester: str, is_admin: bool = False) -> QueueItem:
        pos = self._index_of(item_id)
        item = self._items[pos]
        if item.owner != requester and not is_admin:
            raise NotOwner(item_id)
        del self._items[pos]
        # The owner's later songs move up one round (never below the current one).
        for later in range(pos, len(self._items)):
            other = self._items[later]
            if other.owner == item.owner:
                self._items[later] = replace(other, round=max(self._current_round, other.round - 1))
        self._items.sort(key=lambda i: i.round)  # stable: ties keep their order
        # Their later slots all moved up one, so their next song goes where the
        # removed one was (if it was their last) and never before a remaining one.
        remaining = [i.round for i in self._items if i.owner == item.owner]
        last = max(remaining + [self._last_round.get(item.owner, item.round) - 1])
        if last < self._current_round:
            self._last_round.pop(item.owner, None)
        else:
            self._last_round[item.owner] = last
        return item

    def move(self, item_id: str, position: int) -> None:
        """Admin override: put the item at 1-based ``position`` (clamped).

        The item takes the round of the song that now follows it (or, when it
        goes last, the round of the song before it), so later arrivals are still
        ordered by round around it and cannot jump in front of a song the admin
        moved up."""
        pos = self._index_of(item_id)
        target = max(1, min(position, len(self._items))) - 1
        if target == pos:
            return
        item = self._items.pop(pos)
        if target < len(self._items):
            rnd = self._items[target].round
        elif self._items:
            rnd = max(item.round, self._items[-1].round)
        else:
            rnd = self._current_round
        moved = replace(item, round=rnd)
        self._items.insert(target, moved)
        self._claim(item.owner, rnd)

    def snapshot(self) -> list[QueueItem]:
        return list(self._items)

    def pending_count(self, owner: str) -> int:
        return sum(1 for i in self._items if i.owner == owner)
