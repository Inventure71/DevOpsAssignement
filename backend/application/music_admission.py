"""Atomically deliver a verified import into Rooms, with a live receipt guard."""
from backend.core.errors import DomainError


class MusicAdmissionHandler:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __call__(self, payload, imported, valid):
        c = self.coordinator
        room_id = payload.get('room_id')

        def persist(conn, now):
            self._require_valid(valid)
            result = (c.rooms.join(conn, room_id, payload['nickname'], payload['character_id'], now, imported=imported)
                      if room_id else c.rooms.create(conn, payload['nickname'], payload['character_id'],
                                                     'normal', now, imported=imported))
            self._require_valid(valid)
            return result

        if room_id:
            with c.room_lock(room_id):
                return c.admission(persist)
        return c.admission(persist)

    @staticmethod
    def _require_valid(valid):
        if not valid():
            raise DomainError('music_admission_expired', 'Spotify sign-in expired. Start again.', 401)
