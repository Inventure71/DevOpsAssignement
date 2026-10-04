"""Recording identity, provider delivery, shared cache and import admission."""

import threading
from concurrent.futures import ThreadPoolExecutor
from email.message import Message

import pytest

from backend.core.errors import DomainError
from backend.music.importer import MusicImporter
from backend.music.media import (
    _SafeRedirect,
    allowed_preview_url,
    matches_recording,
    probe_preview,
)
from backend.music.previews import PreviewResolver
from backend.music.sources import SpotifyListeningAdapter


def song(index=1, **changes):
    return {
        "song_key": f"spotify:track:{index}",
        "title": "Stronger",
        "artist": "Kanye West",
        "artists": [{"artist_key": "spotify:artist:kanye", "name": "Kanye West"}],
        "isrc": "USUM70741277",
        "artwork_url": "https://i.scdn.co/image/original",
        "familiarity": "easy",
        **changes,
    }


PREVIEW_URL = "https://audio-ssl.itunes.apple.com/sample.m4a"


class FakeCatalog:
    def __init__(self, resolve=None):
        self.callback = resolve or (lambda entry: entry | {"preview_url": PREVIEW_URL})

    def resolve_verified(self, entry, on_verified=None):
        return self.callback(entry)

    def refresh(self, entry, known, on_verified=None, on_invalid=None):
        return self.callback(entry)


def test_resolved_preview_keeps_spotify_identity_and_every_credit():
    original = song(
        artists=[
            {"artist_key": "spotify:artist:kanye", "name": "Kanye West"},
            {"artist_key": "spotify:artist:other", "name": "Guest"},
        ]
    )
    resolver = PreviewResolver(FakeCatalog())
    result = resolver.resolve(original)
    assert result == original | {"preview_url": PREVIEW_URL}
    assert "preview_url" not in original


@pytest.mark.parametrize(
    "title, artist",
    [
        ("Stronger - Instrumental", "Kanye West"),
        ("Stronger (Live)", "Kanye West"),
        ("Stronger (Remix)", "Kanye West"),
        ("Stronger", "Cover Band"),
        ("Stronger (Remastered)", "Kanye West"),
    ],
)
def test_rejects_different_recording_even_with_identical_isrc(title, artist):
    assert not matches_recording(
        song(), {"title": title, "artist": artist, "isrc": song()["isrc"]}
    )


def test_feature_credits_are_equivalent():
    assert matches_recording(
        song(title="Stronger (feat. Guest)"),
        {"title": "Stronger", "artist": "Kanye West"},
    )


def test_cache_coalesces_media_but_never_reuses_another_players_familiarity():
    calls = []
    resolver = PreviewResolver(
        FakeCatalog(
            lambda entry: calls.append(entry) or entry | {"preview_url": PREVIEW_URL}
        )
    )
    first = resolver.resolve(song(familiarity="easy", source_evidence=["top-short"]))
    first["artists"][0]["name"] = "tampered"
    second = resolver.resolve(song(familiarity="hard", source_evidence=["recent"]))
    assert second["familiarity"] == "hard"
    assert second["source_evidence"] == ["recent"]
    assert second["artists"][0]["name"] == "Kanye West"
    assert len(calls) == 1


def test_missing_artwork_can_use_provider_reference():
    resolver = PreviewResolver(
        FakeCatalog(
            lambda entry: (
                entry
                | {
                    "preview_url": PREVIEW_URL,
                    "artwork_url": "https://is1-ssl.mzstatic.com/cover.jpg",
                }
            )
        )
    )
    assert (
        resolver.resolve(song(artwork_url=None))["artwork_url"]
        == "https://is1-ssl.mzstatic.com/cover.jpg"
    )


def test_inflight_duplicate_request_only_fetches_once():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def fetch(entry):
        calls.append(entry)
        entered.set()
        assert release.wait(2)
        return entry | {"preview_url": PREVIEW_URL}

    resolver = PreviewResolver(FakeCatalog(fetch))
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(resolver.resolve, song())
        assert entered.wait(2)
        second = executor.submit(resolver.resolve, song(familiarity="hard"))
        release.set()
        assert first.result()["familiarity"] == "easy"
        assert second.result()["familiarity"] == "hard"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure,ttl", [(False, 60), (True, 10)], ids=["missing", "error"]
)
def test_negative_media_cache_expires_and_retries(failure, ttl):
    now, calls = [100.0], []

    def fetch(entry):
        calls.append(entry)
        if failure:
            raise DomainError("preview_provider_unavailable", "Offline", 503)

    resolver = PreviewResolver(FakeCatalog(fetch), monotonic=lambda: now[0])

    def resolve():
        if failure:
            with pytest.raises(DomainError, match="Offline") as error:
                resolver.resolve(song())
            assert error.value.code == "preview_provider_unavailable"
        else:
            assert resolver.resolve(song()) is None

    resolve()
    resolve()
    assert len(calls) == 1
    now[0] += ttl + 1
    resolve()
    assert len(calls) == 2


@pytest.mark.parametrize(
    "url",
    [
        "http://cdns-preview-a.dzcdn.net/a.mp3",
        "https://127.0.0.1/a.mp3",
        "https://cdns-preview-a.dzcdn.net.evil.test/a.mp3",
        "https://evil.test/a.mp3",
        "https://user:password@audio-ssl.itunes.apple.com/a",
        "https://audio-ssl.itunes.apple.com:8443/a",
        "https://audio-ssl.itunes.apple.com:wrong/a",
        "file:///etc/passwd",
    ],
)
def test_disallows_untrusted_audio_hosts(url):
    assert not allowed_preview_url(url)


def test_redirect_cannot_escape_audio_allowlist():
    with pytest.raises(ValueError, match="permitted hosts"):
        _SafeRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://127.0.0.1/secret"
        )


@pytest.mark.parametrize(
    "mime,sample,expected",
    [
        ("audio/x-m4p", b"\x00\x00\x00\x20ftypM4A " + b"0" * 256, True),
        ("application/octet-stream", b"ID3" + b"0" * 256, True),
        ("text/html", b"<html>not a song</html>", False),
        ("audio/mpeg", b"ID3", False),
    ],
)
def test_probe_uses_bounded_range_and_checks_delivered_media(
    monkeypatch, mime, sample, expected
):
    class Response:
        headers = Message()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, count):
            assert count == 256
            return sample[:count]

    response = Response()
    response.headers["Content-Type"] = mime

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Range") == "bytes=0-255"
            assert timeout == 4
            assert request.full_url == PREVIEW_URL
            return response

    monkeypatch.setattr("backend.music.media.build_opener", lambda handler: Opener())
    assert probe_preview(PREVIEW_URL) is expected


def test_probe_rejects_untrusted_url_before_network(monkeypatch):
    monkeypatch.setattr(
        "backend.music.media.build_opener",
        lambda handler: pytest.fail("Must not connect"),
    )
    assert probe_preview("https://127.0.0.1/private") is False


class FakeSpotify:
    def __init__(self, count=15):
        self.count = count

    def profile(self, token):
        assert token == "personal-token"
        return "account-id"

    def listening(self, token):
        return [song(index) for index in range(self.count)]


def decoy_tracks():
    return [song(index, isrc=f"DECOY{index}") for index in range(100, 110)]


class FakeResolver:
    def __init__(self, missing=(), failing=()):
        self.missing, self.failing = set(missing), set(failing)

    def resolve(self, entry):
        index = int(entry["song_key"].split(":")[-1])
        if index in self.failing:
            raise DomainError("preview_provider_unavailable", "Offline", 503)
        return None if index in self.missing else entry | {"preview_url": PREVIEW_URL}


def test_import_preserves_observed_songs_and_includes_host_decoys():
    result = MusicImporter(
        SpotifyListeningAdapter(FakeSpotify()),
        FakeResolver(missing=[0, 1]),
        decoy_tracks,
    ).import_account("personal-token", True)
    assert result["account_id"] == "account-id"
    assert len(result["songs"]) == 13 and len(result["decoys"]) == 10
    assert {entry["song_key"] for entry in result["songs"]}.isdisjoint(
        {"spotify:track:0", "spotify:track:1"}
    )
    assert len(result["observed_songs"]) == 15
    assert result["observed_songs"][0]["song_key"] == "spotify:track:0"
    assert all(entry["familiarity"] == "easy" for entry in result["songs"])


def test_guest_import_does_not_request_decoys():
    spotify = FakeSpotify()

    def unexpected_decoys():
        pytest.fail("Guest admission must not request public decoys")

    assert (
        MusicImporter(
            SpotifyListeningAdapter(spotify), FakeResolver(), unexpected_decoys
        ).import_account("personal-token")["decoys"]
        == []
    )


def test_insufficient_playable_history_has_actual_counts():
    with pytest.raises(DomainError) as error:
        MusicImporter(
            SpotifyListeningAdapter(FakeSpotify(count=9)), FakeResolver(), decoy_tracks
        ).import_account("personal-token")
    assert error.value.code == "insufficient_playable_songs"
    assert error.value.details == {"candidate_count": 9, "playable_count": 9}


def test_provider_failure_is_not_misrepresented_as_insufficient_history():
    with pytest.raises(DomainError) as error:
        MusicImporter(
            SpotifyListeningAdapter(FakeSpotify()),
            FakeResolver(failing=range(6)),
            decoy_tracks,
        ).import_account("personal-token")
    assert error.value.code == "preview_provider_unavailable"


def test_sufficient_history_remains_usable_when_some_candidates_temporarily_fail():
    result = MusicImporter(
        SpotifyListeningAdapter(FakeSpotify()),
        FakeResolver(failing=[1, 2]),
        decoy_tracks,
    ).import_account("personal-token")
    assert len(result["songs"]) == 13
    assert {entry["song_key"] for entry in result["songs"]}.isdisjoint(
        {"spotify:track:1", "spotify:track:2"}
    )
    assert {entry["song_key"] for entry in result["observed_songs"]} >= {
        "spotify:track:1",
        "spotify:track:2",
    }


def test_enabled_decoy_pool_requires_enough_playable_tracks():
    with pytest.raises(DomainError) as error:
        MusicImporter(
            SpotifyListeningAdapter(FakeSpotify()),
            FakeResolver(missing=range(100, 108)),
            decoy_tracks,
        ).import_account("personal-token", True)
    assert error.value.code == "insufficient_decoy_songs"


def test_independent_decoy_provider_excludes_known_recordings_by_isrc():
    catalog = lambda: [
        song(200),
        *[song(index, isrc=f"DECOY{index}") for index in range(100, 110)],
    ]
    result = MusicImporter(
        SpotifyListeningAdapter(FakeSpotify()), FakeResolver(), decoy_provider=catalog
    ).import_account("personal-token", True)
    assert len(result["decoys"]) == 10
    assert all(entry["song_key"] != "spotify:track:200" for entry in result["decoys"])
