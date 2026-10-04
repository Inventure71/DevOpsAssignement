# Architecture Decision Records

These five records retain their original decision dates. The fields summarize the decisions as of 2026-10-04; dated updates explain changes from earlier milestones. Original versions remain in Git history.

The entries were first committed on four distinct local dates: ADR-1 in `7fd5e42` (2026-09-27), ADR-2 in `e5b091b` (2026-09-29), ADR-3 in `acc5000` (2026-09-30), and ADR-4/5 in `a55de5a` (2026-10-01).

## 1. Backend framework: Python + FastAPI

Date: 2026-09-25

Status: Decided

Context: The application needs a single process to serve the browser UI, validate game commands and coordinate music imports. I chose a Python stack that I can study and explain, without adding an ORM or account framework.

Decision: Use FastAPI with one Uvicorn worker, standard-library `sqlite3` persistence and one root `requirements.txt`.

Alternatives considered: Flask is a viable lighter option, but FastAPI provides typed request validation and application lifespan management suited to this API. Django's ORM, admin and account system would add responsibilities the room-based game does not need.

Consequences: Pydantic validates HTTP commands, synchronous domain/SQLite operations run outside the asynchronous event loop, and lifespan owns initialization and the in-process phase task. This requires careful handling of thread, transaction and asynchronous task boundaries.

Update (2026-10-04): application commands coordinate HTTP use cases, domain services own game policy, and injected provider adapters isolate external calls. The backend still serves the frontend and runs as one process.

Implementation: [composition root](backend/app.py), [HTTP routes](backend/api/routes.py), [dependencies](requirements.txt).

## 2. Separate Rooms and Game inside one application

Date: 2026-09-29

Status: Decided

Context: The assignment requires two distinct SQLite-backed domains with a credible future separation point. The provider PoC also showed that personal listening input and playable audio are separate capabilities.

Decision: Rooms owns membership, player identity, assigned/imported songs and familiarity; Game owns games, rounds, answers, scoring and rankings. `Coordinator.start` passes values from `RoomsService.snapshot(conn, room_id)` to `GameService.start`; final song and plan facts are frozen after setup.

Alternatives considered: One combined service would couple membership and provider changes to scoring. Two deployed services would introduce network failure handling and violate the single-process requirement.

Consequences: Game works through its own repository without querying Rooms tables or calling listening-history providers. Copying the relevant facts keeps gameplay stable, but a future service split must replace the current shared transaction with an explicit consistency strategy.

Updates: manual song picking was excluded on 2026-09-30; module responsibilities were documented on 2026-10-01. The 2026-10-02 provider path uses Spotify for listening input and Apple for catalog/previews, with provider I/O outside admission transactions. The 2026-10-04 refinement keeps SQL in repositories, domain rules in services and cross-domain ordering in application coordination.

Implementation: [start coordination](backend/application/coordinator.py), [Rooms service](backend/rooms/service.py), [Game service](backend/game/service.py).
Details: [architecture](docs/05_ARCHITECTURE.md).

## 3. Room-local songs and frozen game facts in SQLite

Date: 2026-09-30

Status: Decided

Context: Players can share songs, while rooms need independent membership and expiry. Historical listener facts and scores must remain stable after disconnects or later lobby changes.

Decision: Store room-local `songs` and `player_songs`, freeze the roster in `game_players` and song/plan facts in game JSON, and persist attempts, answers and command receipts relationally. Keep all application and public catalog tables in `DATA_DIR/whos_on_repeat.sqlite3`, expiring room history 30 days after the last completed game or, if none, room creation.

Alternatives considered: Globally shared listening records complicate room-independent deletion, while live membership lookups would change old games. Fully relational snapshot tables offer stronger database references but add joins and tables for values already transferred through one snapshot contract.

Consequences: Frozen facts stabilize scoring and history; void attempts retain their answers without contributing to rankings. JSON references require service validation, and cleanup must delete Game data before Rooms data within one transaction.

Updates: optional artwork and retained void answers were clarified on 2026-09-30. On 2026-10-01, selected song facts replaced four-choice answers and API projections became owner-only, including for the host. The 2026-10-02 admission schema stores account digests rather than OAuth tokens. The 2026-10-04 refinement places public catalog metadata and scoped verified links in the same SQLite file, superseding the intermediate separate-catalog setup; preview expiry does not erase recording identity.

Schema and diagram: [data model](docs/06_DATA_MODEL.md).
Executable schema: [migrations](backend/storage/migrations/).

## 4. Prioritize core rule tests and verify integration separately

Date: 2026-09-30

Status: Decided

Context: Routing coverage alone cannot establish that membership, deadlines, scoring and recovery behave correctly. The assignment requires at least 70% unit coverage of the two domains' core business logic.

Decision: Prioritize deterministic unit tests for Rooms policy, Game transitions, scoring and selection, with controlled clocks/randomness and a 70% coverage gate. Complement them with temporary SQLite/HTTP integration tests and frontend controller tests for persistence, authority, privacy, retries, readiness and stale asynchronous work.

Alternatives considered: Provider mocks alone bypass gameplay and persistence, while a coverage percentage alone can conceal incorrect boundary behavior. Making every test depend on live accounts or physical devices would make failures harder to reproduce.

Consequences: Repository doubles isolate policy tests, while integration tests exercise real transactions and complete matches. Physical audio, phone compatibility and live account setup remain thinner manual acceptance areas, so automated success cannot establish those outcomes.

Update (2026-10-04): the coverage command measures unit tests only over `backend.rooms.service`, `backend.game.service`, `backend.game.scoring` and `backend.game.selection`. The original strategy also targeted a three-browser ten-round game, sub-two-second round preparation and roughly 400 state polls per second; these are acceptance targets, with historical measurements and their limits recorded separately.

Command and test boundaries: [README](README.md#verify).
Dated results and remaining checks: [implementation status](docs/08_IMPLEMENTATION_STATUS.md).

## 5. Defer all-device audio and broader game features

Date: 2026-10-01

Status: Decided

Context: The first playable milestone needed reliable game behavior before personal provider admission and synchronized playback on multiple devices. All-device audio adds browser gesture, scheduling and drift problems beyond proving the core game.

Decision: Keep shared host-device playback and defer all-device audio, mashups, chat and persistent game accounts from this submission. Provide explicit Demo and configured Normal modes without silently substituting fictional listening data for real imports.

Alternatives considered: A fake authorization flag or automatic Normal-to-Demo downgrade would misrepresent the input data. Building synchronized audio and account recovery alongside the initial core would increase timing and identity complexity before the main flow was accepted.

Consequences: Guests participate in readiness and guessing while the host owns playback; Demo assignments remain fictional. The scoped game is easier to reproduce, but it needs a shared speaker and does not provide synchronized playback on each player's device.

Evolution: the 2026-10-01 milestone used four original Demo tracks and deferred Normal admission. The 2026-10-02 checkpoint added the Normal provider path, while live account/device acceptance remained separate. On 2026-10-04, Demo moved to the checksum-pinned 100-song pack with automatic installation before server startup or installation from a downloaded archive; subsequent gameplay works offline without provider credentials. Real-game launch retains Demo, and older synthetic/festival packs and fallback launch paths have been removed.

Scope and runtime: [API/runtime contract](docs/07_API_AND_RUNTIME.md).
Teacher setup: [README](README.md#run), [Demo pack](catalog/README.md).