#!/usr/bin/env bash
# Local checks only: no CI, deployment, provider credentials, or live data.
set -euo pipefail
verification_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$verification_repo"
verification_python="${PYTHON:-.venv/bin/python}"
"$verification_python" -m pytest -q tests/unit \
  --cov=backend.rooms.service --cov=backend.game.service \
  --cov=backend.game.scoring --cov=backend.game.selection \
  --cov-report=term-missing --cov-fail-under=70
"$verification_python" -m pytest -q tests/integration
node --test tests/frontend/*.test.mjs
