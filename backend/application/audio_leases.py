"""Transient ownership of the one host audio tab; credentials stay server-side."""

import secrets

from backend.core.errors import DomainError


class AudioLeases:
    def __init__(self):
        self._leases = {}

    def claim(self, room_id, tab_id, takeover, now):
        old = self._leases.get(room_id)
        if old and old["tab_id"] == tab_id:
            old["seen_at_ms"] = now
            return old["lease_id"], False
        if old and now < old["seen_at_ms"] + 15_000 and not takeover:
            raise DomainError(
                "audio_controller_busy",
                "Another host tab controls audio. Take over explicitly to move it here.",
                409,
            )
        lease = {
            "lease_id": secrets.token_urlsafe(24),
            "tab_id": tab_id,
            "seen_at_ms": now,
        }
        self._leases[room_id] = lease
        return lease["lease_id"], old is not None

    def require(self, room_id, lease_id, now):
        lease = self._leases.get(room_id)
        if (
            not lease
            or lease["lease_id"] != lease_id
            or now >= lease["seen_at_ms"] + 15_000
        ):
            raise DomainError(
                "audio_controller_required", "Enable audio on the active host tab.", 409
            )

    def delete(self, room_id):
        self._leases.pop(room_id, None)

    def active_id(self, room_id, now):
        lease = self._leases.get(room_id)
        if lease and now < lease["seen_at_ms"] + 15_000:
            return lease["lease_id"]
        return None
