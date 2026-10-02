"""Import one account outside database transactions; preserve observed ownership."""

from concurrent.futures import ThreadPoolExecutor

from backend.core.errors import DomainError


class MusicImporter:
    def __init__(self, spotify, resolver, decoy_provider=None):
        self.spotify, self.resolver = spotify, resolver
        self.decoy_provider = decoy_provider or spotify.decoys

    def _resolve(self, candidates):
        songs, errors = [], []
        # executor.map retains provider order (and thus familiarity rank), while
        # the shared resolver independently caps cross-account provider traffic.
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="music-preview") as workers:
            for resolved, error in workers.map(self._resolve_one, candidates):
                if resolved is not None:
                    songs.append(resolved)
                if error is not None:
                    errors.append(error)
        return songs, errors

    def _resolve_one(self, song):
        try:
            return self.resolver.resolve(song), None
        except DomainError as error:
            return None, error

    def import_account(self, token, include_decoys=False):
        account_id = self.spotify.profile(token)
        candidates = self.spotify.listening(token)[:60]
        songs, errors = self._resolve(candidates)
        if len(songs) < 10:
            if errors:
                raise errors[0]
            raise DomainError("insufficient_playable_songs", "Your Spotify history has fewer than ten playable songs.", 422,
                              {"candidate_count": len(candidates), "playable_count": len(songs)})
        decoys = []
        decoy_candidates = []
        decoy_errors = []
        if include_decoys:
            decoy_candidates = self.decoy_provider()[:30]
            personal_keys = {song["song_key"] for song in candidates}
            personal_isrcs = {song["isrc"] for song in candidates if song.get("isrc")}
            decoy_candidates = [song for song in decoy_candidates if song["song_key"] not in personal_keys
                                and (not song.get("isrc") or song["isrc"] not in personal_isrcs)]
            decoys, decoy_errors = self._resolve(decoy_candidates)
            if len(decoys) < 3:
                if decoy_errors:
                    raise decoy_errors[0]
                raise DomainError("insufficient_decoy_songs", "Not enough playable decoy songs are available. Retry later.", 503,
                                  {"playable_count": len(decoys)})
        return {"account_id": account_id, "songs": songs, "observed_songs": candidates, "decoys": decoys,
                "candidate_count": len(candidates), "unavailable_count": len(candidates) - len(songs),
                "provider_error_count": len(errors) + len(decoy_errors),
                "decoy_candidate_count": len(decoy_candidates)}
