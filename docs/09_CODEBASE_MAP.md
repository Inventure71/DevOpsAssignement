# 09 — Codebase Map

Path lookup for the modular monolith. [Architecture](05_ARCHITECTURE.md) explains component boundaries; [Game Rules](03_GAME_RULES.md), [Data Model](06_DATA_MODEL.md) and [API](07_API_AND_RUNTIME.md) own the contracts.

## Backend ownership

| Path | Responsibility and public entry |
|---|---|
| `backend/__main__.py` | Documented `python -m backend` startup |
| `backend/app.py` | `create_app` composition root, dependency injection, HTTP wiring, health, lifespan and static mounts |
| `backend/core/` | Immutable environment configuration, domain errors and source-relative resource paths |
| `backend/api/` | Strict schemas, transport mapping, cookies, Origin checks, admission rate limits and invitation URL generation |
| `backend/application/commands.py` | `RoomCommands` and `GameCommands` expose application use cases to HTTP |
| `backend/application/coordinator.py` | Server acceptance time, authorization, transaction ordering and Rooms/Game lifecycle reconciliation |
| `backend/application/room_locks.py` | Holder/waiter-scoped `RoomLocks`; idle registry entries are released safely |
| `backend/application/audio_leases.py` | One active host-tab lease, renewal and explicit takeover |
| `backend/application/music_admission.py` | Atomic bridge from verified import receipt into Rooms admission |
| `backend/rooms/service.py` | Admission, identity, capacity, presence, membership and frozen snapshot export |
| `backend/rooms/repository.py` | Rooms-owned SQL; callers own transaction boundaries |
| `backend/rooms/demo.py` | Validated seed replacement and detached catalog pool snapshots/public Demo fixtures |
| `backend/rooms/music.py` | Validate evidence/mode, persist checked imports and store observations with unchecked previews stripped |
| `backend/game/service.py` | Game policy, answer finality, readiness, recovery, phase transitions and completion |
| `backend/game/preparation.py` | Separate upcoming candidate, renewable check-ins, freshness and lease validation at promotion |
| `backend/game/selection.py` | Pure bounded full-game candidate/reserve planning |
| `backend/game/scoring.py`, `song_titles.py` | Exact server-timed scoring, credited-artist matching and release-label guess normalization |
| `backend/game/repository.py` | Game-owned SQL, durable command receipts, score updates and rankings |
| `backend/game/views.py` | Public projections, caller-owned answer visibility and private host audio manifest |
| `backend/storage/database.py` | SQLite connection policy and application migrations 001–006 |

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
| `backend/music/sources.py` | `MusicSource` / `ListeningData`, Spotify and simulated Demo listening adapters, exact-pack local preview validation |
| `backend/music/authorization.py` | `AuthorizationFlow` and `SpotifyAuthorization`; provider-specific PKCE state, callback policy and token exchange |
| `backend/music/spotify.py` | Spotify authorization URL/token transport, account verification and bounded top/recent observations |
| `backend/music/apple.py` | Developer catalog search/charts, recording matches and credited-artist enrichment |
| `backend/music/http.py`, `media.py` | Bounded transport, sanitized errors, allowed preview hosts and conservative recording checks |
| `backend/music/recordings.py`, `previews.py` | Verified recording relationships and temporary playable-preview resolution |
| `backend/music/importer.py` | Same bounded source/preview pipeline for Spotify and Demo; separate checked songs, observations and independent decoys |
| `backend/music/admissions.py` | Provider-neutral connection receipts/jobs, cancel-versus-commit guard, acknowledgement and Leave retirement |
| `backend/api/music.py` | Neutral `/api/music` config/admission/status/cancel/acknowledge HTTP/cookies; Spotify callback |

## Browser ownership

| Path | Responsibility |
|---|---|
| `frontend/app.mjs` | Compose model, transport, actions, runtime, readiness, audio and screens |
| `frontend/application/state.mjs` | Session drafts and accepted local receipts |
| `frontend/application/actions.mjs` | User commands and frozen retry payloads |
| `frontend/application/runtime.mjs` | Non-overlapping polling and independent heartbeats |
| `frontend/application/round-readiness.mjs` | Participant ACKs, readiness generation/session fencing and reset |
| `frontend/application/upcoming-readiness.mjs` | Renewable preparation during results with visibility, session and lease cancellation |
| `frontend/application/screen-host.mjs` | Screen mounting, destruction and frame lifecycle |
| `frontend/application/music-admission.mjs` | Staged connection draft, neutral receipt recovery/cancel/accept/acknowledge |
| `frontend/application/music-authorization.mjs` | Registry of implemented browser authorization strategies |
| `frontend/application/spotify-authorization.mjs` | Spotify canonical-origin and authorization URL validation |
| `frontend/screens/music-connection.mjs` | Connect your music provider choice before membership; Spotify configured availability, Apple Music disabled as Coming later |
| `frontend/transport/client.mjs` | JSON transport, request cancellation and server-clock estimate |
| `frontend/audio/host.mjs` | Host unlock/lease, bounded preload/decode and playback scheduling, with stale-work cancellation |
| `frontend/audio/levels.mjs`, `lab.mjs` | Measured waveform extraction and isolated lab playback |
| `frontend/game/` | Pure lobby eligibility, timing and caller-owned result projections |
| `frontend/screens/` | Real/Demo entry, connection/import, lobby, round, reveal, rankings, help and history composition |
| `frontend/components/` | Reusable controls, character SVG/motion, explicit song search, header and standings |
| `frontend/styles/`, `assets/` | Responsive styles, shared tokens, bundled licensed font and favicon |
| `frontend/dom.mjs` | Stable keyed reconciliation and safe text updates |
| `frontend/lab.mjs`, `lab/`, `lab.html` | Fixture-only visual studio, with separate cancellation/clock ownership |

Native `.mjs` modules are served at `/ui/`. `/` hosts the game; `/ui-lab` hosts fixture scenarios. See the [readiness and audio contract](07_API_AND_RUNTIME.md#6-automatic-readiness-and-synchronization).

## Assets, tools and verification

| Path | Responsibility |
|---|---|
| `catalog/demo_catalog.json` | Pinned Demo metadata: 80 personal recordings and 20 decoys |
| `catalog/demo_pack_source.json` | Archive and inventory pin |
| `catalog/local/packs/<pack>-<sha12>/` | Ignored installed media, served at `/static/demo/local/` |
| `tools/setup_demo_pack.py` | Install or validate the pack, including an offline archive |
| `tools/drive_download.py` | Bounded anonymous Drive archive transfer |
| `tools/demo_pack.py`, `demo_pack_validation.py` | Inventory/asset validation, install locking and atomic replacement |
| `tools/run_demo.sh`, `run_real_game.sh`, `launch_game.py` | Shared launch/environment/media preflight |
| `requirements.txt` | Runtime/test dependencies |
| `pyproject.toml`, `tools/verify.sh` | Local verification configuration and runner |
| `tests/unit/` | Isolated business-policy tests |
| `tests/integration/` | SQLite, HTTP and cross-component behavior |
| `tests/frontend/` | Browser-module behavior through Node |

[Catalog setup](../catalog/README.md) covers installation and `/music-credits` attribution. The UI lab obtains a catalog sample from `/api/demo/preview`. [README](../README.md) contains run and verification commands; [Testing Strategy](18_TESTING_STRATEGY.md) maps tests to behavior.
