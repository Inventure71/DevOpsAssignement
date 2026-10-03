#!/usr/bin/env bash
# Start the combined checkout with the existing private provider configuration.
set -euo pipefail

playtest_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$playtest_repo"

if [[ "${1:-}" != "" && "${1:-}" != "--check" ]] || (( $# > 1 )); then
  echo 'Usage: bash tools/run_playtest.sh [--check]' >&2
  exit 2
fi
if [[ ! -x .venv/bin/python || ! -f .env ]]; then
  echo 'Playtesting needs the project .venv and configured local .env.' >&2
  exit 1
fi

set -a
source .env
set +a
export PLAYTEST_MODE=true

.venv/bin/python - <<'PY'
from urllib.parse import urlsplit
from backend.core.config import Config
from backend.music.apple import AppleCatalog

config = Config.from_env()
public = config.public_url.rstrip('/')
address = urlsplit(public)
if address.scheme != 'https' or not address.hostname or address.path or address.query or address.fragment:
    raise SystemExit('Set APP_PUBLIC_URL to the shared HTTPS game origin before device testing.')
if config.spotify_redirect_uri != public + '/api/music/spotify/callback':
    raise SystemExit('SPOTIFY_REDIRECT_URI must use the same shared HTTPS origin and callback path.')
apple = AppleCatalog(config.apple_team_id, config.apple_key_id,
                     config.apple_private_key_path, config.apple_storefront)
if not config.spotify_client_id or not apple.configured:
    raise SystemExit('Complete Spotify and Apple configuration in .env before playtesting.')
if not config.cookie_secure:
    raise SystemExit('Set COOKIE_SECURE=true for the shared HTTPS game.')
print('Open on both devices: ' + public)
print('Two-player playtest enabled; use different nicknames. Local server port: ' + str(config.port))
PY

if [[ "${1:-}" == "--check" ]]; then
  exit 0
fi
exec .venv/bin/python -m backend
