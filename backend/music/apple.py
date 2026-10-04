"""Apple developer catalog metadata and conservative recording-preview matching."""

import re
import threading
import time
from pathlib import Path
from copy import deepcopy
from urllib.parse import quote, urlencode

from backend.music.http import JsonHttpTransport, MusicProviderError, ProviderHttpError
from backend.music.media import (
    allowed_preview_url,
    matches_recording,
    probe_preview,
    normalized_words,
)


def normalize_song(row):
    if not isinstance(row, dict) or row.get("type") != "songs":
        return None
    attributes = row.get("attributes")
    if not isinstance(attributes, dict) or not row.get("id"):
        return None
    title, display_artist = attributes.get("name"), attributes.get("artistName")
    if (
        not isinstance(title, str)
        or not title
        or not isinstance(display_artist, str)
        or not display_artist
    ):
        return None
    relationships = row.get("relationships")
    relationship = (
        relationships.get("artists") if isinstance(relationships, dict) else None
    )
    relationship = relationship if isinstance(relationship, dict) else {}
    credits = []
    for artist in (
        relationship.get("data", [])
        if isinstance(relationship.get("data"), list)
        else []
    ):
        details = artist.get("attributes") if isinstance(artist, dict) else None
        if (
            isinstance(details, dict)
            and isinstance(details.get("name"), str)
            and artist.get("id")
        ):
            credits.append(
                {
                    "artist_key": "apple:artist:" + str(artist["id"]),
                    "name": details["name"][:300],
                }
            )
    if not credits:
        credits = [
            {
                "artist_key": "apple:artist-name:" + display_artist.casefold(),
                "name": display_artist[:300],
            }
        ]
    artwork = attributes.get("artwork") or {}
    artwork_url = artwork.get("url") if isinstance(artwork, dict) else None
    if isinstance(artwork_url, str) and artwork_url.startswith("https://"):
        artwork_url = artwork_url.replace("{w}", "300").replace("{h}", "300")
    else:
        artwork_url = None
    previews = attributes.get("previews")
    preview = (
        next(
            (
                item.get("url")
                for item in previews
                if isinstance(item, dict) and allowed_preview_url(item.get("url"))
            ),
            None,
        )
        if isinstance(previews, list)
        else None
    )
    isrc = attributes.get("isrc")
    return {
        "song_key": "apple:track:" + str(row["id"]),
        "title": title[:300],
        "artist": display_artist[:300],
        "artists": credits,
        "isrc": isrc.strip().upper() if isinstance(isrc, str) else None,
        "artwork_url": artwork_url,
        "preview_url": preview,
    }


class AppleCatalog:
    def __init__(
        self,
        team_id,
        key_id,
        private_key_path,
        storefront="es",
        transport=None,
        clock=time.time,
        probe=probe_preview,
    ):
        self.team_id, self.key_id = team_id, key_id
        self.private_key_path = Path(private_key_path) if private_key_path else None
        self.storefront, self.clock, self.probe = storefront, clock, probe
        self.transport = transport or JsonHttpTransport()
        self._lock = threading.Lock()
        self._token, self._expires = None, 0
        self._retry_at = 0

    @property
    def configured(self):
        return bool(
            self.team_id
            and self.key_id
            and self.private_key_path
            and self.private_key_path.is_file()
            and re.fullmatch(r"[a-z]{2}", self.storefront or "")
        )

    def _developer_token(self):
        if not self.configured:
            raise MusicProviderError(
                "apple_not_configured",
                "Apple Music catalog credentials are not configured.",
                503,
            )
        with self._lock:
            now = int(self.clock())
            if self._token and self._expires > now + 60:
                return self._token
            try:
                import jwt
            except ImportError:
                raise MusicProviderError(
                    "apple_invalid_configuration",
                    "Apple Music catalog signing is unavailable.",
                    503,
                ) from None
            try:
                token = jwt.encode(
                    {"iss": self.team_id, "iat": now, "exp": now + 3600},
                    self.private_key_path.read_bytes(),
                    algorithm="ES256",
                    headers={"kid": self.key_id},
                )
            except (OSError, ValueError, TypeError, jwt.PyJWTError):
                raise MusicProviderError(
                    "apple_invalid_configuration",
                    "Apple Music catalog credentials could not be loaded.",
                    503,
                ) from None
            self._token, self._expires = token, now + 3600
            return token

    def _get(self, resource, params, *, missing_ok=False):
        with self._lock:
            remaining = self._retry_at - self.clock()
        if remaining > 0:
            raise MusicProviderError(
                "apple_rate_limited",
                "Apple Music is busy. Retry shortly.",
                429,
                {"retry_after_seconds": max(1, int(remaining) + 1)},
            )
        url = (
            "https://api.music.apple.com/v1/catalog/"
            + self.storefront
            + "/"
            + resource
            + "?"
            + urlencode(params, quote_via=quote)
        )
        try:
            return self.transport.request(
                "GET",
                url,
                headers={"Authorization": "Bearer " + self._developer_token()},
            )
        except ProviderHttpError as error:
            if missing_ok and error.status == 404:
                return {"data": []}
            if error.status in (401, 403):
                raise MusicProviderError(
                    "apple_authorization_failed",
                    "Apple Music rejected the server's catalog credentials.",
                    503,
                ) from None
            if error.status == 429:
                with self._lock:
                    self._retry_at = max(
                        self._retry_at, self.clock() + (error.retry_after or 30)
                    )
                raise MusicProviderError(
                    "apple_rate_limited",
                    "Apple Music is busy. Retry shortly.",
                    429,
                    {"retry_after_seconds": error.retry_after or 30},
                ) from None
            raise MusicProviderError(
                "apple_unavailable",
                "Apple Music catalog is unavailable. Retry shortly.",
                503,
            ) from None

    @staticmethod
    def _songs(rows):
        if not isinstance(rows, list):
            raise MusicProviderError(
                "apple_invalid_response",
                "Apple Music returned an incomplete catalog response.",
                503,
            )
        return [song for row in rows[:50] if (song := normalize_song(row)) is not None]

    def search(self, query):
        payload = self._get(
            "search",
            {"term": query, "types": "songs", "limit": 20, "include[songs]": "artists"},
        )
        results = payload.get("results")
        if not isinstance(results, dict):
            raise MusicProviderError(
                "apple_invalid_response",
                "Apple Music returned an incomplete search response.",
                503,
            )
        songs = results.get("songs") or {}
        if not isinstance(songs, dict):
            raise MusicProviderError(
                "apple_invalid_response",
                "Apple Music returned an incomplete search response.",
                503,
            )
        return self._songs(songs.get("data", []))

    def decoys(self):
        payload = self._get(
            "charts", {"types": "songs", "limit": 30, "include[songs]": "artists"}
        )
        results = payload.get("results")
        if not isinstance(results, dict):
            raise MusicProviderError(
                "apple_invalid_response",
                "Apple Music returned an incomplete charts response.",
                503,
            )
        charts = results.get("songs", [])
        if not isinstance(charts, list):
            raise MusicProviderError(
                "apple_invalid_response",
                "Apple Music returned an incomplete charts response.",
                503,
            )
        songs = []
        seen = set()
        for chart in charts[:3]:
            if not isinstance(chart, dict):
                continue
            for song in self._songs(chart.get("data", [])):
                key = song.get("isrc") or song["song_key"]
                if key not in seen:
                    seen.add(key)
                    songs.append(song)
        return songs[:30]

    def _matched(self, song, candidates, on_verified=None):
        probes = 0
        for candidate in candidates:
            if (
                song.get("isrc")
                and candidate.get("isrc")
                and song["isrc"] != candidate["isrc"]
            ):
                continue
            if not matches_recording(song, candidate):
                continue
            if on_verified:
                on_verified(candidate)
            if not candidate.get("preview_url"):
                continue
            probes += 1
            if self.probe(candidate["preview_url"]):
                result = deepcopy(song)
                result.update(
                    preview_url=candidate["preview_url"],
                    artwork_url=song.get("artwork_url") or candidate.get("artwork_url"),
                )
                for credit in result.get("artists", []):
                    aliases = [
                        artist["artist_key"]
                        for artist in candidate["artists"]
                        if normalized_words(artist["name"])
                        == normalized_words(credit["name"])
                        and not artist["artist_key"].startswith("apple:artist-name:")
                        and artist["artist_key"] != credit["artist_key"]
                    ]
                    if aliases:
                        credit["aliases"] = list(
                            dict.fromkeys(credit.get("aliases", []) + aliases)
                        )
                return result
            if probes >= 3:
                break
        return None

    def resolve_verified(self, song, on_verified=None):
        """Report a verified catalog identity independently of audio delivery."""
        if song["song_key"].startswith("apple:track:") and allowed_preview_url(
            song.get("preview_url")
        ):
            if on_verified:
                on_verified(song)
            return deepcopy(song) if self.probe(song["preview_url"]) else None
        # Even an ISRC hit must match title/version/lead artist: provider records
        # can be mislabeled and the same ISRC may have multiple catalog entries.
        if song.get("isrc"):
            payload = self._get(
                "songs", {"filter[isrc]": song["isrc"], "include": "artists"}
            )
            matched = self._matched(
                song, self._songs(payload.get("data", [])), on_verified
            )
            if matched:
                return matched
        return self._matched(
            song, self.search(song["title"] + " " + song["artist"]), on_verified
        )

    def refresh(self, song, known, on_verified=None, on_invalid=None):
        """Renew media by an already verified ID, without searching again."""
        key = known["song_key"]
        if not key.startswith("apple:track:"):
            return None
        payload = self._get(
            "songs",
            {"ids": key.removeprefix("apple:track:"), "include": "artists"},
            missing_ok=True,
        )
        candidates = [
            row
            for row in self._songs(payload.get("data", []))
            if row["song_key"] == key
        ]
        if candidates and (
            not matches_recording(song, candidates[0])
            or (
                song.get("isrc")
                and candidates[0].get("isrc")
                and song["isrc"] != candidates[0]["isrc"]
            )
        ):
            if on_invalid:
                on_invalid(key)
            return None
        return self._matched(song, candidates, on_verified)
