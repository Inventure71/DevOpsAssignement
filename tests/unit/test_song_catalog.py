"""Public catalog adapter boundaries and immutable authenticated selections."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.catalog.search import SongSearch
from backend.catalog.tokens import SongTokens
from backend.core.errors import DomainError


SONG = {
    "song_key": "apple:track:42",
    "title": "Billie Jean",
    "artist": "Michael Jackson",
    "artists": [{"artist_key": "apple:artist:7", "name": "Michael Jackson"}],
    "artwork_url": None,
}


def test_shared_cache_coalesces_inflight_queries_and_expires():
    entered, finish = threading.Event(), threading.Event()
    calls, current = [], [10.0]

    def provider(query):
        calls.append(query)
        entered.set()
        assert finish.wait(2)
        return [SONG]

    search = SongSearch(provider, monotonic=lambda: current[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(search.provider_results, "billie jean")
        assert entered.wait(2)
        second = pool.submit(search.provider_results, "billie jean")
        finish.set()
        assert first.result() == ([SONG], False)
        assert second.result() == ([SONG], True)
    assert calls == ["billie jean"]
    current[0] += 301
    assert search.provider_results("billie jean") == ([SONG], False)
    assert len(calls) == 2


def test_provider_failure_is_cached_briefly_then_retried():
    calls, current = [], [10.0]

    def failing(query):
        calls.append(query)
        raise DomainError("song_search_unavailable", "Offline", 503)

    search = SongSearch(failing, monotonic=lambda: current[0])
    for _ in range(2):
        with pytest.raises(DomainError):
            search.provider_results("billie jean")
    assert len(calls) == 1
    current[0] += 11
    with pytest.raises(DomainError):
        search.provider_results("billie jean")
    assert len(calls) == 2


def test_external_budget_is_global_and_cached_queries_still_work():
    current = [10.0]
    search = SongSearch(lambda query: [SONG], monotonic=lambda: current[0])
    for number in range(18):
        search.provider_results(str(number))
    with pytest.raises(DomainError) as error:
        search.provider_results("nineteen")
    assert error.value.code == "song_search_busy"
    assert search.provider_results("0") == ([SONG], True)
    current[0] += 61
    assert search.provider_results("nineteen") == ([SONG], False)


def test_selection_signature_room_scope_and_process_secret():
    tokens = SongTokens(secret=b"a" * 32)
    token = tokens.issue("room-one", SONG, 100)
    assert tokens.decode(token, "room-one") == (SONG, 100 + 20 * 60_000)
    for value, room, codec in [
        (token, "room-two", tokens),
        (token[:-1] + "x", "room-one", tokens),
        ("not-a-token", "room-one", tokens),
        (token, "room-one", SongTokens()),
    ]:
        with pytest.raises(DomainError) as error:
            codec.decode(value, room)
        assert error.value.code == "invalid_song_selection"
