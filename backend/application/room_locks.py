"""Serialize a room's operations without retaining idle room identifiers."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import threading


@dataclass
class _Entry:
    lock: object = field(default_factory=threading.RLock)
    users: int = 0


class RoomLocks:
    def __init__(self):
        self._entries = {}
        self._guard = threading.Lock()

    @contextmanager
    def hold(self, room_id):
        # Count waiters before releasing the guard, so a releasing holder cannot
        # remove an entry that a queued operation is about to acquire.
        with self._guard:
            entry = self._entries.get(room_id)
            if entry is None:
                entry = self._entries[room_id] = _Entry()
            entry.users += 1
        try:
            with entry.lock:
                yield
        finally:
            with self._guard:
                entry.users -= 1
                if entry.users == 0:
                    del self._entries[room_id]

    def __len__(self):
        with self._guard:
            return len(self._entries)
