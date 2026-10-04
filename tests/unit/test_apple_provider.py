"""Developer authentication, full metadata and conservative cross-catalog matching."""

import pytest

from backend.core.errors import DomainError
from backend.music.apple import AppleCatalog, normalize_song
from backend.music.http import ProviderHttpError
from backend.music.previews import PreviewResolver


def catalog_song(title="Stronger", **attributes):
    return {
        "id": "123",
        "type": "songs",
        "attributes": {
            "name": title,
            "artistName": "Kanye West",
            "isrc": "USUM70741277",
            "artwork": {"url": "https://is1-ssl.mzstatic.com/image/{w}x{h}bb.jpg"},
            "previews": [{"url": "https://audio-ssl.itunes.apple.com/sample.m4a"}],
            **attributes,
        },
        "relationships": {
            "artists": {
                "data": [
                    {"id": "kanye", "attributes": {"name": "Kanye West"}},
                    {"id": "guest", "attributes": {"name": "Guest"}},
                ]
            }
        },
    }


def spotify_song():
    return {
        "song_key": "spotify:track:original",
        "title": "Stronger",
        "artist": "Kanye West",
        "artists": [{"artist_key": "spotify:artist:kanye", "name": "Kanye West"}],
        "isrc": "USUM70741277",
        "familiarity": "hard",
        "artwork_url": None,
    }


class Transport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, headers=None, data=None):
        self.calls.append((method, url, headers))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def client(responses):
    transport = Transport(responses)
    apple = AppleCatalog(
        "team", "key", None, transport=transport, probe=lambda url: True
    )
    apple._developer_token = lambda: "developer-token"
    return apple, transport


def test_catalog_metadata_retains_full_relationship_credits_and_formats_artwork():
    result = normalize_song(catalog_song())
    assert result["song_key"] == "apple:track:123"
    assert result["artists"] == [
        {"artist_key": "apple:artist:kanye", "name": "Kanye West"},
        {"artist_key": "apple:artist:guest", "name": "Guest"},
    ]
    assert result["artwork_url"] == "https://is1-ssl.mzstatic.com/image/300x300bb.jpg"


def test_isrc_lookup_and_cached_media_preserve_spotify_facts_and_artist_aliases():
    apple, transport = client([{"data": [catalog_song()]}])
    resolver = PreviewResolver(apple)
    original = spotify_song()
    result = resolver.resolve(original)
    assert result["song_key"] == original["song_key"]
    assert result["artists"] == [
        original["artists"][0] | {"aliases": ["apple:artist:kanye"]}
    ]
    assert result["familiarity"] == "hard"
    assert result["preview_url"] == "https://audio-ssl.itunes.apple.com/sample.m4a"
    assert "filter%5Bisrc%5D=USUM70741277" in transport.calls[0][1]
    assert transport.calls[0][2] == {"Authorization": "Bearer developer-token"}
    assert "preview_url" not in original
    cached = resolver.resolve(original | {"familiarity": "easy"})
    assert cached["artists"] == result["artists"]
    assert cached["familiarity"] == "easy" and result["familiarity"] == "hard"
    assert len(transport.calls) == 1


def test_instrumental_with_same_isrc_is_rejected_before_search_fallback():
    apple, transport = client(
        [
            {"data": [catalog_song("Stronger - Instrumental")]},
            {"results": {"songs": {"data": [catalog_song()]}}},
        ]
    )
    assert apple.resolve_verified(spotify_song())["preview_url"]
    assert len(transport.calls) == 2 and "/search?" in transport.calls[1][1]


def test_wrong_recording_with_matching_title_is_rejected():
    apple, _ = client(
        [
            {"data": [catalog_song(isrc="OTHER")]},
            {"results": {"songs": {"data": [catalog_song("Stronger (Live)")]}}},
        ]
    )
    assert apple.resolve_verified(spotify_song()) is None


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "apple_authorization_failed"),
        (403, "apple_authorization_failed"),
        (429, "apple_rate_limited"),
        (500, "apple_unavailable"),
    ],
)
def test_catalog_errors_do_not_silently_switch_to_public_providers(status, code):
    apple, _ = client([ProviderHttpError(status, retry_after=17)])
    resolver = PreviewResolver(apple=apple)
    with pytest.raises(DomainError) as error:
        resolver.resolve(spotify_song())
    assert error.value.code == code
    if status == 429:
        assert error.value.details["retry_after_seconds"] == 17


def test_missing_configuration_fails_before_network():
    apple = AppleCatalog(None, None, None, transport=Transport([]))
    assert not apple.configured
    with pytest.raises(DomainError) as error:
        apple.search("Stronger")
    assert error.value.code == "apple_not_configured"


def test_rate_limit_cools_down_all_catalog_operations_without_sleeping():
    apple, transport = client(
        [ProviderHttpError(429, retry_after=17), {"results": {"songs": {"data": []}}}]
    )
    now = [100]
    apple.clock = lambda: now[0]
    with pytest.raises(DomainError) as error:
        apple.search("First query")
    assert error.value.details["retry_after_seconds"] == 17
    for operation in (
        lambda: apple.search("Different query"),
        apple.decoys,
        lambda: apple.resolve_verified(spotify_song()),
    ):
        with pytest.raises(DomainError) as retry:
            operation()
        assert retry.value.code == "apple_rate_limited"
    assert len(transport.calls) == 1
    now[0] += 18
    assert apple.search("Retry after deadline") == []
    assert len(transport.calls) == 2


def test_no_isrc_uses_metadata_search():
    apple, transport = client([{"results": {"songs": {"data": [catalog_song()]}}}])
    assert apple.resolve_verified(spotify_song() | {"isrc": None})["preview_url"]
    assert "/search?" in transport.calls[0][1]


def test_charts_are_independent_decoys_with_bounded_deduplication():
    apple, transport = client(
        [{"results": {"songs": [{"data": [catalog_song(), catalog_song()]}]}}]
    )
    result = apple.decoys()
    assert len(result) == 1 and result[0]["song_key"] == "apple:track:123"
    assert "/charts?" in transport.calls[0][1]


def test_chart_preview_is_probed_without_repeat_catalog_lookup():
    apple, transport = client([])
    original = normalize_song(catalog_song())
    assert apple.resolve_verified(original) == original
    assert transport.calls == []


def test_developer_token_is_signed_es256_cached_and_refreshed(tmp_path):
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "AuthKey.p8"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    now = [1_800_000_000]
    apple = AppleCatalog("TEAM123456", "KEY1234567", key_path, clock=lambda: now[0])
    assert apple.configured
    token = apple._developer_token()
    claims = jwt.decode(
        token,
        private_key.public_key(),
        algorithms=["ES256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims == {"iss": "TEAM123456", "iat": now[0], "exp": now[0] + 3600}
    assert jwt.get_unverified_header(token)["kid"] == "KEY1234567"
    assert apple._developer_token() == token
    now[0] += 3541
    assert apple._developer_token() != token


def test_invalid_signing_key_is_a_safe_configuration_error(tmp_path):
    key_path = tmp_path / "secret-path.p8"
    key_path.write_text("SECRET_INVALID_KEY")
    with pytest.raises(DomainError) as error:
        AppleCatalog("team", "key", key_path).search("Song")
    assert error.value.code == "apple_invalid_configuration"
    assert (
        "SECRET" not in error.value.message and str(key_path) not in error.value.message
    )
