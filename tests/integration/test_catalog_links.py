"""Durable verification is independent of games, elapsed time and audio URLs."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.catalog.links import fingerprint
from backend.catalog.search import SongSearch
from backend.catalog.store import CatalogStore
from tests.support.demo import demo_config
from tests.integration.test_catalog_store import bulk_song, store_at
from tests.integration.test_music_admission import admit, create_normal_app
from tests.unit.test_song_catalog import SONG


def test_every_positive_edge_has_scoped_reverse_and_survives_years_restart(tmp_path):
    store = store_at(tmp_path)
    source = bulk_song()
    targets = [SONG, SONG | {"song_key": "apple:track:43", "isrc": "USAB10000002"}]
    for target in targets:
        store.links.save("apple:es", "guess", source, target, 100)
    restarted = CatalogStore(store.path)
    restarted.initialize()
    assert restarted.links.find("apple:es", "guess", source) == targets
    for target in targets:
        assert restarted.links.find("apple:es", "guess", target) == [source]
    assert restarted.links.find("apple:us", "guess", source) == []
    assert restarted.links.find("apple:es", "recording", source) == []
    store.links.save("apple:es", "recording", source, targets[0], 10**10)
    assert store.links.find("apple:es", "recording", source) == [targets[0]]
    assert store.links.find("apple:es", "guess", source) == targets


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Billie Jean (Live)"},
        {"isrc": "USAB10000001"},
        {"artist": "Michael Jackson & Guest"},
        {"artists": [{"artist_key": "other:artist", "name": "Michael Jackson"}]},
        {"artists": [{"artist_key": "same:artist", "name": "Different Artist"}]},
    ],
)
def test_changed_source_recording_identity_requires_new_verification(tmp_path, change):
    store, source = store_at(tmp_path), bulk_song()
    store.links.save("apple:es", "guess", source, SONG, 100)
    assert store.links.find("apple:es", "guess", source | change) == []
    assert store.links.find("apple:es", "guess", source) == [SONG]


def test_complete_credit_order_and_cosmetic_changes_do_not_invalidate(tmp_path):
    store = store_at(tmp_path)
    source = bulk_song() | {"isrc": "usab10000001"}
    source["artists"].append({"artist_key": "guest:1", "name": "Guest"})
    store.links.save("apple:es", "recording", source, SONG, 100)
    cosmetic = source | {
        "title": "BILLIE JEAN",
        "isrc": "USAB10000001",
        "artists": list(reversed(source["artists"])),
    }
    assert store.links.find("apple:es", "recording", cosmetic) == [SONG]
    assert (
        store.links.find(
            "apple:es", "recording", source | {"artists": source["artists"][:1]}
        )
        == []
    )


def test_verification_does_not_store_private_fields_or_index_listening_history(
    tmp_path,
):
    store = store_at(tmp_path)
    source = SONG | {
        "song_key": "spotify:track:private-title-source",
        "title": "Not globally searchable",
        "preview_url": "private-media",
        "source_evidence": ["private-history"],
        "familiarity": "private-rank",
        "listeners": ["private-player"],
    }
    target = SONG | {
        "preview_url": "private-target-audio",
        "player_id": "private-player",
    }
    store.links.save("apple:es", "recording", source, target, 100)
    assert store.search("Not globally searchable") == []
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT source_json,target_json FROM verified_links"
        ).fetchall()
        for row in rows:
            assert all(
                "private-" not in text.replace("private-title-source", "")
                for text in row
            )
            for metadata in map(json.loads, row):
                assert set(metadata) <= {
                    "song_key",
                    "title",
                    "artist",
                    "artists",
                    "isrc",
                    "artwork_url",
                }
        assert conn.execute("SELECT COUNT(*) FROM catalog_songs").fetchone()[0] == 0


def test_known_bad_edge_rejection_removes_only_that_edge_and_its_reverse(tmp_path):
    store, source = store_at(tmp_path), bulk_song()
    other = SONG | {"song_key": "apple:track:other"}
    for purpose in ("guess", "recording"):
        for target in (SONG, other):
            store.links.save("apple:es", purpose, source, target, 100)
    store.links.save("apple:us", "guess", source, SONG, 100)
    store.links.reject("apple:es", "guess", source, SONG["song_key"])
    assert store.links.find("apple:es", "guess", source) == [other]
    assert store.links.find("apple:es", "guess", SONG) == []
    assert store.links.find("apple:es", "guess", other) == [source]
    assert store.links.find("apple:es", "recording", source) == [SONG, other]
    assert store.links.find("apple:us", "guess", source) == [SONG]


def test_new_verification_refreshes_same_target_id_and_only_its_exact_reverse(tmp_path):
    store, source, unrelated = store_at(tmp_path), bulk_song(), bulk_song()
    revised_source = source | {"title": "Billie Jean (Live)"}
    alternate = SONG | {"song_key": "apple:track:alternate"}
    for scope, purpose in (
        ("apple:es", "guess"),
        ("apple:us", "guess"),
        ("apple:es", "recording"),
    ):
        store.links.save(scope, purpose, source, SONG, 100)
    store.links.save("apple:es", "guess", source, alternate, 100)
    store.links.save("apple:es", "guess", unrelated, SONG, 100)
    store.links.save("apple:es", "guess", revised_source, SONG, 100)
    fresh = SONG | {
        "title": "Billie Jean (Live)",
        "artists": [{"artist_key": "apple:artist:revised", "name": "Michael Jackson"}],
    }
    store.links.save("apple:es", "guess", source, fresh, 200)
    assert store.links.find("apple:es", "guess", source) == [fresh, alternate]
    assert store.links.find("apple:es", "guess", fresh) == [source]
    assert store.links.find("apple:es", "guess", SONG) == [unrelated, revised_source]
    assert store.links.find("apple:es", "guess", unrelated) == [SONG]
    assert store.links.find("apple:es", "guess", revised_source) == [SONG]
    assert store.links.find("apple:us", "guess", source) == [SONG]
    assert store.links.find("apple:es", "recording", source) == [SONG]
    assert store.links.find("apple:es", "guess", alternate) == [source]
    # Saving the same fresh verification again remains idempotent.
    store.links.save("apple:es", "guess", source, fresh, 300)
    assert store.links.find("apple:es", "guess", source) == [fresh, alternate]


@pytest.mark.parametrize("scope", ["apple:es", "itunes:us"])
def test_http_every_equivalent_match_reused_across_rooms_years_and_provider_outage(
    tmp_path, scope
):
    calls, now, source = [], [100.0], bulk_song()
    targets = [SONG, SONG | {"song_key": "apple:track:43", "isrc": "USAA10000002"}]

    def provider(query):
        calls.append(query)
        if len(calls) > 1:
            raise AssertionError(
                "A verified link must not trigger another provider search"
            )
        return targets

    for attempt in range(2):
        search = SongSearch(provider, provider_scope=scope, clock=lambda: now[0])
        app = create_normal_app(demo_config(tmp_path), background=False, song_search=search)
        with TestClient(app) as client:
            app.state.catalog_store.save_songs(
                [source], "musicbrainz:canonical:CC0", now[0]
            )
            for index in range(2):
                room = admit(client, "Host", f"account-{attempt}-{index}")
                prefix = "/api/rooms/" + room["room_id"]
                if attempt == index == 0:
                    result = client.get(
                        prefix + "/song-search", params={"q": "billie", "local": True}
                    ).json()["songs"][0]
                    assert result["resolve_required"] is True and calls == []
                    token = result["token"]
                else:
                    token = search.tokens.issue(
                        room["room_id"], source | {"_catalog_reference": True}, 10**15
                    )
                response = client.post(
                    prefix + "/song-selection", json={"token": token}
                )
                assert response.status_code == 200, response.text
                assert set(response.json()) == {"title", "artist", "artwork_url", "token"}
                decoded = search.tokens.decode(
                    response.json()["token"], room["room_id"]
                )[0]
                assert decoded == targets[0]
                ordinary = client.get(
                    prefix + "/song-search", params={"q": "Billie Jean"}
                ).json()["songs"][0]
                assert ordinary["title"] == SONG["title"]
                assert "resolve_required" not in ordinary
            assert app.state.catalog_store.links.find(scope, "guess", source) == targets
            assert all(
                app.state.catalog_store.links.find(scope, "guess", target) == [source]
                for target in targets
            )
            local = app.state.catalog_store.search("Billie Jean", scope=scope)
            assert not any(song["song_key"] == source["song_key"] for song in local)
            assert targets[0]["song_key"] in {song["song_key"] for song in local}
        now[0] += 10 * 365 * 86400
    assert len(calls) == 1


def test_bulk_link_batch_uses_single_connection_and_preserves_provider_order(
    tmp_path, monkeypatch
):
    store = store_at(tmp_path)
    sources = [bulk_song() for _ in range(20)]
    for source in sources:
        store.links.save("apple:es", "guess", source, SONG, 100)
    store.save_songs(sources, "musicbrainz:canonical:CC0", 100)
    original, calls = store.connect, []

    def counted():
        calls.append(1)
        return original()

    monkeypatch.setattr(store, "connect", counted)
    assert store.search("Billie Jean", scope="apple:es") == [SONG]
    assert calls == [1]
    assert fingerprint(sources[0]) == fingerprint(
        sources[0] | {"preview_url": "ignored"}
    )
