# 09 — Codebase Map

The backend is one Python process with two business domains. Directory
boundaries describe responsibilities; they do not imply separate deployed
services. This checkpoint contains the API and catalog assets, with no game
frontend. The four-song fixture catalog supports lobby/data-flow checks only.
Real-song population and frontend implementation are separate follow-up work.

## Repository layout

```text
backend/
  __main__.py                 python -m backend entry point
  app.py                      FastAPI wiring, health, startup and background work
  api/                        HTTP routes, schemas, cookies, origin checks, limits
  application/                Cross-domain command ordering and audio leases
  core/                       Configuration, shared errors and resource paths
  storage/                    SQLite connections and versioned SQL migrations
  rooms/                      Admission, identity, songs, familiarity, snapshots
  game/                       Planning, scoring, readiness, phases and rankings
catalog/
  demo_catalog.json           Runtime song metadata with stable browser URLs
  assets/
    clips/                    Four temporary MP3s
    covers/                   One temporary SVG cover
  README.md                   Fixture provenance and current catalog limitation
tests/
  unit/                       Pure scoring and selection tests
  integration/                Rooms/Game/HTTP paths through temporary SQLite
  support/                    Larger isolated metadata fixtures for verification
tools/
  load_demo.py                Optional ASGI capacity probe
```

Root documents contain the setup guide, design decisions and AI usage record.
`docs/01` through `docs/07` cover planning, requirements, rules, PoC, architecture,
data and the API/runtime contract. `docs/08` distinguishes implementation evidence
from remaining acceptance work. `requirements.txt` contains runtime dependencies;
`requirements-dev.txt` adds testing and measurement dependencies. `pyproject.toml`
configures project tooling. Runtime SQLite files belong in the ignored `data/`
directory, or the directory selected by `DATA_DIR`.

## Backend ownership and data flow

HTTP input passes through `backend/api/schemas.py` and handlers in `routes.py`.
The API converts transport values into calls to `backend/application/coordinator.py`.
The coordinator orders room commands, checks authority and deadlines, and
coordinates short transactions that touch both domains. It does not calculate
scores or own the domains' SQL queries.

`backend/rooms/service.py` owns admission, identity, membership and song-pool
behavior; `repository.py` owns its persistence operations. `demo.py` validates
`catalog/demo_catalog.json` and seeds independent shared fixture records. At
Start, Rooms exports plain snapshot values to Game, including starting players,
song metadata, artwork references and per-player familiarity.

`backend/game/selection.py` builds the frozen song plan; `scoring.py` calculates
exact points. `service.py` owns gameplay commands and persistence coordination,
`phases.py` advances timed phases, `repository.py` owns Game SQL, and `views.py`
projects phase-appropriate public/private values. Game does not query Rooms'
tables or hold provider credentials. Shared transaction connections preserve
atomic lifecycle changes while repositories retain table ownership.

`backend/storage/database.py` owns connection setup and migrations.
`backend/core/paths.py` resolves checked-in catalog, asset and migration locations
relative to the source tree, rather than the shell's working directory. Browser
URLs such as `/static/demo/clips/song-001.mp3` remain independent of those
filesystem paths. `backend/app.py` mounts only the catalog's bundled assets at
`/static/demo`; `/docs` and `/openapi.json` expose the API reference, while `/`
returns 404. Importing a domain does not start the HTTP server.

## Future frontend boundary

The future frontend owns phase rendering, presentation state, non-overlapping
polling, independent heartbeats, automatic ACKs, clock estimates and scheduled
host playback. The backend remains authoritative for identity, phase, timing
and scoring. Browser code consumes the JSON API and the private host audio
manifest; it does not own catalog assets or domain persistence.

The earlier `feature/demo-core` checkpoint retains its temporary browser UI.
It is excluded from this backend checkpoint so a new frontend can be reviewed
and integrated separately. Browser behavior and physical audio checks must run
against that future implementation; Python tests do not establish UI acceptance.

## Where to make a change

| Change | Starting point | Verification |
|---|---|---|
| Song records, previews or artwork | `catalog/demo_catalog.json`, `catalog/assets/`, `backend/rooms/demo.py` | Catalog checkpoint and seeding integration tests |
| Room admission, names or characters | `backend/rooms/service.py` and repository | Rooms integration tests; API tests for transport changes |
| Points or artist partial credit | `backend/game/scoring.py` | Scoring unit tests and persisted-score integration tests |
| Song/difficulty/replacement selection | `backend/game/selection.py` | Selection unit tests and game replacement tests |
| Readiness, deadline or automatic phase behavior | `backend/game/phases.py`, `backend/game/service.py` | Game integration tests with injected clocks |
| Host audio control and takeover | `backend/application/audio_leases.py` and coordinator | Lease/API integration tests; playback checks when frontend exists |
| New HTTP field or command | `backend/api/schemas.py`, `backend/api/routes.py`, relevant service | API and affected service integration tests |
| Catalog asset delivery | `backend/core/paths.py`, `backend/app.py` | HTTP resource and outside-working-directory startup tests |
| Layout, visual style or browser interaction | Future frontend implementation | Browser interaction and physical device checks |
| Schema or startup behavior | `backend/storage/`, `backend/app.py` | Temporary SQLite migration/restart integration tests |

Future personal-history and preview providers need bounded adapters at the
Rooms/import and application/preparation boundaries. They should return
normalized values rather than spread provider-specific code through scoring,
SQL repositories or presentation. No real-provider adapter is implemented yet.

Run instructions and current verification commands are in [README](../README.md).
Structural organization does not establish physical audio, phone compatibility,
network synchronization or deployment acceptance; those remain separate checks.
