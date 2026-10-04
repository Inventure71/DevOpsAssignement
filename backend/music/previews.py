"""Cache media references without caching another player's listening evidence."""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from copy import deepcopy

from backend.core.errors import DomainError
from backend.music.media import normalized_words, allowed_preview_url, preview_cache_ttl
from backend.catalog.identity import recording_title
from backend.catalog import links
from backend.music.recordings import Recordings


class PreviewResolver:
    """Process-wide media cache and bounded duplicate-request coalescing."""

    def __init__(
        self,
        apple,
        monotonic=time.monotonic,
        *,
        store=None,
        clock=time.time,
        provider_scope=None,
    ):
        self.monotonic = monotonic
        self.store, self.clock = store, clock
        self.provider_scope = provider_scope or "apple:" + getattr(
            apple, "storefront", "default"
        )
        self.recordings = Recordings(
            apple, store.links if store else None, self.provider_scope, clock
        )
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.inflight = {}
        self.workers = threading.BoundedSemaphore(4)

    def _find(self, song):
        resolved = self.recordings.resolve(song)
        if not resolved:
            return None
        if (
            not allowed_preview_url(resolved.get("preview_url"))
            or preview_cache_ttl(resolved.get("preview_url"), self.clock()) <= 0
        ):
            return None
        media = {
            key: resolved[key]
            for key in ("preview_url", "artwork_url")
            if key in resolved
        }
        media["artist_aliases"] = [
            {"name": credit["name"], "aliases": credit["aliases"]}
            for credit in resolved.get("artists", [])
            if credit.get("aliases")
        ]
        if resolved.get("_catalog_song"):
            media["catalog_song"] = resolved["_catalog_song"]
        return media

    def _attach_media(self, song, media):
        if media and media.get("catalog_song"):
            self.recordings.remember(song, media["catalog_song"])
        return self._attach(song, media)

    def _key(self, song):
        credits = song.get("artists") or []
        lead = credits[0]["name"] if credits else song["artist"]
        identity = [
            links.MATCH_RULE_VERSION,
            self.provider_scope,
            song.get("isrc") or song["song_key"],
            recording_title(song["title"]),
            normalized_words(lead),
            sorted({normalized_words(credit["name"]) for credit in credits}),
        ]
        return hashlib.sha256(
            json.dumps(identity, ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def _stored_result(value):
        if isinstance(value, dict) and "error" in value:
            error = value["error"]
            return DomainError(
                error["code"], error["message"], error["status"], error["details"]
            )
        if value is not None and not allowed_preview_url(value.get("preview_url")):
            return None
        return value

    def resolve(self, song):
        key = self._key(song)
        with self.lock:
            cached = self.cache.get(key)
            if (
                cached
                and isinstance(cached[1], dict)
                and (
                    preview_cache_ttl(cached[1].get("preview_url"), self.clock()) <= 0
                    or (
                        "catalog_song" in cached[1]
                        and not self.recordings.compatible(
                            song, cached[1]["catalog_song"]
                        )
                    )
                )
            ):
                self.cache.pop(key)
                cached = None
            if cached and cached[0] > self.monotonic():
                self.cache.move_to_end(key)
                if isinstance(cached[1], DomainError):
                    raise cached[1]
                return self._attach_media(song, cached[1])
            waiting = self.inflight.get(key)
            if waiting is None:
                self.inflight[key] = threading.Event()
        if waiting is not None:
            if not waiting.wait(120):
                raise DomainError(
                    "preview_provider_unavailable",
                    "Preview matching timed out. Retry.",
                    503,
                )
            return self.resolve(song)
        result, completed, persisted = None, False, False
        try:
            if self.store:
                found, value = self.store.preview(key, self.clock())
                if found and isinstance(value, dict) and "error" not in value:
                    if (
                        not allowed_preview_url(value.get("preview_url"))
                        or preview_cache_ttl(value.get("preview_url"), self.clock())
                        <= 0
                        or (
                            "catalog_song" in value
                            and not self.recordings.compatible(
                                song, value["catalog_song"]
                            )
                        )
                    ):
                        found = False
                if found:
                    persisted = True
                    result = self._stored_result(value)
                    # Store hits retain their original expiry: repeated reads never
                    # extend the lifetime of a potentially expiring provider URL.
                    if isinstance(result, DomainError):
                        raise result
                    return self._attach_media(song, result)
            if not self.workers.acquire(timeout=45):
                raise DomainError(
                    "preview_provider_busy",
                    "Preview matching is busy. Retry shortly.",
                    429,
                )
            try:
                result = self._find(song)
                completed = True
            finally:
                self.workers.release()
            return self._attach(song, result)
        except DomainError as exc:
            result = exc
            completed = True
            raise
        finally:
            ttl = (
                10
                if isinstance(result, DomainError)
                else (
                    preview_cache_ttl(result["preview_url"], self.clock())
                    if result
                    else 60
                )
            )
            try:
                if completed and not persisted and self.store:
                    value = (
                        {
                            "error": {
                                "code": result.code,
                                "message": result.message,
                                "status": result.status,
                                "details": result.details,
                            }
                        }
                        if isinstance(result, DomainError)
                        else result
                    )
                    self.store.save_preview(key, value, self.clock(), ttl)
            finally:
                with self.lock:
                    # Durable hits bypass the memory cache to preserve exact expiry.
                    if completed and not persisted:
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
            aliases = [
                alias
                for record in media.get("artist_aliases", [])
                if normalized_words(record["name"]) == normalized_words(credit["name"])
                for alias in record["aliases"]
            ]
            if aliases:
                credit["aliases"] = list(
                    dict.fromkeys(credit.get("aliases", []) + aliases)
                )
        return resolved
