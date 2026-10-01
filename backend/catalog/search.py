"""Bounded public Apple metadata search, shared cache and global request budget.

Apple documents its public search endpoint and approximately 20 requests/minute:
https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html
Only metadata is read. This adapter never obtains or plays preview audio.
"""
import json
import threading
import time
from collections import OrderedDict, deque
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.catalog.tokens import SongTokens
from backend.core.errors import DomainError


def apple_search(query):
    url = 'https://itunes.apple.com/search?' + urlencode({'term': query, 'media': 'music',
                                                       'entity': 'song', 'limit': 20, 'country': 'US'})
    try:
        with urlopen(Request(url, headers={'User-Agent': 'WhosOnRepeat/1.0'}), timeout=4) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError('Provider response too large')
        result = json.loads(body)
        rows = result['results']
        if not isinstance(rows, list):
            raise ValueError('Invalid provider response')
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
        raise DomainError('song_search_unavailable', 'Song search is unavailable. Try again shortly.', 503) from exc
    songs = []
    for row in rows[:20]:
        if not isinstance(row, dict) or row.get('kind') != 'song':
            continue
        if not all(row.get(key) for key in ('trackId', 'artistId', 'trackName', 'artistName')):
            continue
        artwork = row.get('artworkUrl100')
        songs.append({'song_key': 'apple:track:' + str(row['trackId']), 'title': str(row['trackName'])[:300],
                      'artist': str(row['artistName'])[:300],
                      'artists': [{'artist_key': 'apple:artist:' + str(row['artistId']), 'name': str(row['artistName'])[:300]}],
                      'artwork_url': artwork if isinstance(artwork, str) and artwork.startswith('https://') else None})
    return songs


class SongSearch:
    def __init__(self, provider=apple_search, monotonic=time.monotonic, tokens=None):
        self.provider, self.monotonic = provider, monotonic
        self.tokens = tokens or SongTokens()
        self.cache = OrderedDict()
        self.calls = deque()
        self.lock = threading.Lock()
        self.inflight = {}

    def _remote(self, query):
        with self.lock:
            now = self.monotonic()
            cached = self.cache.get(query)
            if cached and cached[0] > now:
                self.cache.move_to_end(query)
                if isinstance(cached[1], DomainError):
                    raise cached[1]
                return cached[1], True
            waiting = self.inflight.get(query)
            if waiting is None:
                while self.calls and self.calls[0] <= now - 60:
                    self.calls.popleft()
                if len(self.calls) >= 18:
                    raise DomainError('song_search_busy', 'Song search is busy. Try again in a minute.', 429,
                                      {'retry_after_seconds': 60})
                self.calls.append(now)
                self.inflight[query] = threading.Event()
        if waiting is not None:
            if not waiting.wait(timeout=5):
                raise DomainError('song_search_unavailable', 'Song search is taking too long. Try again shortly.', 503)
            return self._remote(query)
        try:
            songs = self.provider(query)
            with self.lock:
                self.cache[query] = (self.monotonic() + 300, songs)
                self._trim()
            return songs, False
        except DomainError as exc:
            with self.lock:
                self.cache[query] = (self.monotonic() + 10, exc)
                self._trim()
            raise
        finally:
            with self.lock:
                self.inflight.pop(query).set()

    def _trim(self):
        while len(self.cache) > 128:
            self.cache.popitem(last=False)

    def search(self, conn, room_id, query, now):
        query = ' '.join(query.split())
        if not 2 <= len(query) <= 100:
            raise DomainError('invalid_song_query', 'Enter between 2 and 100 characters.')
        terms = query.casefold().split()
        local = []
        # Shared fixtures only: no membership, familiarity or room-specific pool filtering.
        for row in conn.execute('SELECT id,title,artist,artists_json,artwork_url FROM demo_catalog ORDER BY title,id'):
            text = (row['title'] + ' ' + row['artist']).casefold()
            if all(term in text for term in terms):
                local.append({'song_key': 'demo:' + row['id'], 'title': row['title'], 'artist': row['artist'],
                              'artists': json.loads(row['artists_json']), 'artwork_url': row['artwork_url']})
                if len(local) == 20:
                    break
        if local:
            songs, source, cached = local, 'catalog', False
        else:
            songs, cached = self._remote(query.casefold())
            source = 'apple'
        return {'songs': [{k: song[k] for k in ('title', 'artist', 'artwork_url')} |
                          {'token': self.tokens.issue(room_id, song, now)} for song in songs],
                'source': source, 'cached': cached}
