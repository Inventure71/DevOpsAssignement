"""Provider authorization translates browser responses into short-lived credentials."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from backend.core.errors import DomainError


class AuthorizationFlow(Protocol):
    def configuration(self, origin: str) -> dict: ...

    def begin(self, origin: str) -> tuple[dict, Any]: ...

    def validate(self, context: Any, response: dict) -> None: ...

    def finish(self, context: Any, response: dict) -> str: ...


@dataclass(frozen=True, repr=False)
class _SpotifyAttempt:
    state: str
    verifier: str


class SpotifyAuthorization:
    """Spotify PKCE state, redirect validation and token exchange."""

    def __init__(self, client, redirect_uri, local_only):
        self.client = client
        self.callback = urlsplit(redirect_uri)
        self.local_only = local_only

    def configuration(self, origin):
        return {
            "application_url": f"{self.callback.scheme}://{self.callback.netloc}/",
            "requires_shared_url": self.local_only(self.callback.hostname)
            and not self.local_only(urlsplit(origin).hostname),
        }

    def begin(self, origin):
        details = self.configuration(origin)
        if self.callback.path != "/api/music/spotify/callback":
            raise DomainError(
                "music_callback_misconfigured",
                "The configured Spotify callback must end in /api/music/spotify/callback.",
                503,
            )
        if details["requires_shared_url"]:
            raise DomainError(
                "music_shared_url_required",
                "Spotify is configured for the server computer only. The host must finish network setup before other devices can sign in.",
                503,
            )
        if origin.rstrip("/") != details["application_url"].rstrip("/"):
            raise DomainError(
                "music_origin_mismatch",
                "Open the configured game address before Spotify sign-in.",
                409,
                {"application_url": details["application_url"]},
            )
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return {
            "kind": "redirect",
            "url": self.client.authorization_url(state, challenge),
        }, _SpotifyAttempt(state, verifier)

    def validate(self, context, response):
        state = response.get("state")
        if not isinstance(state, str) or not secrets.compare_digest(
            context.state, state
        ):
            raise DomainError(
                "invalid_music_state",
                "This Spotify sign-in could not be verified. Start again.",
                400,
            )
        if response.get("error") or not response.get("code"):
            raise DomainError(
                "music_authorization_denied",
                "Spotify sign-in was cancelled or refused.",
                400,
            )

    def finish(self, context, response):
        return self.client.exchange_code(response["code"], context.verifier)
