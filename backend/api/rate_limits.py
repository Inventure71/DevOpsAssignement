"""Bound room creation and joining per client address in this server process."""

import threading
from collections import defaultdict, deque

from backend.core.errors import DomainError


class AdmissionLimits:
    def __init__(self, create_limit=10, join_limit=30):
        self.limits = {"create": create_limit, "join": join_limit}
        self.windows = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, kind, address, now):
        with self.lock:
            # Remove idle buckets; don't retain every historical visitor address.
            for key in list(self.windows):
                if not self.windows[key] or self.windows[key][-1] <= now - 60_000:
                    del self.windows[key]
            events = self.windows[(kind, address)]
            while events and events[0] <= now - 60_000:
                events.popleft()
            if len(events) >= self.limits[kind]:
                raise DomainError(
                    "rate_limited", "Too many attempts. Try again in a minute.", 429
                )
            events.append(now)
