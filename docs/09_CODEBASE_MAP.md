# 09 — Codebase Map

The backend is one Python process with two business domains. Directory
boundaries describe responsibilities; they do not imply separate deployed
services. `feature/frontend` contains the native browser client, signed catalog
search and the Normal Spotify/Apple provider checkpoint. The four-song Demo
catalog still supports lobby/data-flow checks only; real-song Demo population,
real five-account Spotify QA and physical-device acceptance remain follow-up work.

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
  catalog/                    Public metadata search/cache, signed tokens and pure recording identity normalization
  music/
    spotify.py                PKCE, account verification and bounded top/recent imports
    apple.py                  Developer catalog search/charts and recording resolution
    http.py                   Bounded JSON transport and sanitized provider errors
    media.py                  Allowed audio sources, delivery probes and recording matching
    previews.py               Cached, bounded preview resolver
    importer.py               Account imports, observed ownership and independent decoys
    admissions.py             Expiring browser-bound receipts and background import jobs
frontend/
  app.mjs                     Browser dependency composition and startup
  application/
    state.mjs                 Local drafts and accepted receipts
    actions.mjs               User commands and frozen retry payloads
    runtime.mjs               Non-overlapping polling and independent heartbeats
    screen-host.mjs           Screen selection, mounting and lifecycle
    music-admission.mjs       OAuth navigation, import polling and connection recovery
  transport/client.mjs        JSON requests, cancellation and clock estimates
  audio/
    host.mjs                  Host lease, preload, decoded buffers and scheduling
    levels.mjs                Measured waveform extraction
    lab.mjs                   Isolated preview audio and cancellation
  game/
    timing.mjs                Elapsed/remaining deadline arithmetic
    results.mjs               Owner-only result projections and frozen rankings
    lobby-readiness.mjs       Pure lobby start eligibility
  screens/                    Entry/import progress, lobby, round, results, help/history
  components/                 Reusable character, controls, header and standings
  styles/                     Tokens, responsive composition and supporting pages
  assets/                     Local Nunito font/license and favicon
  dom.mjs                     Stable keyed reconciliation and safe text updates
  lab.mjs, lab.html            Isolated fixture entry point
  lab/
    fixtures.mjs              Pure snapshots without other players' answers
    characters.mjs            Standalone character studio
    controller.mjs            Fixture navigation, events, audio and clock lifecycle
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
  frontend/                   Native module behavior checks through Node’s test runner
tools/
  load_demo.py                Optional ASGI capacity probe
```

Root documents contain the setup guide, design decisions and AI usage record.
`docs/01` through `docs/07` cover planning, requirements, rules, PoC, architecture,
data and the API/runtime contract. `docs/08` distinguishes implementation evidence
from remaining acceptance work. `docs/10` records the current frontend design. `requirements.txt` contains runtime dependencies;
`requirements-dev.txt` adds testing and measurement dependencies. `pyproject.toml`
configures project tooling. Runtime SQLite files belong in the ignored `data/`
directory, or the directory selected by `DATA_DIR`.

## Backend ownership and data flow

HTTP input passes through `backend/api/schemas.py` and handlers in `routes.py`.
Room APIs convert transport values into calls to `backend/application/coordinator.py`.
`backend/api/music.py` owns pre-membership config/admission/callback/status/cancel
transport, temporary cookies and canonical-origin validation.
`backend/application/music_admission.py` rechecks an import receipt's validity
inside the admission transaction, so expiry rolls back rather than orphaning a player.
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
filesystem paths. `backend/app.py` mounts catalog assets at `/static/demo` and
frontend assets separately at `/ui`; `/` serves the game entry, `/ui-lab` isolated
fixtures, and `/docs`/`/openapi.json` the API reference. Importing a domain does not
start the HTTP server.

## Frontend and catalog-search boundaries

`app.mjs` wires browser dependencies and starts the application. Modules in
`application/` coordinate local state, commands and polling. `screen-host.mjs`
selects and mounts screens, owns their animation clock and destroys the outgoing
screen. `transport/client.mjs` owns HTTP requests and server-clock estimates;
`audio/host.mjs` owns host leases, bounded preload/decode and scheduled playback.
`application/music-admission.mjs` owns OAuth navigation and receipt polling;
`screens/music-import.mjs` renders progress and reconnection controls. Neither
handles provider tokens. Local drafts and accepted receipts never grant
authority or change server points.
Pure `game/` modules project timing, results and lobby readiness; screens render
those values and emit user intent. `components/site-header.mjs` owns navigation
and the profile menu independently of game orchestration.

Screens retain structural DOM and keyed player cards. Standalone Web Components
own layered character animation, selection controls, asynchronous song typeahead
and waveform/progress display. `blob-palette.mjs` owns colors, `blob-rig.mjs` owns
pure contour/motion/springs, and `blob-motion.mjs` owns the shared visible-frame
loop. `character.mjs` renders persistent SVG joints; `color-picker.mjs` owns reusable
swatches and preview controls. `game/results.mjs` maps revealed server song matching
to outcome badges, projects the current player's listener correctness and preserves
frozen ranks; it never recomputes scoring. A reveal contains the correct song,
actual listener IDs and only the requesting player's `my_answer`. No screen or
component receives other players' submitted guesses. Flanking listener cards
compare the current player's selection with the revealed listener set; shared
leaderboards display scores and ranks without exposing answers. Updates preserve
focus and stable SVG nodes. The backend owns deadlines and scoring. `/ui-lab` is explicitly
fixture-only; its sessions and guesses do not reach game persistence. Its bootstrap
uses `lab/controller.mjs` for navigation, cancellation and clock lifecycle,
`lab/fixtures.mjs` for pure reproducible state and `lab/characters.mjs` for the
standalone studio. Fixtures follow the same owner-only reveal contract.

`round-countdown.mjs` draws an open upper arc. `waveform-drawing.mjs` owns pure
geometry and drawing customization; `music-waveform.mjs` retains SVG layers and
clips elapsed progress. Both receive the screen clock through `game/timing.mjs`.
Neither component loads audio. `audio/levels.mjs` measures all channels within the
actual answer window; `audio/lab.mjs` loads, decodes and schedules the isolated
preview source, with cancellation on navigation or document hiding.

`screens/results.mjs` composes the cover-centered `screens/reveal.mjs` and the
podium/list view in `components/standings.mjs`. `listener-result.mjs` owns one
player's local listener-guess feedback. `styles/results.css` keeps their responsive
presentation separate from listening/lobby styles. All displays retain keyed
characters across polling; submitted answers do not stop the waveform or audio.

`backend/catalog/search.py` searches shared Demo fixtures or the configured
Apple developer catalog, with a public iTunes fallback for no-credentials Demo.
It owns bounded cache/budget and single-flight requests. `tokens.py` authenticates
room-scoped selected facts. Search never consults hidden listener mappings and
runs outside room command locks. Answer acceptance verifies the token, freezes
song facts and calls pure scoring without provider I/O. Migration
`002_song_selections.sql` converts historical choice slots into frozen selected-song
facts while retaining points/ranks. This adapter does not authorize personal music
accounts or acquire playback audio.

`backend/music/spotify.py` normalizes verified personal song facts;
`apple.py` resolves recording previews and verified credited-artist aliases.
`importer.py` coordinates bounded preview work and preserves unavailable observed
ownership. `admissions.py` owns expiring PKCE receipts and its background worker
queue, without SQL. The application's admission callback calls Rooms only after
provider work completes. `backend/rooms/music.py` persists normalized imports
through the Rooms repository; migration 004 adds account digests and pool kinds.
Provider-specific details do not enter Game's selection/phase orchestration.

The earlier `feature/demo-core` checkpoint preserves its temporary UI. Backend
PR #1 is merged into `integration`; the redesigned UI checkpoint is committed at
`a05e19e` on `feature/frontend`, with the provider checkpoint now uncommitted.

## Where to make a change

| Change | Starting point | Verification |
|---|---|---|
| Song records, previews or artwork | `catalog/demo_catalog.json`, `catalog/assets/`, `backend/rooms/demo.py` | Catalog checkpoint and seeding integration tests |
| Room admission, names or characters | `backend/rooms/service.py` and repository | Rooms integration tests; API tests for transport changes |
| Points or artist partial credit | `backend/game/scoring.py` | Scoring unit tests and persisted-score integration tests |
| Song/difficulty/replacement selection | `backend/game/selection.py` | Selection unit tests and game replacement tests |
| Readiness, deadline or automatic phase behavior | `backend/game/phases.py`, `backend/game/service.py` | Game integration tests with injected clocks |
| Host audio control and takeover | `backend/application/audio_leases.py` and coordinator | Lease/API integration tests; browser playback checks |
| New HTTP field or command | `backend/api/schemas.py`, `backend/api/routes.py`, relevant service | API and affected service integration tests |
| Catalog asset delivery | `backend/core/paths.py`, `backend/app.py` | HTTP resource and outside-working-directory startup tests |
| Layout, visual style or browser interaction | `frontend/screens/`, `components/`, `styles/` | Browser interaction, standalone components and physical device checks |
| Selected-song search and verification | `backend/catalog/`, `backend/music/apple.py`, `frontend/components/song-search.mjs` | Signature/cache/provider tests and browser typeahead checks |
| Music authorization/import and previews | `backend/music/`, `backend/api/music.py`, `backend/rooms/music.py` | Provider/admission tests, five-player loop and real-account/audio QA |
| Browser requests, receipts or clocks | `frontend/transport/`, `frontend/application/` | Native module tests and actual session/reconnect checks |
| Schema or startup behavior | `backend/storage/`, `backend/app.py` | Temporary SQLite migration/restart integration tests |

Additional personal-history sources belong behind the existing normalized
adapters and verified admission boundary. They should return normalized values
rather than spread provider-specific code through scoring, SQL repositories or
presentation. File imports, multiple Spotify clients and other personal providers
remain unimplemented; the active Normal path is one Spotify app plus Apple catalog.

Frontend files use explicit `.mjs` extensions in imports and HTML entry scripts.
The browser serves them directly; there is no npm manifest, install or build step.
Run module tests with Node 24 or newer:

```bash
node --test tests/frontend/*.test.mjs
```

Run instructions and Python verification commands are in [README](../README.md).
Structural organization does not establish physical audio, phone compatibility,
network synchronization or deployment acceptance; those remain separate checks.
