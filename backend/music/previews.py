"""Cache media references without caching another player's listening evidence."""

import threading
import time
from collections import OrderedDict
from copy import deepcopy

from backend.core.errors import DomainError
from backend.music.media import normalized_words


class PreviewResolver:
    """Process-wide media cache and bounded duplicate-request coalescing."""

    def __init__(self, apple, monotonic=time.monotonic):
        self.apple, self.monotonic = apple, monotonic
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.inflight = {}
        self.workers = threading.BoundedSemaphore(4)

    def _find(self, song):
        resolved = self.apple.resolve(song)
        if not resolved:
            return None
        media = {key: resolved[key] for key in ("preview_url", "artwork_url") if key in resolved}
        media["artist_aliases"] = [{"name": credit["name"], "aliases": credit["aliases"]}
                                   for credit in resolved.get("artists", []) if credit.get("aliases")]
        return media

    def resolve(self, song):
        key = (song["song_key"], song["title"], song["artist"])
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > self.monotonic():
                self.cache.move_to_end(key)
                if isinstance(cached[1], DomainError):
                    raise cached[1]
                return self._attach(song, cached[1])
            waiting = self.inflight.get(key)
            if waiting is None:
                self.inflight[key] = threading.Event()
        if waiting is not None:
            if not waiting.wait(120):
                raise DomainError("preview_provider_unavailable", "Preview matching timed out. Retry.", 503)
            return self.resolve(song)
        result = None
        try:
            if not self.workers.acquire(timeout=45):
                raise DomainError("preview_provider_busy", "Preview matching is busy. Retry shortly.", 429)
            try:
                result = self._find(song)
            finally:
                self.workers.release()
            return self._attach(song, result)
        except DomainError as exc:
            result = exc
            raise
        finally:
            with self.lock:
                ttl = 10 if isinstance(result, DomainError) else (1200 if result else 60)
                self.cache[key] = (self.monotonic() + ttl, result)
                while len(self.cache) > 512:
                    self.cache.popitem(last=False)
                self.inflight.pop(key).set()

    @staticmethod
    def _attach(song, media):
        if media is None:
            return None
        resolved = deepcopy(song)
        resolved["preview_url"] = media["preview_url"]
        if not resolved.get("artwork_url") and media.get("artwork_url"):
            resolved["artwork_url"] = media["artwork_url"]
        for credit in resolved.get("artists", []):
            aliases = [alias for record in media.get("artist_aliases", []) if normalized_words(record["name"]) == normalized_words(credit["name"])
                       for alias in record["aliases"]]
            if aliases:
                credit["aliases"] = list(dict.fromkeys(credit.get("aliases", []) + aliases))
        return resolved
