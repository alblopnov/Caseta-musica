"""First-come, first-served song queue. Pure logic, not thread-safe (the caller holds the lock).

Songs play in the order they were added, whoever added them: five songs from one
phone followed by five from another are positions 1 to 5 and 6 to 10. The only
rules besides order are a cap on how many songs one phone may have waiting (the
admin is exempt) and that the same song cannot be waiting twice. Only the admin
can reorder.
"""
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class QueueItem:
    id: str
    song: str
    owner: str


class QueueFull(Exception):
    pass


class DuplicateSong(Exception):
    pass


class NotOwner(Exception):
    pass


class UnknownItem(Exception):
    pass


class SongQueue:
    def __init__(self, max_pending_per_user: int):
        self.max_pending_per_user = max_pending_per_user
        self._items: list[QueueItem] = []

    def add(self, song: str, owner: str, is_admin: bool = False) -> QueueItem:
        if any(i.song == song for i in self._items):
            raise DuplicateSong(song)
        if not is_admin and self.pending_count(owner) >= self.max_pending_per_user:
            raise QueueFull(owner)
        item = QueueItem(id=uuid4().hex, song=song, owner=owner)
        self._items.append(item)
        return item

    def pop_next(self) -> QueueItem | None:
        return self._items.pop(0) if self._items else None

    def push_front(self, item: QueueItem) -> None:
        """Put back an item just taken by ``pop_next`` (it could not be played).

        It goes first again; no cap or duplicate checks."""
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
        return item

    def move(self, item_id: str, position: int) -> None:
        """Admin override: put the item at 1-based ``position`` (clamped)."""
        pos = self._index_of(item_id)
        item = self._items.pop(pos)
        target = max(1, min(position, len(self._items) + 1)) - 1
        self._items.insert(target, item)

    def snapshot(self) -> list[QueueItem]:
        return list(self._items)

    def pending_count(self, owner: str) -> int:
        return sum(1 for i in self._items if i.owner == owner)
