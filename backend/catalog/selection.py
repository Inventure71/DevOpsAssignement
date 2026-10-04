"""Resolve signed bulk metadata before selection; answer submission stays offline."""

from backend.catalog.identity import normalized_words, recording_title
from backend.core.errors import DomainError
from backend.music.media import matches_recording


class CatalogSelections:
    def __init__(self, tokens, lookup, result, *, links=None, scope, clock):
        self.tokens, self.lookup, self.result = tokens, lookup, result
        self.links, self.scope, self.clock = links, scope, clock

    def resolve(self, room_id, token, now):
        song, expires = self.tokens.decode(token, room_id)
        if expires <= now:
            raise DomainError(
                "song_selection_expired", "Search again to select this song."
            )
        if not song.get("_catalog_reference"):
            return self.result(room_id, song, now)
        verified = self.links.find(self.scope, "guess", song) if self.links else []
        if not verified:
            query = song["title"] + " " + song["artist"]
            candidates, _ = self.lookup(normalized_words(query), query.casefold())
            matches = [
                candidate
                for candidate in candidates
                if matches_recording(song, candidate)
            ]
            # Resolve the selected recording here; Game alone relaxes release
            # labels for guess scoring. Regional editions may differ in ISRC;
            # audio-preview recording matching remains strict.
            identities = {
                (
                    recording_title(candidate["title"]),
                    tuple(
                        sorted(credit["artist_key"] for credit in candidate["artists"])
                    ),
                )
                for candidate in matches
            }
            if not matches:
                raise DomainError(
                    "song_selection_unavailable",
                    "This recording could not be matched. Try another result.",
                    503,
                )
            if len(identities) != 1:
                raise DomainError(
                    "song_selection_ambiguous",
                    "Several recordings match this result. Choose the correct recording.",
                    409,
                    {
                        "alternatives": [
                            self.result(room_id, candidate, now)
                            for candidate in matches[:20]
                        ]
                    },
                )
            if self.links:
                for candidate in matches:
                    self.links.save(self.scope, "guess", song, candidate, self.clock())
            verified = matches
        return self.result(room_id, verified[0], now)
