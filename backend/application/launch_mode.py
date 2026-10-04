"""Gate Spotify behind real-game launch; Demo is always available."""

from backend.core.errors import DomainError


class LaunchMode:
    def __init__(self, mode):
        self.mode = mode

    def require(self, mode):
        if mode == "normal" and self.mode != "normal":
            raise DomainError(
                "mode_unavailable",
                "This server is running Demo. Spotify rooms are unavailable.",
                409,
            )

    def capabilities(self, *, music_configured):
        spotify = self.mode == "normal" and music_configured
        return {
            "launch_mode": self.mode,
            "modes": {
                "demo": {
                    "enabled": True,
                    "reason": None,
                },
                "normal": {
                    "enabled": spotify,
                    "reason": "Unavailable in this Demo session."
                    if self.mode == "demo"
                    else None
                    if spotify
                    else "Spotify is not configured on this server.",
                },
            },
        }
