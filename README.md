# Who's On Repeat

A local music party game for 3–10 people. Everyone guesses on their own screen;
the host also plays and supplies the shared speaker. This branch implements
the **Demo core**, with four temporary fictional songs and hidden database
assignments. The real-song catalog and UI redesign are the next milestone.
Personal music-provider admission and all-device audio remain pending.

## Run

Python 3.12+ is recommended. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend
```

Open `http://localhost:8000`. Create a Demo room and share its six-character
code. Two other people join from their own browsers. The current four-song seed
supports lobby and data-flow checks, but it is too small for a complete match.
Start requires at least ten songs per player, and the plan needs distinct songs,
an independent decoy pool and checked replacements. With this seed, the Start
button stays disabled (a direct API request returns `insufficient_songs`); the normal game screens cannot be played through
yet. Larger temporary test fixtures exercise the complete game loop.

With a sufficient catalog, enable shared audio on the host, choose settings,
then Start. Keep the host browser active. The full set and reserves preload
once; check-ins, countdowns, reveals and rankings then advance automatically.

For phones on the same trusted LAN, use the computer's LAN address and `PORT`.
The host browser needs Web Audio and a tap to enable sound. This is a casual
shared-speaker game: only the active host tab gets the private audio manifest.
The seeded familiarity assignments are fictional; Demo demonstrates the game
mechanics without importing anyone's actual listening history.

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
snapshots stay unchanged and may reference media removed during this cleanup.
Create a new room, or use a fresh `DATA_DIR`, when checking the four-song seed.
No credentials, external service, ffmpeg, Dockerfile or manual migration are
needed to run Demo. Use **one process / worker / replica**, with persistent local
storage that supports SQLite WAL. `/health/live` checks liveness;
`/health/ready` checks initialized storage and the runtime task.

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
| `backend/core/` | Configuration, shared errors and repository-relative asset paths |
| `temporary_frontend/` | Entry page, browser ES modules, styles, images and bundled demo media |
| `catalog/` | Four temporary song records and their provenance |
| `tests/` | Python unit/integration tests, frontend behavior checks and isolated fixtures |
| `tools/` | Optional development and measurement commands |

`backend/app.py` wires the application and owns startup, health and background
work. Run it through the package entry point, `python -m backend`. Runtime
packages are in `requirements.txt`; tests and measurements add
`requirements-dev.txt`. See the [codebase map](docs/09_CODEBASE_MAP.md) for
module boundaries and where to make common changes.

Both domains persist through SQLite. Game receives plain snapshot values from
Rooms and does not query Rooms tables. Submitted empty listener selections mean
Nobody; absent submissions mean No answer and score zero. Artist partial credit
uses frozen structured identities. Rankings count revealed attempts only;
void attempts retain diagnostic answers.

## Verify

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
for module in temporary_frontend/static/js/*.js; do
  node --input-type=module --check < "$module"
done
node tests/frontend/client.test.mjs
```

The tests use real temporary SQLite databases and injected server clocks. They
exercise both domains, ten-round games, concurrent final submissions, exact
deadlines, immutable snapshots, retries, readiness exclusions, replacement
budgets, host expiry, restart and retention. The coverage result and browser
checks for this implementation are recorded in
[implementation status](docs/08_IMPLEMENTATION_STATUS.md).

A successful automated run does not prove physical audibility, phone-browser
compatibility, the 300 ms optional all-device drift target, or production load
capacity. Those acceptance checks remain separate. See the
[architecture](docs/05_ARCHITECTURE.md), [rules](docs/03_GAME_RULES.md),
[data model](docs/06_DATA_MODEL.md), and [API contract](docs/07_API_AND_RUNTIME.md).

The four audio fixtures are temporary original synthesized compositions; see
[catalog provenance](catalog/README.md). Normal mode rejects admission until a real
provider is validated; it never silently switches to Demo.

The local capacity probe uses isolated temporary data and 20 active games:

```bash
python -m tools.load_demo
```

It measures the actual ASGI state endpoint for 20 rooms × 10 players, with
400 requests and 20 workers. It excludes real network and browser delivery,
so it is evidence for server capacity rather than full deployment acceptance.
