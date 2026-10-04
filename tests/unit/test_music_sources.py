"""The listening contract distinguishes external identity from simulated facts."""

import json
import random
from copy import deepcopy

import pytest

from backend.core.errors import DomainError
from backend.music.sources import (
    DemoListeningAdapter,
    LocalPreviewResolver,
    SpotifyListeningAdapter,
)
from backend.music.spotify import SpotifyClient
from tests.support.demo import make_demo_pack


def catalog(pack):
    return [
        {
            "song_key": "demo:" + entry["id"],
            **{
                key: entry.get(key)
                for key in (
                    "isrc",
                    "title",
                    "artist",
                    "artists",
                    "preview_url",
                    "artwork_url",
                )
            },
        }
        for entry in json.loads((pack / "demo_catalog.json").read_text())
        if entry["pool_kind"] == "personal"
    ]


def test_spotify_adapter_normalizes_real_client_facts_and_keeps_account_identity():
    calls = []

    class Transport:
        def request(self, method, url, headers=None, data=None):
            calls.append(url)
            assert headers == {"Authorization": "Bearer test-credential"}
            if url.endswith("/me"):
                return {"id": "external-account"}
            if "recently-played" in url:
                return {"items": []}
            return {
                "items": [
                    {
                        "id": "recording",
                        "name": "Song",
                        "artists": [{"id": "artist", "name": "Artist"}],
                        "external_ids": {"isrc": " usabc1234567 "},
                    }
                ]
            }

    source = SpotifyListeningAdapter(
        SpotifyClient("client", "http://127.0.0.1:8000/callback", transport=Transport())
    )
    facts = source.read("test-credential")
    assert facts.provider == source.provider == "spotify"
    assert source.label == "Spotify" and facts.evidence == "personal"
    assert facts.account_id == "external-account"
    assert len(calls) == 5 and calls[0].endswith("/me")
    assert len(facts.songs) == 1
    song = facts.songs[0]
    assert song["isrc"] == "USABC1234567" and song["familiarity"] == "easy"
    assert len(song["source_evidence"]) == 3 and "preview_url" not in song


def test_demo_adapter_simulates_36_independent_facts_without_external_identity(
    tmp_path,
):
    songs = catalog(make_demo_pack(tmp_path / "pack"))
    before = deepcopy(songs)
    source = DemoListeningAdapter(songs, rng=random.Random(17))
    first, second = source.read(), source.read()
    assert first.provider == source.provider == "demo" and source.label == "Demo"
    assert first.evidence == "simulated" and first.account_id is None
    assert len(first.songs) == len({s["song_key"] for s in first.songs}) == 36
    assert {s["familiarity"] for s in first.songs} == {"easy", "medium", "hard"}
    assert {s["song_key"] for s in first.songs} != {s["song_key"] for s in second.songs}
    first.songs[0]["artists"][0]["name"] = "Edited"
    assert songs == before and source.songs == before


def test_local_resolver_uses_pack_facts_and_never_an_injected_media_url(tmp_path):
    pack = make_demo_pack(tmp_path / "pack")
    songs = catalog(pack)
    resolver = LocalPreviewResolver(songs, pack)
    facts = songs[0] | {"familiarity": "hard"}
    resolved = resolver.resolve(facts | {"preview_url": "https://example.com/clip"})
    assert resolved["preview_url"] == facts["preview_url"]
    assert (
        resolved["familiarity"] == "hard" and resolved["song_key"] == facts["song_key"]
    )
    resolved["artists"][0]["name"] = "Edited"
    assert resolver.resolve(facts)["artists"] == facts["artists"]
    with pytest.raises(DomainError) as error:
        resolver.resolve(facts | {"isrc": "DIFFERENT"})
    assert error.value.code == "invalid_demo_recording"


@pytest.mark.parametrize("unsafe", ["../outside.wav", "%2e%2e/outside.wav"])
def test_local_resolver_rejects_path_escape_even_for_supplied_catalog(tmp_path, unsafe):
    pack = make_demo_pack(tmp_path / "pack")
    song = catalog(pack)[0] | {"preview_url": "/static/demo/local/" + unsafe}
    (pack / "outside.wav").write_bytes(b"outside")
    with pytest.raises(DomainError) as error:
        LocalPreviewResolver([song], pack).resolve(song)
    assert error.value.code == "demo_pack_unavailable"


def test_local_resolver_reports_missing_installed_asset(tmp_path):
    pack = make_demo_pack(tmp_path / "pack")
    song = catalog(pack)[0]
    resolver = LocalPreviewResolver([song], pack)
    (pack / "assets" / song["preview_url"].removeprefix("/static/demo/local/")).unlink()
    with pytest.raises(DomainError) as error:
        resolver.resolve(song)
    assert error.value.code == "demo_pack_unavailable"
