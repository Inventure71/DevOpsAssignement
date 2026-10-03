"""Shared metadata search cache, signed selections and local request budget.

The no-credentials Demo fallback uses public iTunes metadata (~20 requests/minute):
https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html
Normal mode injects the developer catalog adapter instead. Only answer metadata
is signed; listening evidence and playback URLs do not enter search responses.
"""
import json
import threading
import time
from collections import OrderedDict, deque
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.catalog.tokens import SongTokens
from backend.catalog.identity import normalized_words
from backend.catalog.store import public_song
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
    def __init__(self, provider=apple_search, monotonic=time.monotonic, tokens=None, *, provider_name='apple', calls_per_minute=18, store=None, provider_scope=None, clock=time.time):
        self.provider, self.monotonic = provider, monotonic
        self.tokens = tokens or SongTokens()
        self.provider_name, self.calls_per_minute = provider_name, calls_per_minute
        self.store, self.clock = store, clock
        self.provider_scope = provider_scope or provider_name
        self.cache = OrderedDict()
        self.calls = deque()
        self.lock = threading.Lock()
        self.inflight = {}

    def _remote(self, query, provider_query=None):
        if self.store:
            persisted = self.store.query(self.provider_scope, query, self.clock())
            if persisted is not None:
                return persisted, True
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
                if len(self.calls) >= self.calls_per_minute:
                    raise DomainError('song_search_busy', 'Song search is busy. Try again in a minute.', 429,
                                      {'retry_after_seconds': 60})
                self.calls.append(now)
                self.inflight[query] = threading.Event()
        if waiting is not None:
            if not waiting.wait(timeout=10):
                raise DomainError('song_search_unavailable', 'Song search is taking too long. Try again shortly.', 503)
            return self._remote(query, provider_query)
        try:
            raw = self.provider(provider_query or query)
            if not isinstance(raw, list):
                raise DomainError('song_search_unavailable', 'Song search returned invalid results.', 503)
            songs = [entry for song in raw[:20] if (entry := public_song(song))]
            if self.store:
                songs = self.store.save_query(self.provider_scope, query, songs, self.clock())
            with self.lock:
                self.cache[query] = (self.monotonic() + (300 if songs else 60), songs)
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

    def search(self, conn, room_id, query, now, *, local_first=False):
        query = ' '.join(query.split())
        if not 2 <= len(query) <= 100:
            raise DomainError('invalid_song_query', 'Enter between 2 and 100 characters.')
        terms = normalized_words(query).split()
        if not terms:
            raise DomainError('invalid_song_query', 'Enter a song or artist name.')
        local = []
        # Shared fixtures only: no membership, familiarity or room-specific pool filtering.
        room = conn.execute('SELECT mode FROM rooms WHERE id=?', (room_id,)).fetchone()
        fixtures = [] if room and room['mode'] == 'normal' else conn.execute('SELECT id,title,artist,artists_json,artwork_url FROM demo_catalog ORDER BY title,id')
        for row in fixtures:
            text = normalized_words(row['title'] + ' ' + row['artist'])
            if all(term in text for term in terms):
                local.append({'song_key': 'demo:' + row['id'], 'title': row['title'], 'artist': row['artist'],
                              'artists': json.loads(row['artists_json']), 'artwork_url': row['artwork_url']})
                if len(local) == 20:
                    break
        if local:
            songs, source, cached = local, 'catalog', False
        elif local_first and self.store and (bulk := self.store.search(query, scope=self.provider_scope, now=self.clock())):
            # Public bulk metadata is searchable without upstream traffic. A signed
            # reference requires explicit resolution before it can become a guess.
            return {'songs': [self.result(room_id, song, now, reference=song['song_key'].startswith('musicbrainz:'))
                              for song in bulk], 'source': 'catalog', 'cached': True}
        else:
            indexed = self.store.search(query, selectable=True, scope=self.provider_scope, now=self.clock()) if self.store else []
            complete = self.store.query(self.provider_scope, normalized_words(query), self.clock()) if self.store else None
            # Prefix hits never establish coverage: cached 'track10'...'track19'
            # must not hide an uncached exact 'track1' recording.
            exact_title = any(normalized_words(song['title']) == normalized_words(query)
                              for song in indexed)
            if complete is not None:
                covered_keys = {song['song_key'] for song in complete}
                songs = (complete + [song for song in indexed if song['song_key'] not in covered_keys])[:20]
                source, cached = 'catalog', True
            elif exact_title:
                songs, source, cached = indexed, 'catalog', True
            else:
                try:
                    remote, cached = self._remote(normalized_words(query), query.casefold())
                    songs = remote + [song for song in indexed if song['song_key'] not in
                                      {entry['song_key'] for entry in remote}]
                    songs, source = songs[:20], self.provider_name
                except DomainError:
                    if not indexed:
                        raise
                    songs, source, cached = indexed, 'catalog', True
        songs = [{key: value for key, value in song.items()
                  if key in {'song_key', 'title', 'artist', 'artists', 'isrc', 'artwork_url'}} for song in songs]
        return {'songs': [self.result(room_id, song, now) for song in songs],
                'source': source, 'cached': cached}

    def result(self, room_id, song, now, *, reference=False):
        metadata = public_song(song)
        if metadata is None:
            raise DomainError('song_search_unavailable', 'Song search returned invalid metadata.', 503)
        if reference:
            metadata['_catalog_reference'] = True
        result = {key: metadata[key] for key in ('title', 'artist', 'artwork_url')}
        result['token'] = self.tokens.issue(room_id, metadata, now)
        if reference:
            result['resolve_required'] = True
        return result
