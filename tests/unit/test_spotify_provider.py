"""Spotify wire contracts and import evidence at the provider boundary."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.music.http import JsonHttpTransport, MusicProviderError, ProviderHttpError
from backend.music.spotify import SpotifyClient, normalize_track


def track(identifier, isrc=None, artists=None):
    return {"id": identifier, "name": "Song " + identifier,
            "artists": artists or [{"id": "artist-one", "name": "First Artist"},
                                   {"id": "artist-two", "name": "Featured Artist"}],
            "external_ids": {"isrc": isrc} if isrc else {},
            "album": {"images": [{"url": "https://images.example/cover.jpg"}]},
            "preview_url": "https://not-used.example/preview.mp3"}


class Transport:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, method, url, headers=None, data=None):
        self.calls.append((method, url, headers, data))
        return self.handler(method, url, headers, data)


def client(transport, clock=lambda: 100):
    return SpotifyClient("client-id", "server-secret", "http://127.0.0.1:8000/api/music/spotify/callback",
                         transport=transport, clock=clock)


def test_authorization_and_pkce_exchange_do_not_use_or_retain_refresh_token():
    transport = Transport(lambda *args: {"access_token": "access", "refresh_token": "private-refresh"})
    spotify = client(transport)
    query = parse_qs(urlsplit(spotify.authorization_url("bound-state", "challenge")).query)
    assert query["scope"] == ["user-top-read user-read-recently-played"]
    assert query["state"] == ["bound-state"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["challenge"]
    assert spotify.exchange_code("code", "verifier") == "access"
    method, url, headers, body = transport.calls[0]
    assert method == "POST" and url == "https://accounts.spotify.com/api/token"
    assert "Authorization" not in headers
    assert parse_qs(body.decode())["code_verifier"] == ["verifier"]
    assert "private-refresh" not in repr(vars(spotify))


def test_pkce_login_and_personal_import_work_without_app_search_secret():
    def respond(method, url, headers, data):
        if method == "POST":
            return {"access_token": "access"}
        if urlsplit(url).path == "/v1/me":
            return {"id": "account"}
        return {"items": []}
    transport = Transport(respond)
    spotify = SpotifyClient("client-id", None, "http://127.0.0.1:8000/api/music/spotify/callback",
                            transport=transport)
    assert spotify.configured and not spotify.search_configured
    assert spotify.authorization_url("state", "challenge")
    assert spotify.exchange_code("code", "verifier") == "access"
    assert spotify.profile("access") == "account"
    assert spotify.listening("access") == []
    for operation in (lambda: spotify.search("song"), spotify.decoys):
        with pytest.raises(MusicProviderError) as error:
            operation()
        assert error.value.code == "spotify_search_not_configured"
    assert len(transport.calls) == 6


@pytest.mark.parametrize("redirect", ["http://localhost:8000/callback", "ftp://example.com/callback", "",
    "http://127.0.0.1:8000/callback#fragment", "http://127.0.0.1:bad/callback", "https://:443/callback",
    "https://user:password@example.com/callback"])
def test_unconfigured_client_refuses_authorization_before_network(redirect):
    transport = Transport(lambda *args: pytest.fail("Unexpected request"))
    spotify = SpotifyClient("id", "secret", redirect, transport=transport)
    assert not spotify.configured
    with pytest.raises(MusicProviderError) as error:
        spotify.authorization_url("state", "challenge")
    assert error.value.code == "spotify_not_configured"


def test_normalized_facts_include_every_credit_isrc_and_artwork_without_preview():
    song = normalize_track(track("one", " usabc1234567 "))
    assert song["song_key"] == "spotify:track:one"
    assert song["isrc"] == "USABC1234567"
    assert song["artists"] == [{"artist_key": "spotify:artist:artist-one", "name": "First Artist"},
                               {"artist_key": "spotify:artist:artist-two", "name": "Featured Artist"}]
    assert song["artist"] == "First Artist, Featured Artist"
    assert song["artwork_url"] == "https://images.example/cover.jpg"
    assert "preview_url" not in song
    assert normalize_track({"id": "incomplete"}) is None
    assert normalize_track(track("local") | {"is_local": True}) is None
    assert normalize_track(track("no-images") | {"album": {"images": None}})["artwork_url"] is None


def test_personal_import_deduplicates_isrc_preserves_evidence_and_strongest_familiarity():
    one = track("original", "ISRC-ONE")
    duplicate = track("reissue", "isrc-one", [{"id": "third", "name": "Third Artist"}])
    def respond(method, url, headers, data):
        assert headers == {"Authorization": "Bearer user-token"}
        query = parse_qs(urlsplit(url).query)
        if urlsplit(url).path.endswith("recently-played"):
            assert query == {"limit": ["50"]}
            return {"items": [{"track": duplicate}, {"track": track("recent")} ]}
        assert query["limit"] == ["50"] and query["offset"] == ["0"]
        window = query["time_range"][0]
        return {"items": {"short_term": [one], "medium_term": [duplicate],
                          "long_term": [track("long"), duplicate]}[window]}
    transport = Transport(respond)
    songs = client(transport).listening("user-token")
    assert len(transport.calls) == 4
    assert {song["song_key"] for song in songs} == {"spotify:track:original", "spotify:track:long", "spotify:track:recent"}
    original = next(song for song in songs if song["song_key"].endswith("original"))
    assert original["familiarity"] == "easy"
    assert {row["source"] for row in original["source_evidence"]} == {
        "short_term", "medium_term", "long_term", "recently_played"}
    assert original["artists"][-1] == {"artist_key": "spotify:artist:third", "name": "Third Artist"}
    assert next(song for song in songs if song["song_key"].endswith("long"))["familiarity"] == "hard"
    assert next(song for song in songs if song["song_key"].endswith("recent"))["familiarity"] == "medium"


def test_import_cap_retains_balanced_strata_and_recent_evidence_is_not_exact_frequency():
    def respond(method, url, headers, data):
        query = parse_qs(urlsplit(url).query)
        if urlsplit(url).path.endswith("recently-played"):
            return {"items": []}
        window = query["time_range"][0]
        return {"items": [track(window + str(number)) for number in range(50)]}
    songs = client(Transport(respond)).listening("user")
    assert len(songs) == 60
    assert {level: sum(song["familiarity"] == level for song in songs)
            for level in ("easy", "medium", "hard")} == {"easy": 20, "medium": 20, "hard": 20}
    assert all("play_count" not in song for song in songs)


def test_catalog_search_uses_server_credentials_market_and_one_cached_app_token():
    now = [100]
    token_number = [0]
    def respond(method, url, headers, data):
        if method == "POST":
            token_number[0] += 1
            assert headers["Authorization"].startswith("Basic ")
            assert data == b"grant_type=client_credentials"
            return {"access_token": "app-" + str(token_number[0]), "expires_in": 3600}
        query = parse_qs(urlsplit(url).query)
        assert query == {"q": ["Song & artist"], "type": ["track"], "market": ["ES"], "limit": ["10"], "offset": ["0"]}
        return {"tracks": {"items": [track("one"), track("one"), {"id": "bad"}]}}
    spotify = client(Transport(respond), clock=lambda: now[0])
    assert len(spotify.search("Song & artist")) == 1
    spotify.search("Song & artist")
    assert token_number[0] == 1
    now[0] += 3571
    spotify.search("Song & artist")
    assert token_number[0] == 2


def test_simultaneous_catalog_queries_coalesce_token_acquisition():
    token_calls = []
    entered, finish = threading.Event(), threading.Event()
    def respond(method, url, headers, data):
        if method == "POST":
            token_calls.append(url)
            entered.set()
            assert finish.wait(2)
            return {"access_token": "app", "expires_in": 3600}
        return {"tracks": {"items": [track("one")]}}
    spotify = client(Transport(respond))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(spotify.search, "first")
        assert entered.wait(2)
        second = pool.submit(spotify.search, "second")
        finish.set()
        assert first.result() and second.result()
    assert len(token_calls) == 1


def test_revoked_app_token_is_replaced_once_without_reauthorizing_players():
    token_count = [0]
    def respond(method, url, headers, data):
        if method == "POST":
            token_count[0] += 1
            return {"access_token": "app-" + str(token_count[0]), "expires_in": 3600}
        if headers["Authorization"] == "Bearer app-1":
            raise ProviderHttpError(401)
        return {"tracks": {"items": [track("one")]}}
    assert client(Transport(respond)).search("query")
    assert token_count[0] == 2


def test_persistent_app_token_rejection_has_a_finite_retry_budget():
    calls = []
    def respond(method, url, headers, data):
        calls.append(method)
        if method == "POST":
            return {"access_token": "app", "expires_in": 3600}
        raise ProviderHttpError(401)
    with pytest.raises(MusicProviderError):
        client(Transport(respond)).search("query")
    assert calls == ["POST", "GET", "POST", "GET"]


def test_decoys_are_independent_public_catalog_search_not_personal_history():
    offsets = []
    def respond(method, url, headers, data):
        if method == "POST":
            return {"access_token": "app", "expires_in": 3600}
        query = parse_qs(urlsplit(url).query)
        assert query["q"] == ["year:2010-2025"]
        offset = int(query["offset"][0])
        offsets.append(offset)
        return {"tracks": {"items": [track(str(offset + index)) for index in range(10)]}}
    songs = client(Transport(respond)).decoys()
    assert len(songs) == 30 and offsets == [0, 10, 20]


@pytest.mark.parametrize("status,code,api_status", [(403, "spotify_account_not_allowed", 403),
    (401, "spotify_authorization_expired", 401), (429, "spotify_rate_limited", 429),
    (500, "spotify_unavailable", 503)])
def test_provider_failures_are_safe_structured_errors_without_retry_sleep(status, code, api_status):
    def fail(*args):
        raise ProviderHttpError(status, 12)
    with pytest.raises(MusicProviderError) as error:
        client(Transport(fail)).profile("secret-user-token")
    assert error.value.code == code and error.value.status == api_status
    assert "secret-user-token" not in str(error.value)
    if status == 429:
        assert error.value.details == {"retry_after_seconds": 12}


@pytest.mark.parametrize("payload", [{}, {"id": None}, {"id": 2}])
def test_profile_requires_an_account_identifier(payload):
    with pytest.raises(MusicProviderError) as error:
        client(Transport(lambda *args: payload)).profile("token")
    assert error.value.code == "spotify_invalid_response"


def test_http_transport_bounds_body_and_timeout():
    seen = []
    def open_request(request, timeout):
        seen.append((request, timeout))
        return BytesIO(json.dumps({"ok": True}).encode())
    transport = JsonHttpTransport(timeout=4, opener=open_request)
    assert transport.request("GET", "https://api.spotify.com/v1/me") == {"ok": True}
    assert seen[0][1] == 4
    assert seen[0][0].get_header("Accept") == "application/json"
    with pytest.raises(MusicProviderError):
        JsonHttpTransport(max_bytes=2, opener=open_request).request("GET", "https://api.spotify.com")


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null"])
def test_http_transport_rejects_malformed_payloads(body):
    with pytest.raises(MusicProviderError) as error:
        JsonHttpTransport(opener=lambda *args, **kwargs: BytesIO(body)).request("GET", "https://provider")
    assert error.value.code == "music_provider_unavailable"


def test_http_errors_do_not_read_sensitive_bodies_and_bound_retry_after():
    body = BytesIO(b"sensitive-token")
    def fail(*args, **kwargs):
        raise HTTPError("https://provider", 429, "secret message", {"Retry-After": "10000"}, body)
    with pytest.raises(ProviderHttpError) as error:
        JsonHttpTransport(opener=fail).request("GET", "https://provider")
    assert error.value.status == 429 and error.value.retry_after == 120
    assert body.closed
    assert "sensitive" not in str(error.value) and "secret" not in str(error.value)


def test_network_errors_are_sanitized():
    def fail(*args, **kwargs):
        raise URLError("secret token in upstream error")
    with pytest.raises(MusicProviderError) as error:
        JsonHttpTransport(opener=fail).request("GET", "https://provider")
    assert "secret" not in str(error.value)
