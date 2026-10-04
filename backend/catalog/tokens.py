"""Room-scoped, authenticated metadata selections; no provider call on submission."""

import base64
import hashlib
import hmac
import json
import secrets

from backend.core.errors import DomainError


class SongTokens:
    def __init__(self, secret=None, lifetime_ms=20 * 60_000):
        self.secret = secret or secrets.token_bytes(32)
        self.lifetime_ms = lifetime_ms

    def issue(self, room_id, song, now):
        value = json.dumps(
            {"room": room_id, "expires": now + self.lifetime_ms, "song": song},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        body = base64.urlsafe_b64encode(value).decode().rstrip("=")
        signature = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return body + "." + signature

    def decode(self, token, room_id):
        """Verify authenticity. The game checks expiry after its idempotency receipt."""
        try:
            body, signature = token.split(".")
            expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            value = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if value["room"] != room_id:
                raise ValueError("room")
            return value["song"], value["expires"]
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise DomainError(
                "invalid_song_selection", "Choose a song from the search results."
            ) from exc
