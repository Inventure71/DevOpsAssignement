#!/usr/bin/env bash
# Run unit coverage, integration and frontend checks.
set -euo pipefail
verification_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$verification_repo"
verification_python="${PYTHON:-.venv/bin/python}"
"$verification_python" -m pytest -q tests/unit \
  --cov=backend.rooms.service --cov=backend.game.service \
  --cov=backend.game.scoring --cov=backend.game.selection \
  --cov=backend.game.preparation --cov=backend.game.song_titles \
  --cov-report=term-missing --cov-fail-under=90
# Enforce the target in each domain; a stronger domain cannot hide a weaker one.
"$verification_python" -m coverage report \
  --include=backend/rooms/service.py --fail-under=90
"$verification_python" -m coverage report \
  --include='backend/game/service.py,backend/game/scoring.py,backend/game/selection.py,backend/game/preparation.py,backend/game/song_titles.py' \
  --fail-under=90
# Preparation is small and critical: also prevent dilution within Game coverage.
"$verification_python" -m coverage report \
  --include=backend/game/preparation.py --fail-under=90
"$verification_python" -m pytest -q tests/integration
node --test tests/frontend/*.test.mjs
