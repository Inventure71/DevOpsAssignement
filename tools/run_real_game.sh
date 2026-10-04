#!/usr/bin/env bash
# macOS/Linux convenience wrapper. Windows: py -3 tools/launch_game.py real
set -euo pipefail
real_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for real_python in "$real_repo/.venv/bin/python" python3 python3.14 python3.13 python3.12 python; do
  if command -v "$real_python" >/dev/null 2>&1 && "$real_python" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' 2>/dev/null; then
    exec "$real_python" "$real_repo/tools/launch_game.py" real "$@"
  fi
done
echo 'Python 3.12 or newer is required. Install Python, then rerun this script.' >&2
exit 1
