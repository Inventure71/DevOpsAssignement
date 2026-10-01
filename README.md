# Who's On Repeat

A local music party game for 3–10 people. The host also plays; everyone guesses
on their own screen and the host device supplies the shared speaker. This
checkpoint contains the **Demo backend**, four temporary fictional songs and
hidden database assignments. The game frontend is being developed separately.
Real-song catalog population and personal music-provider admission remain pending.

## Run the backend

Python 3.12+ is recommended. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend
```

Open `http://localhost:8000/docs` for the interactive API reference, or fetch
`http://localhost:8000/openapi.json` for the schema. `/health/live` and
`/health/ready` expose process and initialization checks. The root URL returns
404 because this checkpoint contains no game UI.

Create a Demo room through `POST /api/rooms` with a nickname and character, then
join using its room code from separate browser sessions. The API sets a
room-specific identity cookie; keep that cookie when requesting room state or
issuing commands. See [the API contract](docs/07_API_AND_RUNTIME.md) and the
interactive request schemas for the complete fields and host-audio lease flow.

The four-song seed supports admission, lobby, persistence and media-delivery
checks. It is too small for a complete match: Start requires at least ten songs
per player, and planning needs distinct songs, an independent decoy pool and
checked replacements. A Start request with this seed returns
`insufficient_songs`. Larger isolated test fixtures exercise the full game loop.
The minimum and selection rules remain in force while the catalog is populated.

A future frontend will enable host audio with a tap, preload the planned clips
and reserves, send automatic check-ins, and display countdowns, reveals and
rankings. Only the active host audio controller receives the private playback
manifest. Demo familiarity is fictional; it does not import anyone's listening
history. Normal mode returns `provider_unavailable` until a real provider is
validated and never silently changes to Demo.

## Configuration and storage

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | HTTP port; binds to `0.0.0.0` |
| `DATA_DIR` | `./data` | SQLite directory |
| `COOKIE_SECURE` | `false` | Set `true` when served over HTTPS |
| `SETUP_TIMEOUT_MS` | `60000` | Bounded full-game preload window (10000–120000 ms) |
| `ROOM_CREATE_LIMIT` | `10` | Room creation attempts per client address per minute |
| `ROOM_JOIN_LIMIT` | `30` | Join attempts per client address per minute |

SQLite lives at **`DATA_DIR/whos_on_repeat.sqlite3`**. Startup applies versioned
migrations, seeds the catalog and recovers interrupted games automatically.
Startup refreshes the shared fixture catalog; existing room songs and frozen
snapshots stay unchanged and can still reference assets from an earlier catalog.
Create a new room, or use a fresh `DATA_DIR`, when checking the four-song seed.
No music credentials, external service, ffmpeg, Dockerfile or manual migration
are needed to run the Demo backend. Use **one process / worker / replica**, with
persistent local storage that supports SQLite WAL.

Only a completed game renews the whole room's 30-day retention. A restart aborts
unfinished games, retains revealed scores, and returns surviving rooms to the
lobby. Lobby settings are process-local until Start freezes them; a restart
restores the last game's settings, or defaults before the first game. Back up a
running database with SQLite's backup API, rather than copying only its main
file while WAL writes are active.

Room credentials are random HttpOnly cookies scoped to that room, with only
SHA-256 digests stored. Refresh restores the player; a nickname never recovers
lost identity. Multiple host tabs must explicitly take over audio ownership.
Moving the controller during an unrevealed attempt voids that attempt rather
than replaying the song.

## Structure

| Directory | Responsibility |
|---|---|
| `backend/api/` | HTTP routes, request validation, cookies, origin checks and rate limits |
| `backend/application/` | Command ordering, cross-domain lifecycle transactions and host audio leases |
| `backend/rooms/` | Admission, membership, familiarity, demo assignment and room snapshots |
| `backend/game/` | Frozen plans, readiness, phases, scoring, guesses and rankings |
| `backend/storage/` | SQLite connections and versioned migrations |
| `backend/core/` | Configuration, shared errors and repository-relative resource paths |
| `catalog/` | Four temporary song records, bundled clips/cover and their provenance |
| `tests/` | Python unit/integration tests and isolated metadata fixtures |
| `tools/` | Optional development and measurement commands |

`backend/app.py` wires the application and owns startup, health and background
work. Run it through `python -m backend`. Catalog assets live in
`catalog/assets/` and are served at `/static/demo/`; no frontend directory is
needed for startup or media delivery. Runtime packages are in `requirements.txt`;
tests and measurements add `requirements-dev.txt`. See the
[codebase map](docs/09_CODEBASE_MAP.md) for module boundaries and change locations.

Both domains persist through SQLite. Game receives plain snapshot values from
Rooms and does not query Rooms tables. Submitted empty listener selections mean
Nobody; absent submissions mean No answer and score zero. Artist partial credit
uses frozen structured identities. Rankings count revealed attempts only;
void attempts retain diagnostic answers. Artwork references are optional; the
future reveal UI must display a placeholder when an image is missing or fails.

## Verify

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
```

Tests use real temporary SQLite databases and injected server clocks. They
exercise both domains, ten-round games, concurrent final submissions, exact
deadlines, immutable snapshots, retries, readiness exclusions, replacement
budgets, host expiry, restart and retention. Catalog integration tests check
startup and media delivery independently of a frontend. Current evidence and
remaining acceptance work are recorded in
[implementation status](docs/08_IMPLEMENTATION_STATUS.md).

A successful automated run does not prove physical audibility, phone-browser
compatibility, the optional 300 ms all-device drift target, or deployment load
capacity. Those checks require the frontend and appropriate devices. See the
[architecture](docs/05_ARCHITECTURE.md), [rules](docs/03_GAME_RULES.md),
[data model](docs/06_DATA_MODEL.md), and [API contract](docs/07_API_AND_RUNTIME.md).

The four audio fixtures are temporary original synthesized compositions; see
[catalog provenance](catalog/README.md). Real-song population is a separate
catalog milestone.

The optional local capacity probe uses isolated temporary data and 20 active games:

```bash
python -m tools.load_demo
```

It measures the actual ASGI state endpoint for 20 rooms × 10 players, with
400 requests and 20 workers. It excludes real network and browser delivery,
so its measurements describe server capacity rather than deployment acceptance.
