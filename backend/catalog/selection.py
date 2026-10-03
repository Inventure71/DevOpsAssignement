"""Resolve signed bulk metadata before selection; answer submission stays offline."""

from backend.catalog.identity import normalized_words, recording_title
from backend.core.errors import DomainError
from backend.music.media import matches_recording


class CatalogSelections:
    def __init__(self, search):
        self.search = search

    def resolve(self, room_id, token, now):
        song, expires = self.search.tokens.decode(token, room_id)
        if expires < now:
            raise DomainError('song_selection_expired', 'Search again to select this song.')
        if not song.get('_catalog_reference'):
            return self.search.result(room_id, song, now)
        store, scope = self.search.store, self.search.provider_scope
        verified = store.links.find(scope, 'guess', song) if store else []
        if not verified:
            query = song['title'] + ' ' + song['artist']
            candidates, _ = self.search._remote(normalized_words(query), query.casefold())
            matches = [candidate for candidate in candidates if matches_recording(song, candidate)]
            # Guess scoring already equates the same version-aware title and
            # structured artist IDs. Regional editions may have different ISRCs;
            # this never relaxes the stricter audio-preview recording policy.
            identities = {(recording_title(candidate['title']),
                           tuple(sorted(credit['artist_key'] for credit in candidate['artists'])))
                          for candidate in matches}
            if not matches:
                raise DomainError('song_selection_unavailable',
                                  'This recording could not be matched. Try another result.', 503)
            if len(identities) != 1:
                raise DomainError('song_selection_ambiguous',
                                  'Several recordings match this result. Choose the correct recording.', 409,
                                  {'alternatives': [self.search.result(room_id, candidate, now) for candidate in matches[:20]]})
            if store:
                for candidate in matches:
                    store.links.save(scope, 'guess', song, candidate, self.search.clock())
            verified = matches
        return self.search.result(room_id, verified[0], now)
