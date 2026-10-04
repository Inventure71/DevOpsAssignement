"""Real SQLite public metadata persistence, safe search and selection boundaries."""

import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.catalog.importer import import_canonical
from backend.catalog.search import SongSearch
from backend.catalog.store import CatalogStore
from tests.support.demo import demo_config
from backend.core.errors import DomainError
from tests.unit.test_song_catalog import SONG
from tests.integration.test_api import session as session, start
from tests.integration.test_music_admission import (
    admit,
    create_normal_app,
    normal_session as normal_session,
)


def store_at(tmp_path):
    store = CatalogStore(tmp_path / "catalog.sqlite3")
    store.initialize()
    return store


def bulk_song(title="Billie Jean", artist="Michael Jackson"):
    return {
        "song_key": "musicbrainz:recording:" + str(uuid4()),
        "title": title,
        "artist": artist,
        "artists": [
            {"artist_key": "musicbrainz:artist:" + str(uuid4()), "name": artist}
        ],
        "artwork_url": None,
    }


def test_index_unicode_ranking_injection_and_metadata_allowlist(tmp_path):
    store = store_at(tmp_path)
    song = SONG | {
        "title": "Déjà Vu",
        "preview_url": "private-media",
        "listeners": ["private-player"],
        "source_evidence": ["private-history"],
    }
    store.save_songs(
        [song, SONG | {"song_key": "apple:track:43", "title": "Déjà Vu Live"}],
        "apple:es",
        100,
    )
    assert [row["title"] for row in store.search("deja vu")] == [
        "Déjà Vu",
        "Déjà Vu Live",
    ]
    assert len(store.search("Michael dej")) == 2
    assert store.search('" OR * -- DROP TABLE catalog_songs') == []
    assert store.search("🎵") == []
    assert not {"preview_url", "listeners", "source_evidence"} & set(
        store.search("deja")[0]
    )
    with store.connect() as conn:
        stored = " ".join(
            str(value)
            for value in conn.execute("SELECT * FROM catalog_songs").fetchone()
        )
        assert "private-" not in stored
    store.save_songs([song | {"title": "Replacement"}], "apple:es", 101)
    assert len(store.search("deja vu")) == 1
    assert store.search("replacement")[0]["song_key"] == SONG["song_key"]


def test_query_positive_and_empty_persist_and_expire_by_scope(tmp_path):
    now, calls = [100.0], []
    store = store_at(tmp_path)

    def provider(query):
        calls.append(query)
        return [] if query == "missing" else [SONG]

    first = SongSearch(
        provider, store=store, clock=lambda: now[0], provider_scope="apple:es"
    )
    assert first.provider_results("billie jean") == ([SONG], False)
    second = SongSearch(
        provider, store=store, clock=lambda: now[0], provider_scope="apple:es"
    )
    assert second.provider_results("billie jean") == ([SONG], True)
    assert second.provider_results("missing") == ([], False)
    assert SongSearch(
        provider, store=store, clock=lambda: now[0], provider_scope="apple:es"
    ).provider_results("missing") == ([], True)
    assert calls == ["billie jean", "missing"]
    now[0] += 61
    assert SongSearch(
        provider, store=store, clock=lambda: now[0], provider_scope="apple:es"
    ).provider_results("missing") == ([], False)
    assert (
        SongSearch(
            provider, store=store, clock=lambda: now[0], provider_scope="apple:us"
        ).provider_results("billie jean")[1]
        is False
    )
    now[0] += 86401
    assert (
        SongSearch(
            provider, store=store, clock=lambda: now[0], provider_scope="apple:es"
        ).provider_results("billie jean")[1]
        is False
    )
    assert len(calls) == 5


def test_http_warm_search_survives_restart_and_tokens_remain_room_specific(tmp_path):
    calls = []

    def provider(query):
        calls.append(query)
        return [SONG]

    for attempt in range(2):
        app = create_normal_app(
            demo_config(tmp_path), background=False, song_search=SongSearch(provider)
        )
        with TestClient(app) as client:
            room = admit(client, "Host", "host-account")
            prefix = "/api/rooms/" + room["room_id"]
            result = client.get(
                prefix + "/song-search", params={"q": "Billie Jean"}
            ).json()
            assert result["cached"] is bool(attempt)
            assert set(result["songs"][0]) == {
                "title",
                "artist",
                "artwork_url",
                "token",
            }
            token = result["songs"][0]["token"]
            assert (
                app.state.song_search.tokens.decode(token, room["room_id"])[0] == SONG
            )
            another = admit(client, "Other", "other-account")
            with pytest.raises(DomainError):
                app.state.song_search.tokens.decode(token, another["room_id"])
    assert calls == ["billie jean"]


def test_bulk_local_search_zero_calls_resolution_is_cached_and_default_contract_works(
    tmp_path,
):
    calls = []

    def provider(query):
        calls.append(query)
        return [SONG]

    app = create_normal_app(
        demo_config(tmp_path), background=False, song_search=SongSearch(provider)
    )
    with TestClient(app) as client:
        reference = bulk_song()
        app.state.catalog_store.save_songs(
            [reference], "musicbrainz:canonical:CC0", 100
        )
        room = admit(client, "Host", "host-account")
        prefix = "/api/rooms/" + room["room_id"]
        result = client.get(
            prefix + "/song-search", params={"q": "billie", "local": True}
        ).json()["songs"][0]
        assert result["resolve_required"] is True and calls == []
        resolved = client.post(
            prefix + "/song-selection", json={"token": result["token"]}
        )
        assert resolved.status_code == 200, resolved.text
        assert set(resolved.json()) == {"title", "artist", "artwork_url", "token"}
        metadata = app.state.song_search.tokens.decode(
            resolved.json()["token"], room["room_id"]
        )[0]
        assert metadata == SONG and "_catalog_reference" not in metadata
        assert len(calls) == 1
        # A new resolver object uses the durable public recording mapping.
        assert (
            client.post(
                prefix + "/song-selection", json={"token": result["token"]}
            ).status_code
            == 200
        )
        assert len(calls) == 1
        ordinary = client.get(
            prefix + "/song-search", params={"q": "Billie Jean"}
        ).json()
        assert (
            ordinary["songs"][0]["title"] == SONG["title"]
            and "resolve_required" not in ordinary["songs"][0]
        )
        assert len(calls) == 1
    app = create_normal_app(
        demo_config(tmp_path), background=False, song_search=SongSearch(provider)
    )
    with TestClient(app) as client:
        room = admit(client, "New", "new-account")
        prefix = "/api/rooms/" + room["room_id"]
        token = app.state.song_search.tokens.issue(
            room["room_id"], reference | {"_catalog_reference": True}, 10**15
        )
        assert (
            client.post(prefix + "/song-selection", json={"token": token}).status_code
            == 200
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "candidate, expected",
    [
        (SONG | {"title": "Billie Jean (Live)"}, "song_selection_unavailable"),
        (
            SONG
            | {
                "artist": "Cover Band",
                "artists": [{"artist_key": "apple:artist:other", "name": "Cover Band"}],
            },
            "song_selection_unavailable",
        ),
        (
            [
                SONG,
                SONG
                | {
                    "song_key": "apple:track:43",
                    "artists": [
                        {"artist_key": "apple:artist:other", "name": "Michael Jackson"}
                    ],
                },
            ],
            "song_selection_ambiguous",
        ),
    ],
)
def test_bulk_selection_rejects_wrong_versions_covers_and_homonymous_ambiguity(
    tmp_path, candidate, expected
):
    candidates = candidate if isinstance(candidate, list) else [candidate]
    app = create_normal_app(
        demo_config(tmp_path),
        background=False,
        song_search=SongSearch(lambda q: candidates),
    )
    with TestClient(app) as client:
        room = admit(client, "Host", "host-account")
        token = app.state.song_search.tokens.issue(
            room["room_id"], bulk_song() | {"_catalog_reference": True}, 10**15
        )
        response = client.post(
            "/api/rooms/" + room["room_id"] + "/song-selection", json={"token": token}
        )
        assert response.json()["error"]["code"] == expected
        if expected == "song_selection_ambiguous":
            alternatives = response.json()["error"]["details"]["alternatives"]
            assert len(alternatives) == 2
            assert all(
                set(entry) == {"title", "artist", "artwork_url", "token"}
                for entry in alternatives
            )
            assert all(
                "_catalog_reference"
                not in app.state.song_search.tokens.decode(
                    entry["token"], room["room_id"]
                )[0]
                for entry in alternatives
            )


def test_selection_authentication_expiry_wrong_room_and_unresolved_answer_rejected(
    tmp_path,
):
    app = create_normal_app(
        demo_config(tmp_path),
        background=False,
        song_search=SongSearch(lambda q: [SONG]),
    )
    with TestClient(app) as client:
        room = admit(client, "Host", "host-account")
        prefix = "/api/rooms/" + room["room_id"]
        token = app.state.song_search.tokens.issue(
            room["room_id"], bulk_song() | {"_catalog_reference": True}, 0
        )
        assert (
            client.post(prefix + "/song-selection", json={"token": token}).json()[
                "error"
            ]["code"]
            == "song_selection_expired"
        )
        assert (
            TestClient(app)
            .post(prefix + "/song-selection", json={"token": token})
            .status_code
            == 401
        )
        token = app.state.song_search.tokens.issue("another-room", SONG, 10**15)
        assert (
            client.post(prefix + "/song-selection", json={"token": token}).json()[
                "error"
            ]["code"]
            == "invalid_song_selection"
        )


def test_streaming_import_validates_real_canonical_columns_and_skips_composite_credit(
    tmp_path,
):
    store = store_at(tmp_path)
    recording, artist = str(uuid4()), str(uuid4())
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "recording_mbid",
            "recording_name",
            "artist_credit_name",
            "artist_mbids",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "recording_mbid": recording,
            "recording_name": "Déjà Vu",
            "artist_credit_name": "Solo",
            "artist_mbids": artist,
        }
    )
    writer.writerow(
        {
            "recording_mbid": str(uuid4()),
            "recording_name": "Collaboration",
            "artist_credit_name": "Two & Three",
            "artist_mbids": "{" + artist + "," + str(uuid4()) + "}",
        }
    )
    writer.writerow(
        {
            "recording_mbid": "not-a-uuid",
            "recording_name": "Bad",
            "artist_credit_name": "Bad",
            "artist_mbids": artist,
        }
    )
    output.seek(0)
    assert import_canonical(output, store, batch_size=1) == {
        "rows_read": 3,
        "imported": 1,
        "skipped": 2,
    }
    assert (
        store.search("deja vu")[0]["song_key"] == "musicbrainz:recording:" + recording
    )
    with pytest.raises(ValueError):
        import_canonical(io.StringIO("title,artist\nBad,CSV\n"), store)


def test_unresolved_reference_cannot_enter_game_answers(session):
    c, clock, host, guests, room, prefix, lease = session
    gid, attempt, _ = start(session)
    with c.db.read() as conn:
        clock.value = c.game.repo.current(conn, gid)["starts_at_ms"]
    c.tick()
    token = host.app.state.song_search.tokens.issue(
        room["room_id"], bulk_song() | {"_catalog_reference": True}, clock.value
    )
    response = host.post(
        prefix + f"/games/{gid}/rounds/{attempt['id']}/answers",
        json={"song_guess_token": token, "who_player_ids": []},
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "song_selection_unresolved"
    )
    with c.db.read() as conn:
        assert c.game.repo.answers(conn, attempt["id"]) == []


def test_public_canonical_priority_ranks_original_ahead_of_cover_and_provider_identity_first(
    tmp_path,
):
    store = store_at(tmp_path)
    cover = bulk_song("Bohemian Rhapsody", "Phish") | {"_catalog_priority": 4748184}
    original = bulk_song("Bohemian Rhapsody", "Queen") | {"_catalog_priority": 9922}
    unknown = bulk_song("Bohemian Rhapsody", "Unknown")
    store.save_songs([cover, unknown, original], "musicbrainz:canonical:CC0", 100)
    assert [entry["artist"] for entry in store.search("Bohemian Rhapsody")] == [
        "Queen",
        "Phish",
        "Unknown",
    ]
    store.save_songs(
        [SONG | {"title": "Bohemian Rhapsody", "artist": "Queen"}], "apple:es", 100
    )
    assert store.search("Bohemian Rhapsody")[0]["song_key"] == SONG["song_key"]


def test_selection_multiple_isrc_editions_with_same_structured_artist_and_version_are_valid(
    tmp_path,
):
    alternatives = [
        SONG | {"isrc": "USAA10000001"},
        SONG | {"song_key": "apple:track:43", "isrc": "GBBB20000002"},
    ]
    app = create_normal_app(
        demo_config(tmp_path),
        background=False,
        song_search=SongSearch(lambda query: alternatives),
    )
    with TestClient(app) as client:
        room = admit(client, "Host", "host-account")
        token = app.state.song_search.tokens.issue(
            room["room_id"], bulk_song() | {"_catalog_reference": True}, 10**15
        )
        response = client.post(
            "/api/rooms/" + room["room_id"] + "/song-selection", json={"token": token}
        )
        assert response.status_code == 200, response.text
        metadata = app.state.song_search.tokens.decode(
            response.json()["token"], room["room_id"]
        )[0]
        assert metadata == alternatives[0]


def test_fresh_app_has_small_real_cc0_catalog_without_upstream_calls(tmp_path):
    calls = []
    app = create_normal_app(
        demo_config(tmp_path),
        background=False,
        song_search=SongSearch(lambda query: calls.append(query) or []),
    )
    with TestClient(app) as client:
        room = admit(client, "Host", "host-account")
        response = client.get(
            "/api/rooms/" + room["room_id"] + "/song-search",
            params={"q": "Fleetwood Dreams", "local": True},
        )
        assert response.status_code == 200 and calls == []
        assert any(
            song["title"] == "Dreams" and song["artist"] == "Fleetwood Mac"
            for song in response.json()["songs"]
        )


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("version", [1, 2, 4])
def test_unsupported_catalog_version_is_rejected_without_changing_metadata(
    tmp_path, shared, version
):
    from backend.storage.database import Database

    path = tmp_path / "catalog.sqlite3"
    if shared:
        Database(path).initialize()
    store = CatalogStore(path)
    store.initialize()
    store.save_songs([SONG], "apple:es", 100)
    with store.connect() as conn:
        conn.execute(
            "UPDATE component_schema_versions SET version=? WHERE component='catalog'",
            (version,),
        )
    with pytest.raises(RuntimeError, match="Unsupported catalog schema version"):
        store.initialize()
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT version FROM component_schema_versions WHERE component='catalog'"
            ).fetchone()[0]
            == version
        )
        assert conn.execute("PRAGMA user_version").fetchone()[0] == (6 if shared else 3)
        assert (
            conn.execute("SELECT title FROM catalog_songs").fetchone()[0]
            == SONG["title"]
        )


def test_current_catalog_with_missing_fields_is_rejected_without_upgrade(tmp_path):
    store = store_at(tmp_path)
    store.save_songs([SONG], "apple:es", 100)
    with store.connect() as conn:
        conn.execute("ALTER TABLE catalog_songs DROP COLUMN priority")
    with pytest.raises(RuntimeError, match="expected current fields"):
        store.initialize()
    with store.connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(catalog_songs)")
        }
        assert "priority" not in columns
        assert (
            conn.execute("SELECT title FROM catalog_songs").fetchone()[0]
            == SONG["title"]
        )


@pytest.mark.parametrize("version", [1, 4])
def test_standalone_unsupported_user_version_is_not_hidden_by_component_version(
    tmp_path, version
):
    store = store_at(tmp_path)
    with store.connect() as conn:
        conn.execute(f"PRAGMA user_version={version}")
    with pytest.raises(RuntimeError, match="Unsupported catalog schema version"):
        store.initialize()
    with store.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version


def test_bulk_selection_resolves_public_artist_identity_and_scores_through_real_http(
    normal_session,
):
    from tests.integration.test_music_admission import (
        five_players,
        prepare_game,
        start_round,
    )

    scenario = normal_session
    room, clients, player_ids = five_players(scenario)
    prefix, game_id, lease = prepare_game(scenario, room, 5)
    current, frozen = start_round(scenario, clients, prefix, game_id, lease)
    app = scenario["app"]
    # Public provider fixture accepts the explicit title-plus-artist lookup;
    # its metadata is independent of the private room snapshot.
    app.state.song_search.provider = lambda query: scenario["apple"].search(
        query.removesuffix(" test artist")
    )
    reference = bulk_song(frozen["title"], frozen["artist"]) | {
        "_catalog_reference": True
    }
    token = app.state.song_search.tokens.issue(
        room["room_id"], reference, scenario["clock"].value
    )
    result = clients[0].post(prefix + "/song-selection", json={"token": token})
    assert result.status_code == 200, result.text
    resolved = app.state.song_search.tokens.decode(
        result.json()["token"], room["room_id"]
    )[0]
    assert resolved["artists"] == [
        {"artist_key": "apple:artist:test", "name": "Test Artist"}
    ]
    assert not resolved["song_key"].startswith("musicbrainz:")
    for client in clients:
        response = client.post(
            prefix + f"/games/{game_id}/rounds/{current['id']}/answers",
            json={
                "song_guess_token": result.json()["token"],
                "who_player_ids": [owner["player_id"] for owner in frozen["listeners"]],
            },
        )
        assert response.status_code == 200, response.text
    state = clients[0].get(prefix + "/state").json()
    assert state["game"]["round"]["reveal"]["my_answer"]["song_match"] == "correct"
    assert state["game"]["round"]["reveal"]["my_answer"]["points"] > 100


def test_empty_query_memory_cache_does_not_outlive_persistent_negative_expiry(tmp_path):
    store = store_at(tmp_path)
    now, calls = [100.0], []
    search = SongSearch(
        lambda query: calls.append(query) or [],
        store=store,
        monotonic=lambda: now[0],
        clock=lambda: now[0],
    )
    assert search.provider_results("not found") == ([], False)
    now[0] += 61
    assert search.provider_results("not found") == ([], False)
    assert len(calls) == 2


def test_default_search_fetches_missing_exact_recording_despite_many_cached_prefix_hits(
    tmp_path,
):
    calls = []
    requested = "Catalog track same-account1"
    exact = SONG | {"song_key": "apple:track:exact1", "title": requested}

    def provider(query):
        calls.append(query)
        assert query == requested.casefold()
        return [exact]

    app = create_normal_app(
        demo_config(tmp_path), background=False, song_search=SongSearch(provider)
    )
    with TestClient(app) as client:
        room = admit(client, "Host", "host-account")
        path = "/api/rooms/" + room["room_id"] + "/song-search"
        prefixes = [
            SONG
            | {
                "song_key": f"apple:track:prefix{index}",
                "title": f"Catalog track same-account{index}",
            }
            for index in range(10, 20)
        ]
        app.state.catalog_store.save_songs(prefixes, "apple", 100)
        # The explicit local-first contract can show its available prefix metadata
        # without upstream calls; the default complete-search path must fetch.
        local = client.get(path, params={"q": requested, "local": True}).json()
        assert len(local["songs"]) == 10 and calls == []
        assert all(row["title"] != requested for row in local["songs"])
        first = client.get(path, params={"q": requested})
        assert first.status_code == 200, first.text
        assert first.json()["songs"][0]["title"] == requested
        assert calls == [requested.casefold()] and first.json()["cached"] is False
        second = client.get(path, params={"q": requested})
        assert second.status_code == 200 and second.json()["cached"] is True
        assert second.json()["songs"][0]["title"] == requested
        assert calls == [requested.casefold()]
