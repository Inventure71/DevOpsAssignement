"""Reuse verified recording identities while media references renew separately."""

from backend.catalog.store import public_song
from backend.music.media import matches_recording


class Recordings:
    def __init__(self, provider, links, scope, clock):
        self.provider, self.links = provider, links
        self.scope, self.clock = scope, clock

    @staticmethod
    def _isrc(song):
        return song | {'song_key': 'isrc:' + song['isrc'].strip().upper()}

    @staticmethod
    def compatible(song, target):
        target = public_song(target)
        if target is None or not matches_recording(song, target):
            return None
        if song.get('isrc') and target.get('isrc') and song['isrc'].upper() != target['isrc'].upper():
            return None
        return target

    def remember(self, song, target):
        """Only directly checked identities become durable catalog edges."""
        target = self.compatible(song, target)
        if target is None:
            return None
        if self.links:
            now = self.clock()
            self.links.save(self.scope, 'recording', song, target, now)
            if song.get('isrc') and target.get('isrc') == song['isrc'].upper():
                identifier = self._isrc(song)
                self.links.save(self.scope, 'recording', identifier, target, now)
                self.links.save(self.scope, 'recording', song, identifier, now)
        return target

    def _known(self, song):
        if not self.links:
            return []
        candidates = self.links.find(self.scope, 'recording', song)
        if song.get('isrc'):
            candidates += self.links.find(self.scope, 'recording', self._isrc(song))
        seen = set()
        targets = []
        for candidate in candidates:
            key = candidate['song_key']
            if key.startswith('apple:track:') and key not in seen:
                seen.add(key)
                targets.append(candidate)
        return targets

    def _reject(self, song, target_key):
        self.links.reject(self.scope, 'recording', song, target_key)
        if song.get('isrc'):
            self.links.reject(self.scope, 'recording', self._isrc(song), target_key)

    def resolve(self, song):
        resolve_verified = getattr(self.provider, 'resolve_verified', None)
        if resolve_verified is None:
            return self.provider.resolve(song)
        last_target = None

        def verified(candidate):
            nonlocal last_target
            last_target = self.remember(song, candidate)

        def attach(result):
            if result is not None and last_target is not None:
                return result | {'_catalog_song': last_target}
            return result

        refresh = getattr(self.provider, 'refresh', None)
        if refresh:
            unavailable = False
            for candidate in self._known(song)[:3]:
                last_target = None
                result = refresh(song, candidate, on_verified=verified,
                                 on_invalid=lambda key: self._reject(song, key))
                if result is not None:
                    return attach(result)
                unavailable = unavailable or last_target is not None
            if unavailable:
                return None  # A known recording's media failure isn't an identity miss.
        return attach(resolve_verified(song, on_verified=verified))
