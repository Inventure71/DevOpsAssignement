#!/usr/bin/env bash
# macOS/Linux convenience wrapper. Windows: py -3 tools/launch_game.py demo
set -euo pipefail
demo_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for demo_python in "$demo_repo/.venv/bin/python" python3 python3.14 python3.13 python3.12 python; do
  if command -v "$demo_python" >/dev/null 2>&1 && "$demo_python" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' 2>/dev/null; then
    exec "$demo_python" "$demo_repo/tools/launch_game.py" demo "$@"
  fi
done
echo 'Python 3.12 or newer is required. Install Python, then rerun this script.' >&2
exit 1
