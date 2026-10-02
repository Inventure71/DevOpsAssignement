"""Environment configuration for the single-process application."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path("data")
    port: int = 8000
    cookie_secure: bool = False
    setup_timeout_ms: int = 60_000
    spotify_client_id: str = ''
    spotify_client_secret: str = field(default='', repr=False)
    spotify_redirect_uri: str = 'http://127.0.0.1:8000/api/music/spotify/callback'
    apple_team_id: str = ''
    apple_key_id: str = ''
    apple_private_key_path: str = ''
    apple_storefront: str = 'es'

    @property
    def database_path(self) -> Path:
        return self.data_dir / "whos_on_repeat.sqlite3"

    @classmethod
    def from_env(cls) -> "Config":
        port = int(os.environ.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        secure = os.environ.get("COOKIE_SECURE", "false").lower()
        if secure not in {"true", "false", "1", "0"}:
            raise ValueError("COOKIE_SECURE must be true or false")
        setup_timeout = int(os.environ.get("SETUP_TIMEOUT_MS", "60000"))
        if not 10_000 <= setup_timeout <= 120_000:
            raise ValueError("SETUP_TIMEOUT_MS must be between 10000 and 120000")
        return cls(Path(os.environ.get("DATA_DIR", "data")), port, secure in {"true", "1"}, setup_timeout,
                   os.environ.get('SPOTIFY_CLIENT_ID', ''), os.environ.get('SPOTIFY_CLIENT_SECRET', ''),
                   os.environ.get('SPOTIFY_REDIRECT_URI', f'http://127.0.0.1:{port}/api/music/spotify/callback'),
                   os.environ.get('APPLE_TEAM_ID', ''), os.environ.get('APPLE_KEY_ID', ''),
                   os.environ.get('APPLE_PRIVATE_KEY_PATH', ''), os.environ.get('APPLE_STOREFRONT', 'es'))
