"""Import one account outside database transactions; preserve observed ownership."""

from concurrent.futures import ThreadPoolExecutor

from backend.core.errors import DomainError
from backend.music.sources import MusicSource


class MusicImporter:
    def __init__(
        self,
        source: MusicSource,
        resolver,
        decoy_provider,
        *,
        personal_target=24,
        decoy_target=12,
        candidate_limit=60,
        decoy_candidate_limit=30,
        minimum_personal=10,
        minimum_decoys=3,
    ):
        self.source, self.resolver = source, resolver
        self.decoy_provider = decoy_provider
        self.personal_target, self.decoy_target = personal_target, decoy_target
        self.candidate_limit, self.decoy_candidate_limit = (
            candidate_limit,
            decoy_candidate_limit,
        )
        self.minimum_personal, self.minimum_decoys = minimum_personal, minimum_decoys

    def _resolve(self, candidates, target=24):
        songs, errors = [], []
        # Sources already order familiarity strata. Batches retain that
        # order and avoid scheduling all 60 lookups before enough clips exist.
        with ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="music-preview"
        ) as workers:
            for offset in range(0, len(candidates), 4):
                batch = candidates[offset : offset + 4]
                for resolved, error in workers.map(self._resolve_one, batch):
                    if resolved is not None:
                        songs.append(resolved)
                    if error is not None:
                        errors.append(error)
                if len(songs) >= target:
                    break
        return songs, errors

    def _resolve_one(self, song):
        try:
            return self.resolver.resolve(song), None
        except DomainError as error:
            return None, error

    def import_account(self, credential=None, include_decoys=False):
        listening = self.source.read(credential)
        candidates = listening.songs[: self.candidate_limit]
        songs, errors = self._resolve(candidates, target=self.personal_target)
        if len(songs) < self.minimum_personal:
            if errors:
                raise errors[0]
            raise DomainError(
                "insufficient_playable_songs",
                f"Your {self.source.label} listening data has too few playable songs.",
                422,
                {"candidate_count": len(candidates), "playable_count": len(songs)},
            )
        decoys = []
        if include_decoys:
            decoy_candidates = self.decoy_provider()[: self.decoy_candidate_limit]
            personal_keys = {song["song_key"] for song in candidates}
            personal_isrcs = {song["isrc"] for song in candidates if song.get("isrc")}
            decoy_candidates = [
                song
                for song in decoy_candidates
                if song["song_key"] not in personal_keys
                and (not song.get("isrc") or song["isrc"] not in personal_isrcs)
            ]
            decoys, decoy_errors = self._resolve(
                decoy_candidates, target=self.decoy_target
            )
            if len(decoys) < self.minimum_decoys:
                if decoy_errors:
                    raise decoy_errors[0]
                raise DomainError(
                    "insufficient_decoy_songs",
                    "Not enough playable decoy songs are available. Retry later.",
                    503,
                    {"playable_count": len(decoys)},
                )
        return {
            "provider": listening.provider,
            "evidence": listening.evidence,
            "account_id": listening.account_id,
            "songs": songs,
            "observed_songs": candidates,
            "decoys": decoys,
        }
