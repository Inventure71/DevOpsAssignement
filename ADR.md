# Architecture Decision Records

Five decisions, updated on 2026-10-04. Original decision dates are retained.
First commits: ADR-1 `7fd5e42` (Sep 27), ADR-2 `e5b091b` (Sep 29), ADR-3 `acc5000` (Sep 30), ADR-4/5 `a55de5a` (Oct 1).

## 1. Backend framework: Python + FastAPI

Date: 2026-09-25

Status: Decided

Context: The app needs one process to serve the browser, validate commands and coordinate music imports. Python is a stack I can study and explain.

Decision: Use FastAPI, one Uvicorn worker, standard-library SQLite and one root `requirements.txt`.

Alternatives considered: Flask is lighter; FastAPI provides typed validation and lifespan management. Django adds an ORM, admin and account system beyond this game's scope.

Consequences: HTTP validation stays at the API boundary. Synchronous SQLite work runs outside the event loop, while lifespan owns initialization and the phase task; transaction and task boundaries need careful coordination.

Frontend rationale (2026-10-04): native JavaScript modules and CSS are served by the same process. Server templates still need browser code for polling, readiness and host audio; React with a build tool adds dependencies and a build step. Native modules keep setup small and behavior inspectable, at the cost of explicit state updates, screen lifecycle and cancellation guards. Frontend controller tests cover those responsibilities.

Implementation: [app](backend/app.py), [routes](backend/api/routes.py), [dependencies](requirements.txt).

## 2. Separate Rooms and Game inside one application

Date: 2026-09-29

Status: Decided

Context: Membership and music imports change for different reasons than rounds and scoring. The assignment requires two SQLite-backed domains with a future separation point.

Decision: Rooms owns membership and listening data; Game owns frozen games, attempts, answers and rankings. Application coordination passes `RoomsService.snapshot` values into `GameService.start`.

Alternatives considered: One combined service couples provider changes to gameplay. Separately deployed services add network coordination and conflict with the single-process constraint.

Consequences: Game uses stable snapshots and its own repository. A future service split will need an explicit consistency strategy to replace the shared transaction.

Update (2026-10-04): Spotify and Demo translate input through `MusicSource`, then share `MusicImporter`, `MusicAdmissionHandler` and Rooms persistence. Provider calls happen before the admission transaction. [Architecture](docs/05_ARCHITECTURE.md) explains these boundaries and their course-pattern rationale.

## 3. Room-local songs and frozen game facts in SQLite

Date: 2026-09-30

Status: Decided

Context: Players can share recordings, but each room needs independent expiry. Historical listeners and scores must survive disconnects and later lobby changes.

Decision: Store room-local `songs`/`player_songs`, freeze roster and song-plan facts at Start, and persist attempts, answers and receipts in `DATA_DIR/whos_on_repeat.sqlite3`. Expire rooms 30 days after their last completed game, or creation if none completes.

Alternatives considered: Global listening records complicate room deletion; live membership lookups change old games. Fully relational snapshot tables add joins for facts already transferred as values.

Consequences: Frozen facts stabilize scoring and history, including retained void answers. Services validate JSON references, and transactional cleanup deletes Game data before Rooms data.

Update (2026-10-04): public catalog metadata and verified links share the application database. Preview expiry affects audio availability; recording identity remains stored. See the [schema and diagram](docs/06_DATA_MODEL.md).

## 4. Prioritize core rule tests and verify integration separately

Date: 2026-09-30

Status: Decided

Context: Membership, deadlines, scoring and recovery need reproducible tests. The assignment requires at least 70% unit coverage of both domains' core business logic.

Decision: Use deterministic unit tests and a 90% core coverage gate per domain. Add real SQLite/HTTP tests for persistence and transport, and frontend tests for controller and audio behavior.

Alternatives considered: Broad HTTP tests alone make policy failures harder to isolate. Live-provider tests depend on account access and external availability.

Consequences: Controlled clocks, randomness and repository doubles make policy tests repeatable; integration tests cover transactions and complete matches. Device audio and live accounts require manual checks.

Update (2026-10-04): consolidation gives each behavior a clear test owner. Coverage includes Rooms service and Game service, scoring, selection, preparation and song-title matching. See [test ownership](docs/18_TESTING_STRATEGY.md) and the [verification command](README.md#verify).

## 5. Use host-device audio and keep the first game focused

Date: 2026-10-01

Status: Decided

Context: Shared playback avoids per-device gesture, scheduling and drift problems while the core game is being built. Provider uncertainty also requires a reproducible Demo.

Decision: Play audio on the host device and defer synchronized device audio, mashups, chat and persistent game accounts. Offer explicit Demo and Real modes, with successful personal import required before Real membership.

Alternatives considered: Synchronized playback adds timing and recovery work. Automatically replacing failed personal imports with simulated libraries would change what the game represents.

Consequences: Everyone guesses through their own browser and hears a shared speaker. Demo uses simulated libraries; Real depends on configured provider access.

Evolution: the four-track Oct 1 prototype became a pinned 100-song Demo pack on Oct 4. Spotify personal imports are implemented; Apple provides catalog/previews, with personal listening deferred. The launcher prepares Demo music before starting; bare server readiness works independently of the pack. See [setup](README.md#run) and the [music connection contract](docs/07_API_AND_RUNTIME.md#12-real-music-connection-runtime).
