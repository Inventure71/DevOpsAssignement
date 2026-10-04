"""Expose launch policy and installed music availability to admission and HTTP."""

from backend.core.errors import DomainError


class LaunchMode:
    def __init__(self, mode):
        self.mode = mode
        self.demo_available = False

    def available(self, mode):
        if mode == "demo":
            return self.demo_available
        return mode == "normal" and self.mode == "normal"

    def require(self, mode):
        if mode == "demo" and not self.demo_available:
            raise DomainError(
                "mode_unavailable",
                "Demo music is not installed. Run the Demo launcher to prepare "
                "the music, then restart this server.",
                409,
            )
        if mode == "normal" and self.mode != "normal":
            raise DomainError(
                "mode_unavailable",
                "This server is running Demo. Real rooms are unavailable.",
                409,
            )

    def capabilities(self, *, music_configured):
        real = self.mode == "normal" and music_configured
        return {
            "launch_mode": self.mode,
            "modes": {
                "demo": {
                    "enabled": self.demo_available,
                    "reason": None
                    if self.demo_available
                    else "Demo music is not installed on this server.",
                },
                "normal": {
                    "enabled": real,
                    "reason": "Unavailable in this Demo session."
                    if self.mode == "demo"
                    else None
                    if real
                    else "No music connection is configured on this server.",
                },
            },
        }
