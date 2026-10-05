"""Fair round-robin queue. Pure logic, not thread-safe (the caller holds the lock)."""
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

    def add(self, song: str, owner: str) -> QueueItem:
        if any(i.song == song for i in self._items):
            raise DuplicateSong(song)
        own_rounds = [i.round for i in self._items if i.owner == owner]
        if len(own_rounds) >= self.max_pending_per_user:
            raise QueueFull(owner)
        rnd = 1 + max(own_rounds) if own_rounds else 0
        item = QueueItem(id=uuid4().hex, song=song, owner=owner, round=rnd)
        index = len(self._items)
        for pos, other in enumerate(self._items):
            if other.round > rnd:
                index = pos
                break
        self._items.insert(index, item)
        return item

    def pop_next(self) -> QueueItem | None:
        if not self._items:
            return None
        return self._items.pop(0)

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
        for later in range(pos, len(self._items)):
            other = self._items[later]
            if other.owner == item.owner:
                self._items[later] = replace(other, round=other.round - 1)
        return item

    def move(self, item_id: str, position: int) -> None:
        pos = self._index_of(item_id)
        item = self._items.pop(pos)
        target = max(1, min(position, len(self._items) + 1))
        self._items.insert(target - 1, item)

    def snapshot(self) -> list[QueueItem]:
        return list(self._items)

    def pending_count(self, owner: str) -> int:
        return sum(1 for i in self._items if i.owner == owner)
