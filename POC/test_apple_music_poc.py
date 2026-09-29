from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).with_name("apple_music_poc.py")
SPEC = importlib.util.spec_from_file_location("apple_music_poc", MODULE_PATH)
assert SPEC and SPEC.loader
poc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = poc
SPEC.loader.exec_module(poc)


def test_developer_token_has_required_header_claims_and_optional_origin(tmp_path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "AuthKey_TEST.p8"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    config = poc.Config("TEAM123456", "KEY1234567", key_path)

    token = poc.make_developer_token(config, origin="http://127.0.0.1:8765", now=1_000)

    assert jwt.get_unverified_header(token) == {
        "alg": "ES256",
        "kid": "KEY1234567",
        "typ": "JWT",
    }
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims == {
        "iss": "TEAM123456",
        "iat": 1_000,
        "exp": 22_600,
        "origin": ["http://127.0.0.1:8765"],
    }


def test_library_song_reads_catalog_isrc_and_preview() -> None:
    resource = {
        "id": "i.library-id",
        "type": "library-songs",
        "attributes": {
            "name": "Example Song",
            "artistName": "Example Artist",
            "playParams": {"catalogId": "123"},
        },
        "relationships": {
            "catalog": {
                "data": [
                    {
                        "id": "123",
                        "attributes": {
                            "isrc": "USRC17607839",
                            "previews": [{"url": "https://audio-ssl.itunes.apple.com/example.m4a"}],
                        },
                    }
                ]
            }
        },
    }

    song = poc.song_from_resource(resource, "library")

    assert song is not None
    assert song.resource_id == "123"
    assert song.isrc == "USRC17607839"
    assert song.embedded_preview_url == "https://audio-ssl.itunes.apple.com/example.m4a"


def test_non_song_heavy_rotation_resource_is_not_misrepresented() -> None:
    resource = {
        "id": "album-1",
        "type": "albums",
        "attributes": {"name": "An Album", "artistName": "An Artist"},
    }
    assert poc.song_from_resource(resource, "heavy_rotation") is None


def spotify_track(
    track_id: str = "spotify-1",
    title: str = "Example Song",
    artist: str = "Example Artist",
    isrc: str | None = "usrc17607839",
) -> dict:
    external_ids = {"isrc": isrc} if isrc is not None else {}
    return {
        "id": track_id,
        "name": title,
        "artists": [{"name": artist}],
        "external_ids": external_ids,
        "preview_url": "https://spotify.example/ignored.mp3",
    }


def test_spotify_track_converts_to_shared_song_and_normalises_isrc() -> None:
    song = poc.song_from_spotify_track(
        spotify_track(), "spotify_top_short_term"
    )

    assert song == poc.Song(
        source="spotify_top_short_term",
        resource_id="spotify-1",
        title="Example Song",
        artist="Example Artist",
        isrc="USRC17607839",
        embedded_preview_url=None,
    )


def test_spotify_track_skips_malformed_items_and_keeps_text_fallback() -> None:
    assert poc.song_from_spotify_track(
        {"id": "bad", "name": "Missing artist", "artists": []},
        "spotify_recently_played",
    ) is None

    song = poc.song_from_spotify_track(
        spotify_track(isrc="not-an-isrc"), "spotify_recently_played"
    )
    assert song is not None
    assert song.isrc is None
    assert song.identity == "text:example song|example artist"


def test_deduplication_uses_isrc_then_normalised_title_artist() -> None:
    songs = [
        poc.Song("library", "1", "Song (feat. Guest)", "Artist", None),
        poc.Song("recent", "2", " song ", "ARTIST", None),
        poc.Song("recent", "3", "Different title", "Someone", "USRC17607839"),
        poc.Song("library", "4", "Different edition", "Someone", "USRC17607839"),
    ]
    unique = poc.deduplicate_songs(songs)
    assert len(unique) == 2
    assert {song.identity for song in unique} == {
        "text:song|artist",
        "isrc:USRC17607839",
    }


def test_deduplication_reconciles_text_only_copy_with_single_isrc_recording() -> None:
    songs = [
        poc.Song("library", "library-1", "Song (feat. Guest)", "Artist", None),
        poc.Song("recent", "catalog-1", "Song", "Artist", "USRC17607839"),
    ]

    unique = poc.deduplicate_songs(songs)

    assert len(unique) == 1
    assert unique[0].identity == "isrc:USRC17607839"


def test_preview_metrics_are_cumulative() -> None:
    results = [
        poc.PreviewResult("1", "A", "A", "USRC17607839", "apple", "https://a"),
        poc.PreviewResult("2", "B", "B", None, "itunes", "https://b"),
        poc.PreviewResult("3", "C", "C", "GBUM71029604", "deezer", "https://c"),
        poc.PreviewResult("4", "D", "D", None, None, None),
    ]
    metrics = poc.preview_metrics(results)
    assert metrics["apple_percent"] == 25.0
    assert metrics["after_itunes_percent"] == 50.0
    assert metrics["after_deezer_percent"] == 75.0
    assert metrics["unresolved_count"] == 1
    assert metrics["coverage_passes"] is False


def test_spotify_probe_returns_deduplicated_sanitized_song_list() -> None:
    first = spotify_track()
    second = spotify_track(
        track_id="spotify-2",
        title="No ISRC Song",
        artist="Another Artist",
        isrc=None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/me/top/tracks":
            return httpx.Response(200, json={"items": [first]})
        if request.url.path == "/v1/me/player/recently-played":
            return httpx.Response(
                200,
                json={"items": [{"track": first}, {"track": second}]},
            )
        raise AssertionError(f"Unexpected Spotify request: {request.url}")

    async def run() -> tuple[dict, list]:
        session = poc.SessionData(
            spotify_access_token="access-token",
            spotify_expires_at=float("inf"),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await poc.spotify_probe(client, poc.Config(None, None, None), session)

    result, songs = asyncio.run(run())

    assert result["passes"] is True
    assert result["unique_songs"] == 2
    assert result["unique_isrc_count"] == 1
    assert result["unique_isrc_percent"] == 50.0
    assert len(songs) == 2
    assert result["songs"][0] == {
        "title": "Example Song",
        "artist": "Example Artist",
        "isrc": "USRC17607839",
        "sources": [
            "top_short_term",
            "top_medium_term",
            "top_long_term",
            "recently_played",
        ],
    }
    assert set(result["songs"][0]) == {"title", "artist", "isrc", "sources"}


def test_spotify_song_is_resolved_through_apple_catalog(monkeypatch) -> None:
    preview_url = "https://audio-ssl.itunes.apple.com/example.m4a"
    monkeypatch.setattr(poc, "apple_headers", lambda _config: {})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/catalog/us/songs"
        assert request.url.params["filter[isrc]"] == "USRC17607839"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "apple-1",
                        "attributes": {
                            "isrc": "USRC17607839",
                            "previews": [{"url": preview_url}],
                        },
                    }
                ]
            },
        )

    async def run() -> tuple[dict, list]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await poc.preview_probe(
                client,
                poc.Config(None, None, None),
                [
                    poc.Song(
                        "spotify_top_short_term",
                        "spotify-1",
                        "Example Song",
                        "Example Artist",
                        "USRC17607839",
                    )
                ],
            )

    metrics, previews = asyncio.run(run())

    assert metrics["apple_catalog_match_count"] == 1
    assert metrics["apple_catalog_match_percent"] == 100.0
    assert metrics["apple_percent"] == 100.0
    assert previews[0].source == "apple"
    assert previews[0].url == preview_url


def test_activating_song_corpus_invalidates_dependent_results() -> None:
    session = poc.SessionData(
        songs=[poc.Song("library", "old", "Old", "Artist", None)],
        song_provider="apple_personal",
        previews=[poc.PreviewResult("old", "Old", "Artist", None, None, None)],
        played_samples={"old"},
        report={"q4": {"passes": True}, "q5": {"passes": True}, "q6": {"passes": True}},
    )
    replacement = poc.Song(
        "spotify_recently_played", "new", "New", "Artist", "USRC17607839"
    )

    poc.activate_song_corpus(session, "spotify", [replacement])

    assert session.songs == [replacement]
    assert session.song_provider == "spotify"
    assert session.previews == []
    assert session.played_samples == set()
    assert "q4" not in session.report
    assert "q5" not in session.report
    assert session.report["q6"]["passes"] is True


def test_sync_summary_uses_offset_corrected_start_spread() -> None:
    run = poc.SyncRun("run", "https://example.apple.com/a.m4a", "Track", 10_000, 0)
    run.observations = {
        "a": {
            "client_id": "a",
            "estimated_server_start_ms": 10_080.0,
            "scheduled_server_start_ms": 10_000.0,
            "best_rtt_ms": 12.0,
            "audio_current_time": 0.02,
            "audible": True,
        },
        "b": {
            "client_id": "b",
            "estimated_server_start_ms": 10_240.0,
            "scheduled_server_start_ms": 10_000.0,
            "best_rtt_ms": 18.0,
            "audio_current_time": 0.03,
            "audible": True,
        },
    }
    summary = poc.sync_summary(run)
    assert summary["inter_device_drift_ms"] == 160.0
    assert summary["max_absolute_start_error_ms"] == 240.0
    assert summary["passes"] is True


def test_sync_requires_audibility_and_on_time_start() -> None:
    run = poc.SyncRun("run", "https://example.apple.com/a.m4a", "Track", 10_000, 0)
    run.observations = {
        "a": {
            "client_id": "a",
            "estimated_server_start_ms": 11_000.0,
            "scheduled_server_start_ms": 10_000.0,
            "best_rtt_ms": 12.0,
            "audio_current_time": 0.02,
            "audible": True,
        },
        "b": {
            "client_id": "b",
            "estimated_server_start_ms": 11_100.0,
            "scheduled_server_start_ms": 10_000.0,
            "best_rtt_ms": 18.0,
            "audio_current_time": 0.03,
            "audible": False,
        },
    }

    summary = poc.sync_summary(run)

    assert summary["inter_device_drift_ms"] == 100.0
    assert summary["max_absolute_start_error_ms"] == 1100.0
    assert summary["audible_confirmed_count"] == 1
    assert summary["passes"] is False


def test_capped_pagination_marks_final_oversized_page_truncated(
    tmp_path: Path,
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "AuthKey_TEST.p8"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    config = poc.Config("TEAM123456", "KEY1234567", key_path, max_items_per_list=3)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("offset") == "2":
            return httpx.Response(200, json={"data": [{"id": "3"}, {"id": "4"}]})
        return httpx.Response(
            200,
            json={
                "data": [{"id": "1"}, {"id": "2"}],
                "next": "/v1/me/library/songs?offset=2",
            },
        )

    async def run() -> tuple[list[dict], dict]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await poc.fetch_apple_pages(
                client,
                config,
                "/v1/me/library/songs",
                user_token="user-token",
                params={"limit": 2},
            )

    items, metrics = asyncio.run(run())
    assert [item["id"] for item in items] == ["1", "2", "3"]
    assert metrics["page_sizes"] == [2, 2]
    assert metrics["truncated"] is True


def test_recent_library_songs_request_catalog_relationship(monkeypatch) -> None:
    seen: dict[str, dict] = {}

    async def fake_fetch(_client, _config, path, *, user_token, params):
        seen[path] = params
        return [], {
            "resource_count": 0,
            "pages": 1,
            "page_sizes": [0],
            "total_available": 0,
            "truncated": False,
            "elapsed_ms": 1,
        }

    monkeypatch.setattr(poc, "fetch_apple_pages", fake_fetch)
    asyncio.run(poc.listening_probe(None, poc.Config(None, None, None), "token"))

    recent = seen["/v1/me/recent/played/tracks"]
    assert recent["types"] == "songs,library-songs"
    assert recent["include[library-songs]"] == "catalog"


def test_health_and_page_work_without_credentials() -> None:
    config = poc.Config(None, None, None)
    with TestClient(poc.create_app(config), client=("127.0.0.1", 50000)) as client:
        health = client.get("/api/health")
        page = client.get("/")
        failed_catalog = client.post("/api/apple/catalog-test", json={"term": "test"})
        report = client.get("/api/report").json()
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["apple_configured"] is False
    assert health.json()["lan_sync_enabled"] is False
    assert health.json()["lan_sync_origins"] == []
    assert "samesite=lax" in health.headers["set-cookie"].lower()
    assert page.status_code == 200
    assert "Who's On Repeat" in page.text
    assert poc.SESSION_COOKIE in client.cookies
    assert failed_catalog.status_code == 503
    assert report["report"]["q1"]["passes"] is False
    assert "APPLE_TEAM_ID" in report["markdown"]


def test_health_advertises_lan_origin_only_in_lan_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        poc, "lan_addresses", lambda port: [f"http://192.168.1.20:{port}"]
    )
    app = poc.create_app(poc.Config(None, None, None), lan_enabled=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        health = client.get("/api/health").json()

    assert health["lan_sync_enabled"] is True
    assert health["lan_sync_origins"] == ["http://192.168.1.20:80"]


def test_failed_apple_authorization_is_recorded_without_a_token() -> None:
    with TestClient(
        poc.create_app(poc.Config(None, None, None)), client=("127.0.0.1", 50000)
    ) as client:
        result = client.post(
            "/api/apple/authorization-failure",
            json={
                "transport": "http",
                "reason": "AUTHORIZATION_ERROR: authorization did not return a user token",
            },
        )
        report = client.get("/api/report").json()["report"]["q2"]

    assert result.status_code == 200
    assert report == {
        "passes": False,
        "transport": "http",
        "error": "AUTHORIZATION_ERROR: authorization did not return a user token",
    }


def test_sync_api_calculates_two_device_result() -> None:
    with TestClient(poc.create_app(poc.Config(None, None, None))) as client:
        created = client.post(
            "/api/sync/runs",
            json={
                "preview_url": "https://audio-ssl.itunes.apple.com/example.m4a",
                "title": "Example",
            },
        ).json()
        run_id = created["run_id"]
        scheduled = client.post(
            f"/api/sync/runs/{run_id}/schedule", json={"delay_ms": 3000}
        ).json()
        start = scheduled["start_at_ms"]
        first = {
            "client_id": "client-a",
            "estimated_server_start_ms": start + 40,
            "scheduled_server_start_ms": 0,
            "clock_offset_ms": 1,
            "best_rtt_ms": 10,
            "audio_current_time": 0.01,
            "audible": True,
        }
        second = {**first, "client_id": "client-b", "estimated_server_start_ms": start + 120}
        client.post(f"/api/sync/runs/{run_id}/observations", json=first)
        result = client.post(
            f"/api/sync/runs/{run_id}/observations", json=second
        ).json()

    assert result["inter_device_drift_ms"] == 80.0
    assert result["max_absolute_start_error_ms"] == 120.0
    assert result["audible_confirmed_count"] == 2
    assert result["passes"] is True


def test_token_routes_reject_lan_clients_before_reading_credentials() -> None:
    with TestClient(
        poc.create_app(poc.Config(None, None, None)), client=("192.168.1.25", 50000)
    ) as client:
        result = client.get("/api/apple/music-kit-config")
    assert result.status_code == 403


def test_spotify_denial_validates_and_consumes_oauth_state() -> None:
    config = poc.Config(
        None,
        None,
        None,
        spotify_client_id="client-id",
    )
    with TestClient(
        poc.create_app(config),
        follow_redirects=False,
        client=("127.0.0.1", 50000),
    ) as client:
        login = client.get("/api/spotify/login")
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
        denied = client.get(f"/callback?error=access_denied&state={state}")
        replay = client.get(f"/callback?error=access_denied&state={state}")

    assert login.status_code == 302
    assert denied.status_code == 303
    assert denied.headers["location"] == "/?spotify_error=access_denied"
    assert replay.status_code == 400


def test_spotify_login_uses_pkce_with_client_id_only() -> None:
    config = poc.Config(None, None, None, spotify_client_id="client-id")
    with TestClient(
        poc.create_app(config),
        follow_redirects=False,
        client=("127.0.0.1", 50000),
    ) as client:
        login = client.get("/api/spotify/login")

    params = parse_qs(urlparse(login.headers["location"]).query)
    session_id = login.cookies.get(poc.SESSION_COOKIE)
    assert login.status_code == 302
    assert params["client_id"] == ["client-id"]
    assert params["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in params
    assert session_id is not None
    verifier = poc.SESSIONS[session_id].spotify_code_verifier
    assert verifier is not None
    expected_challenge = poc.base64.urlsafe_b64encode(
        poc.hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert params["code_challenge"] == [expected_challenge]


def test_spotify_pkce_callback_exchanges_code_without_secret(monkeypatch) -> None:
    captured: dict = {}

    async def fake_request_json(_client, provider, method, url, **kwargs):
        captured.update(
            {"provider": provider, "method": method, "url": url, "kwargs": kwargs}
        )
        return {
            "access_token": "spotify-access",
            "refresh_token": "spotify-refresh",
            "expires_in": 3600,
        }

    monkeypatch.setattr(poc, "request_json", fake_request_json)
    config = poc.Config(None, None, None, spotify_client_id="client-id")
    with TestClient(
        poc.create_app(config),
        follow_redirects=False,
        client=("127.0.0.1", 50000),
    ) as client:
        login = client.get("/api/spotify/login")
        login_params = parse_qs(urlparse(login.headers["location"]).query)
        callback = client.get(f"/callback?code=auth-code&state={login_params['state'][0]}")

    data = captured["kwargs"]["data"]
    assert callback.status_code == 303
    assert callback.headers["location"] == "/?spotify=connected"
    assert "auth" not in captured["kwargs"]
    assert data["client_id"] == "client-id"
    assert data["code"] == "auth-code"
    assert data["code_verifier"]
    expected_challenge = poc.base64.urlsafe_b64encode(
        poc.hashlib.sha256(data["code_verifier"].encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert login_params["code_challenge"] == [expected_challenge]


def test_spotify_pkce_refresh_uses_client_id_without_basic_auth() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["data"] = parse_qs((await request.aread()).decode("utf-8"))
        return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})

    async def run() -> str:
        session = poc.SessionData(spotify_refresh_token="refresh")
        config = poc.Config(None, None, None, spotify_client_id="client-id")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await poc.spotify_access_token(client, config, session)

    assert asyncio.run(run()) == "fresh"
    assert "authorization" not in captured["headers"]
    assert captured["data"] == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["refresh"],
        "client_id": ["client-id"],
    }


def test_spotify_endpoint_activates_songs_for_apple_preview_probe(monkeypatch) -> None:
    imported = poc.Song(
        "spotify_top_short_term",
        "spotify-1",
        "Example Song",
        "Example Artist",
        "USRC17607839",
    )

    async def fake_spotify_probe(_client, _config, _session):
        return (
            {
                "top_tracks": {
                    "short_term": {
                        "count": 1,
                        "usable_song_count": 1,
                        "isrc_count": 1,
                        "isrc_percent": 100.0,
                    }
                },
                "recently_played": {
                    "count": 0,
                    "usable_song_count": 0,
                    "isrc_count": 0,
                    "isrc_percent": 0.0,
                },
                "unique_songs": 1,
                "unique_isrc_count": 1,
                "unique_isrc_percent": 100.0,
                "passes": True,
                "songs": [
                    {
                        "title": imported.title,
                        "artist": imported.artist,
                        "isrc": imported.isrc,
                        "sources": ["top_short_term"],
                    }
                ],
            },
            [imported],
        )

    async def fake_preview_probe(_client, _config, songs):
        assert songs == [imported]
        return (
            {
                "total_songs": 1,
                "apple_lookup_eligible_count": 1,
                "apple_catalog_match_count": 1,
                "apple_catalog_match_percent": 100.0,
                "apple_count": 1,
                "apple_percent": 100.0,
                "after_itunes_count": 1,
                "after_itunes_percent": 100.0,
                "after_deezer_count": 1,
                "after_deezer_percent": 100.0,
                "unresolved_count": 0,
                "coverage_passes": True,
                "provider_errors": {},
                "manual_playback_confirmed": 0,
                "three_clip_check_passes": False,
            },
            [
                poc.PreviewResult(
                    imported.identity,
                    imported.title,
                    imported.artist,
                    imported.isrc,
                    "apple",
                    "https://audio-ssl.itunes.apple.com/example.m4a",
                )
            ],
        )

    monkeypatch.setattr(poc, "spotify_probe", fake_spotify_probe)
    monkeypatch.setattr(poc, "preview_probe", fake_preview_probe)

    with TestClient(poc.create_app(poc.Config(None, None, None))) as client:
        spotify = client.post("/api/spotify/probe")
        health = client.get("/api/health").json()
        preview = client.post("/api/apple/previews")
        report = client.get("/api/report").json()["report"]

    assert spotify.status_code == 200
    assert spotify.json()["songs"] == [
        {
            "title": "Example Song",
            "artist": "Example Artist",
            "isrc": "USRC17607839",
            "sources": ["top_short_term"],
        }
    ]
    assert health["song_provider"] == "spotify"
    assert health["song_count"] == 1
    assert preview.status_code == 200
    assert preview.json()["input_provider"] == "spotify"
    assert preview.json()["input_song_count"] == 1
    assert "songs" not in report["q6"]
    assert report["q4"]["input_provider"] == "spotify"


def test_report_contains_required_list_and_chart_measurements() -> None:
    list_result = {
        "song_count": 12,
        "resource_count": 15,
        "page_sizes": [10, 5],
        "requested_page_limit": 10,
        "total_available": 15,
        "isrc_percent": 75.0,
        "elapsed_ms": 123,
        "truncated": False,
        "resource_types": {"songs": 12, "albums": 3},
    }
    markdown = poc.report_markdown(
        {
            "q3": {
                "passes": True,
                "unique_songs": 12,
                "heavy_rotation": list_result,
                "recently_played": list_result,
                "library": list_result,
            },
            "q7": {
                "passes": True,
                "song_count": 50,
                "isrc_percent": 98.0,
                "preview_percent": 96.0,
                "isrc_and_preview_count": 47,
                "elapsed_ms": 88,
            },
        }
    )

    assert "pages [10, 5] at requested limit 10" in markdown
    assert "ISRC 75.0%" in markdown
    assert "previews 96.0%" in markdown
