"""Public catalog adapter boundaries and immutable authenticated selections."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest

from backend.catalog.search import SongSearch, apple_search
from backend.catalog.tokens import SongTokens
from backend.core.errors import DomainError


SONG = {'song_key': 'apple:track:42', 'title': 'Billie Jean', 'artist': 'Michael Jackson',
        'artists': [{'artist_key': 'apple:artist:7', 'name': 'Michael Jackson'}], 'artwork_url': None}


def test_apple_adapter_encodes_query_and_normalizes_structured_ids(monkeypatch):
    seen = []
    def open_request(request, timeout):
        seen.append((request.full_url, timeout))
        return BytesIO(json.dumps({'results': [{'kind': 'song', 'trackId': 42, 'artistId': 7,
            'trackName': 'Billie Jean', 'artistName': 'Michael Jackson', 'previewUrl': 'hidden'},
            {'kind': 'music-video', 'trackId': 9}, {'kind': 'song', 'artistName': 'Missing ID'}]}).encode())
    monkeypatch.setattr('backend.catalog.search.urlopen', open_request)
    assert apple_search('Billie & Jean') == [SONG]
    assert 'term=Billie+%26+Jean' in seen[0][0]
    assert 'entity=song' in seen[0][0] and seen[0][1] == 4


@pytest.mark.parametrize('body', [b'not json', b'[]', b'{"results":null}', b'x' * 1_000_001])
def test_invalid_provider_response_is_explicit_failure(monkeypatch, body):
    monkeypatch.setattr('backend.catalog.search.urlopen', lambda *args, **kwargs: BytesIO(body))
    with pytest.raises(DomainError) as error:
        apple_search('query')
    assert error.value.code == 'song_search_unavailable'


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
        first = pool.submit(search._remote, 'billie jean')
        assert entered.wait(2)
        second = pool.submit(search._remote, 'billie jean')
        finish.set()
        assert first.result() == ([SONG], False)
        assert second.result() == ([SONG], True)
    assert calls == ['billie jean']
    current[0] += 301
    assert search._remote('billie jean') == ([SONG], False)
    assert len(calls) == 2


def test_provider_failure_is_cached_briefly_then_retried():
    calls, current = [], [10.0]
    def failing(query):
        calls.append(query)
        raise DomainError('song_search_unavailable', 'Offline', 503)
    search = SongSearch(failing, monotonic=lambda: current[0])
    for _ in range(2):
        with pytest.raises(DomainError):
            search._remote('billie jean')
    assert len(calls) == 1
    current[0] += 11
    with pytest.raises(DomainError):
        search._remote('billie jean')
    assert len(calls) == 2


def test_external_budget_is_global_and_cached_queries_still_work():
    current = [10.0]
    search = SongSearch(lambda query: [SONG], monotonic=lambda: current[0])
    for number in range(18):
        search._remote(str(number))
    with pytest.raises(DomainError) as error:
        search._remote('nineteen')
    assert error.value.code == 'song_search_busy'
    assert search._remote('0') == ([SONG], True)
    current[0] += 61
    assert search._remote('nineteen') == ([SONG], False)


def test_selection_signature_room_scope_and_process_secret():
    tokens = SongTokens(secret=b'a' * 32)
    token = tokens.issue('room-one', SONG, 100)
    assert tokens.decode(token, 'room-one') == (SONG, 100 + 20 * 60_000)
    for value, room, codec in [(token, 'room-two', tokens), (token[:-1] + 'x', 'room-one', tokens),
                               ('not-a-token', 'room-one', tokens), (token, 'room-one', SongTokens())]:
        with pytest.raises(DomainError) as error:
            codec.decode(value, room)
        assert error.value.code == 'invalid_song_selection'
