# 09 — Codebase Map

Current checkout, updated 2026-10-04. One Python process serves two business domains, the public metadata catalog, API and native browser client. Assignment 1 uses layered modules within the required monolithic deployment. Folder boundaries define responsibility; they do not imply separately deployed services.

## Backend ownership

| Path | Responsibility and public entry |
|---|---|
| `backend/__main__.py` | Documented `python -m backend` startup |
| `backend/app.py` | `create_app` composition root, dependency injection, HTTP wiring, health, lifespan and static mounts |
| `backend/core/` | Immutable environment configuration, domain errors and source-relative resource paths |
| `backend/api/` | Strict schemas, transport mapping, cookies, Origin checks, admission rate limits and invitation URL generation |
| `backend/application/commands.py` | Named `RoomCommands` and `GameCommands`; HTTP receives values rather than connections |
| `backend/application/coordinator.py` | Server acceptance time, authorization, transaction ordering and Rooms/Game lifecycle reconciliation |
| `backend/application/room_locks.py` | Holder/waiter-scoped `RoomLocks`; idle registry entries are released safely |
| `backend/application/audio_leases.py` | One active host-tab lease, renewal and explicit takeover |
| `backend/application/music_admission.py` | Atomic bridge from verified import receipt into Rooms admission |
| `backend/rooms/service.py` | Admission, identity, capacity, presence, membership and frozen snapshot export; repository is injected |
| `backend/rooms/repository.py` | Rooms-owned SQL; callers own transaction boundaries |
| `backend/rooms/demo.py` | Validated seed replacement, independent room assignments and public Demo fixtures |
| `backend/rooms/music.py` | Persist normalized imports and observed listener ownership, including unavailable previews |
| `backend/game/service.py` | Game policy, answer finality, readiness, recovery, phase transitions and completion; includes `advance` |
| `backend/game/preparation.py` | Separate upcoming candidate, renewable check-ins, freshness and lease validation at promotion |
| `backend/game/selection.py` | Pure bounded full-game candidate/reserve planning |
| `backend/game/scoring.py` | Exact server-timed scoring and version-aware artist/title classification |
| `backend/game/repository.py` | Game-owned SQL, durable command receipts, score updates and rankings |
| `backend/game/views.py` | Public projections, caller-owned answer visibility and private host audio manifest |
| `backend/storage/database.py` | SQLite connection policy and application migrations 001–006 |

There is no separate phase controller: `GameService` owns timed transitions and commands together. Routes call injected use cases. Coordination applies due transitions before accepting the incoming command, keeping closure/expiry correct when a stale request is rejected. Room locks serialize both requests and cleanup; SQLite transactions maintain local cross-domain atomicity.

Rooms exports roster, song facts and familiarity values at Start. Game freezes them without querying live membership tables. SQL foreign keys still enforce the shared local room lifecycle, as shown in [the data model](06_DATA_MODEL.md). Replacing storage or splitting services requires addressing that transaction and lifecycle boundary explicitly.

## Public metadata and music adapters

| Path | Responsibility |
|---|---|
| `backend/catalog/search.py` | Shared metadata lookup, query coverage, bounded request budget/cache and coalescing; receives permitted fixture values and injected provider callable |
| `backend/catalog/store.py` | Public metadata/FTS index, persistent query coverage and temporary preview references |
| `backend/catalog/links.py` | Permanent positive identity links, bidirectional storage, scope/purpose and fingerprint invalidation |
| `backend/catalog/selection.py` | Resolve signed bulk references before submission using narrow injected capabilities |
| `backend/catalog/tokens.py` | Signed room-scoped selected-song facts; process secret and twenty-minute lifetime |
| `backend/catalog/identity.py` | Shared pure identity/title normalization |
| `backend/catalog/importer.py`, `starter/` | Streaming optional bulk metadata import and the small MusicBrainz starter/provenance |
| `backend/music/spotify.py` | PKCE, account verification and bounded personal top/recent observations |
| `backend/music/apple.py` | Developer catalog search/charts, recording matches and credited-artist enrichment |
| `backend/music/http.py`, `media.py` | Bounded transport, sanitized errors, allowed preview hosts and conservative recording checks |
| `backend/music/recordings.py`, `previews.py` | Verified recording relationships and temporary playable-preview resolution |
| `backend/music/importer.py` | Bounded import/preview work, observed membership preservation and independent decoys |
| `backend/music/admissions.py` | Expiring browser-bound PKCE receipts and background import jobs; no SQL |

Public search knows no hidden listener tables or private room SQL. Application commands supply Demo metadata only when permitted. Provider waits happen after room serialization/read contexts end. Successful relationships are reused across rooms/games; preview expiry does not expire the recording identity. Signed answer submission and score closure need no provider I/O.

All active persistence uses `DATA_DIR/whos_on_repeat.sqlite3`: application migration version 6 and catalog component version 3 coexist independently. There is no separate catalog file or legacy import module. Shared catalog data contains no private account/listener evidence.

## Browser ownership

| Path | Responsibility |
|---|---|
| `frontend/app.mjs` | Compose model, transport, actions, runtime, readiness, audio and screens |
| `frontend/application/state.mjs` | Session drafts and accepted local receipts; no server authority |
| `frontend/application/actions.mjs` | User commands and frozen retry payloads |
| `frontend/application/runtime.mjs` | Non-overlapping polling and independent heartbeats |
| `frontend/application/round-readiness.mjs` | Participant ACKs, readiness generation/session fencing and reset |
| `frontend/application/upcoming-readiness.mjs` | Renewable preparation during results with visibility, session and lease cancellation |
| `frontend/application/screen-host.mjs` | Screen mounting, destruction and frame lifecycle |
| `frontend/application/music-admission.mjs` | OAuth navigation and import-receipt recovery; no provider tokens |
| `frontend/transport/client.mjs` | JSON transport, request cancellation and server-clock estimate |
| `frontend/audio/host.mjs` | Host unlock/lease, bounded preload/decode and playback scheduling, with stale-work cancellation |
| `frontend/audio/levels.mjs`, `lab.mjs` | Measured waveform extraction and isolated lab playback |
| `frontend/game/` | Pure lobby eligibility, timing and caller-owned result projections |
| `frontend/screens/` | Entry, import, lobby, round, reveal, rankings, help and history composition |
| `frontend/components/` | Reusable controls, character SVG/motion, explicit song search, header and standings |
| `frontend/styles/`, `assets/` | Responsive styles, shared tokens, bundled licensed font and favicon |
| `frontend/dom.mjs` | Stable keyed reconciliation and safe text updates |
| `frontend/lab.mjs`, `lab/`, `lab.html` | Fixture-only visual studio, with separate cancellation/clock ownership |

Guests acknowledge round data independently of host playback. Only the host speaker loads/plays game clips in the current mode. Resetting or changing room invalidates pending audio/readiness work. Polling preserves stable controls and SVG nodes; result helpers display authoritative scores rather than recalculate them. Reveal includes only the requesting player's guesses alongside the public correct song, frozen listeners and rankings.

Native `.mjs` modules are served directly from `/ui/`, with no npm manifest or build step. `/` is the game; `/ui-lab` is explicitly fixture-only. Browser Search or Enter sends a query; typing alone does not. A selected unresolved bulk result is verified once before its signed facts can be submitted.

## Assets, tools and verification

`catalog/demo_catalog.json` contains the sole default Demo's 100 public metadata rows: 80 personal songs and 20 decoys. Every participant receives 36 personal songs with simulated familiarity. The tracked `catalog/demo_pack_source.json` pins the corresponding Drive archive and inventory; media installs under ignored `catalog/local/packs/<pack>-<sha12>/`. API keys and ffmpeg are unnecessary for installation and play. First setup needs internet or the pinned ZIP supplied to `tools/setup_demo_pack.py --archive`. Media is served at `/static/demo/local/`; `/music-credits` serves the selected pack's attribution. Private acquisition tooling and original media remain excluded from source control. No synthetic or festival fallback catalog remains. See [catalog setup](../catalog/README.md).

The UI lab requests one actual catalog sample from `/api/demo/preview`; its alternate guesses are metadata-only rendering scenarios rather than another playable catalog. Startup does not autoplay audio, and character/lobby fixtures remain available if music metadata cannot load.

`tools/drive_download.py` owns anonymous Drive confirmation and bounded ZIP transfer; `tools/demo_pack.py` owns pinned inventory checks, locking and atomic installation. `tools/demo_pack_validation.py` shares the actual catalog and asset validation between setup and launch. `tools/setup_demo_pack.py` is the public install/offline-check command. The launch script prepares a missing pack before starting the server; runtime providers and application data are independent of that setup. Downloads and installations stay in ignored `catalog/local/`; only the descriptor, installer and tests belong in source control.

`requirements.txt` is the single root runtime/test dependency manifest. `pyproject.toml` configures verification rather than declaring another dependency set. `tools/verify.sh` runs local checks; catalog setup/import and playtest/load tools are optional development tools. `tools/run_demo.sh` and `tools/run_real_game.sh` share a portable `launch_game.py` entry, environment and asset preflight, and Python setup helpers. The application startup contract does not require a `.env` file, manual migrations, tunnel or media encoder.

| Change | Starting point | Meaningful verification |
|---|---|---|
| Admission/presence/identity | Rooms service and injected repository | Rooms policy units plus SQLite/API integration |
| Scores or partial artist credit | Game scoring | Pure arithmetic/classification units and persisted score tests |
| Plan/replacement/skip policy | Game selection/service | Deterministic selection units and clock-driven replacement integration |
| Timed phases or readiness | Game service; application round readiness | Deadline/recovery integration and stale browser readiness tests |
| Command ordering/authorization | Named commands, coordinator and RoomLocks | Actual HTTP paths, concurrent same/different room operations and cleanup |
| Host lease/preload/playback | Audio leases and host audio | Lease/takeover APIs, late response tests and actual browser/device playback |
| Search/verification/provider | Catalog components and music adapters | Query-cache/token/link tests and explicit browser selection |
| Persistence/startup | Database and catalog initialization | Fresh shared schema, rollback/restart/migration and preserved-history tests |
| Demo metadata/media | Pinned metadata/source, installer and pack validation | Full default ten-/fifteen-round HTTP match, real media retrieval and decode |
| Presentation | Screens, components and styles | Browser interaction, keyboard/mobile layout and physical devices |

`tests/unit/` isolates business policy with explicit dependencies; integration tests use temporary real SQLite and production HTTP paths; `tests/frontend/` checks browser module behavior with Node. Automated acceptance does not establish physical audio, phone compatibility, synchronized speakers or real-account availability. Run/setup/coverage commands live in [README](../README.md); dated experiments remain in the PoC and implementation-status documents.
