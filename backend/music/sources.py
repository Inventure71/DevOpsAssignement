"""Listening evidence adapters, independent of previews and room persistence."""

import secrets
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import unquote

from backend.core.errors import DomainError


@dataclass(frozen=True)
class ListeningData:
    provider: str
    evidence: Literal["personal", "simulated"]
    songs: list[dict]
    account_id: str | None = None


class MusicSource(Protocol):
    provider: str
    label: str

    def read(self, credential: str | None = None) -> ListeningData: ...


class SpotifyListeningAdapter:
    provider = "spotify"
    label = "Spotify"

    def __init__(self, client):
        self.client = client

    def read(self, credential: str | None = None) -> ListeningData:
        if not isinstance(credential, str) or not credential:
            raise DomainError(
                "spotify_authorization_expired", "Connect Spotify again.", 401
            )
        account_id = self.client.profile(credential)
        return ListeningData(
            self.provider, "personal", self.client.listening(credential), account_id
        )


class DemoListeningAdapter:
    provider = "demo"
    label = "Demo"

    def __init__(self, songs, *, assignment_size=36, rng=None):
        self.songs = deepcopy(songs)
        self.assignment_size = assignment_size
        self.rng = rng or secrets.SystemRandom()

    def read(self, credential: str | None = None) -> ListeningData:
        assigned = self.rng.sample(
            self.songs, min(self.assignment_size, len(self.songs))
        )
        return ListeningData(
            self.provider,
            "simulated",
            [
                deepcopy(song)
                | {"familiarity": self.rng.choice(("easy", "medium", "hard"))}
                for song in assigned
            ],
        )


class LocalPreviewResolver:
    """Resolve only the exact recording and assets of an installed Demo pack."""

    def __init__(self, songs, pack):
        self.songs = {song["song_key"]: deepcopy(song) for song in songs}
        self.assets = (Path(pack) / "assets").resolve()

    def resolve(self, song):
        stored = self.songs.get(song.get("song_key"))
        if stored is None or any(
            song.get(field) != stored.get(field)
            for field in ("isrc", "title", "artist", "artists")
        ):
            raise DomainError(
                "invalid_demo_recording", "This recording is not in the Demo pack.", 503
            )
        for field in ("preview_url", "artwork_url"):
            value = stored.get(field)
            if value is None and field == "artwork_url":
                continue
            prefix = "/static/demo/local/"
            if not isinstance(value, str) or not value.startswith(prefix):
                raise self._missing_asset()
            try:
                target = (self.assets / unquote(value[len(prefix) :])).resolve()
                available = (
                    target.is_relative_to(self.assets)
                    and target.is_file()
                    and target.stat().st_size > 0
                )
            except OSError:
                available = False
            if not available:
                raise self._missing_asset()
        return deepcopy(song) | {
            "preview_url": stored["preview_url"],
            "artwork_url": stored.get("artwork_url"),
        }

    @staticmethod
    def _missing_asset():
        return DomainError(
            "demo_pack_unavailable", "Demo music assets are unavailable.", 503
        )
