# Architecture Decision Records

## 1. Backend framework: Python + FastAPI
Date: 2026-09-25
Status: Decided
Context: The app is a single-process web server that serves pages, exposes a small JSON API for the game, and makes outbound calls to Apple Music/Spotify while importing players' songs. I need a Python framework I can explain line by line.
Decision: Use FastAPI (served by uvicorn), with SQLite accessed through the standard `sqlite3` module.
Alternatives considered: Flask is a viable lighter framework, but FastAPI's typed request validation and async/ASGI model fit the planned API and outbound imports directly. Django brings an ORM, admin and auth system that this app does not need for room-scoped identities and one small SQLite schema.
Consequences: Pydantic validates the HTTP commands, while synchronous domain/SQLite work runs outside the async event loop. Lifespan owns startup and the in-process phase task; future provider calls need their own bounded outbound adapter. The cost is understanding the boundary between asynchronous orchestration and synchronous transactional services.

## 2. Separate Rooms and Game inside one application
Date: 2026-09-29
Status: Decided
Context: The assignment needs two distinct backend domains that both use SQLite and can be separated later. The PoC showed that importing personal songs and finding audio previews are separate jobs: Spotify supplied the tester's songs while Apple supplied catalog data and previews.
Decision: Rooms owns room membership, player identification, imported/assigned songs and familiarity; Game owns games, rounds, guesses, scoring and rankings. At Start, the application obtains a room value snapshot through `RoomsService.snapshot(conn, room_id)` and passes it to Game; Game freezes final song/plan facts after setup. Separate history and preview interfaces hide external providers, all within one FastAPI process and one SQLite file.
Alternatives considered: A single music/game service would mix imports, membership and scoring, making changes harder to test. Two deployed services would add network and deployment work and violate Assignment 1's single-process constraint.
Consequences: Each domain has its own service, persistence code and business-logic tests; Game never reads Rooms tables directly or calls a history provider. The snapshot duplicates the game-relevant facts to keep scoring stable, and a later service split still needs transaction and failure-handling design.

Scope clarification (2026-09-30): manual song picking is excluded. The host chooses Normal or Demo before joins and also plays; only the host is admin. Normal requires each player's verified music authorization and lobby import; explicit Demo uses a seeded database catalog. No automatic mode downgrade. Rooms exposes nicknames/characters/counts/readiness rather than the song pool.

Runtime clarification (2026-09-30): server-issued room credentials identify players, the host is the only admin, and separate polling/heartbeats preserve presence rules. The full sequence is prepared once; automatic readiness/countdown/guess/reveal/leaderboard phases use server deadlines. Retry increments readiness generation; Continue excludes unready non-host players from the barrier only. The original-plus-three replacement budget and strict 30% skip rule apply across setup and runtime. Revealed results are final, and checked reserves create separate void/replacement attempts. This contract is detailed in `docs/07_API_AND_RUNTIME.md`.

Implementation organization clarification (2026-10-01): `backend/api/` owns
HTTP handling and validation; `backend/application/` coordinates domain
commands and audio leases. `backend/rooms/` and `backend/game/` retain their
existing responsibilities, with connections/migrations in `backend/storage/`
and configuration/shared errors in `backend/core/`. `catalog/` owns runtime
fixture metadata and bundled clips/cover; `tests/` owns verification. The backend serves catalog media independently of presentation assets. The
earlier `feature/demo-core` checkpoint preserves its temporary UI. Backend PR #1
is merged into `integration`; the replacement native ES module/Web Component
frontend checkpoint is on `feature/frontend`. This is the concrete placement
of the existing single-process/domain decision, not a new deployment split.
See `docs/09_CODEBASE_MAP.md`.

## 3. Room-local songs and immutable game snapshots in SQLite
Date: 2026-09-30
Status: Decided
Context: Several players can listen to the same song, but each room must have independent membership and cleanup. A game's starting identities and song facts must survive disconnects and later lobby changes, while history retains rankings, rounds, guesses and scores for the room's 30-day lifetime.
Decision: Use room-local `songs` and `player_songs` familiarity; copy nickname/character/identity into `game_players` and final song/credited-artist facts plus the full checked plan/reserves into immutable game JSON. Persist attempts, answers and host-command receipts relationally. A submitted empty listener list is Nobody; no submission is a missing blank answer with zero points. Expire the whole room 30 days after its last completed game (or creation). Rooms also owns the independent seeded `demo_catalog`; the revised ten-table schema is in `docs/06_DATA_MODEL.md`.
Alternatives considered: Global song records would complicate room-independent deletion. Reading live memberships for old games would change historical listener facts; fully relational song-snapshot tables would enforce more references in SQLite but add tables and joins for immutable values already passed through one snapshot contract.
Consequences: Games and history remain stable when players disconnect or later change their lobby songs, and each domain keeps ownership of its tables. The service must validate references inside JSON and coordinate Game deletion before Rooms deletion in one transaction; schema constraints alone do not enforce every gameplay rule.

Reveal/failure clarification (2026-09-30): songs and frozen game snapshots keep an optional `artwork_url`, resolved from catalog metadata or a bundled demo asset. A missing/broken image shows a bundled placeholder without affecting scoring; SQLite stores references rather than image bytes. Failed clips retain their answers under a `void` attempt, and only `revealed` attempts contribute to live or final rankings. A replacement has its own attempt and answers.

Selected-answer clarification (2026-10-01; ADR-2/3): the user replaced four issued
song options with a broad catalog typeahead. A selected result carries verified
recording/title/artist facts in a room-scoped expiring token; submission freezes
those facts and performs no provider lookup. Pure scoring retains full-song and
structured artist partial credit. Migration 2 converts prior choice slots into
historical song facts without changing points. The public Apple metadata adapter
is separate from personal-history authorization and preview imports; the
2026-10-02 clarification below records their implemented provider boundary.
See `docs/03_GAME_RULES.md`, `docs/06_DATA_MODEL.md` and `docs/07_API_AND_RUNTIME.md`.

Presentation clarification (2026-10-01; ADR-3): one fluid blob rig replaces
separate shapes. The existing `character_id` field now holds one of eight color
IDs; migration 3 translates live players and frozen rosters while preserving
scores and history. Reveal song classification shares the scoring rule and drives
correct/artist/wrong/unanswered reactions without inferring correctness from
listener-inclusive total points.

Answer privacy clarification (2026-10-01; ADR-3): each player sees only their
own submitted song/listener selections and personal round feedback. Other
players' answers are never disclosed through game state, results or history;
the host has no exception. Correct-song/listener facts, named submission status
and ranking totals remain shared. SQLite retains every answer for scoring,
retries and diagnosis, including answers on void attempts whose points do not
count. Private storage does not imply a public answer feed.

## 4. Test core behavior through service, database and browser boundaries
Date: 2026-09-30
Status: Decided
Context: A working PoC, executable schema or coverage percentage does not prove the multiplayer game, shared audio or failure recovery works.
Decision: Test exact scoring/preparation with controlled randomness and clocks; test both domains through actual SQLite/service transactions; exercise retries, deadline/failure races, readiness exclusions, startup recovery and expiry. Require at least 70% Rooms/Game logic coverage and three real browsers completing a ten-round Demo game. Measure round-data preparation, required ACKs and common start delivery under two seconds in stated conditions, plus the approximately 400-state-polls/second capacity target. Browser checks cover audio, characters/statuses, automatic phases, reconnect and artwork fallback.
Alternatives considered: Mocked provider tests alone bypass service/persistence boundaries; coverage-only acceptance can miss races and physical audio. Enabling real imports or all-device audio from a functional PoC would skip capability/measurement gates.
Consequences: Keep scoring tests deterministic and use real temporary SQLite transactions for domain/lifecycle tests; thin HTTP integration tests verify cookies, authority and projections. Provider adapters now have isolated transport/import and admission tests in addition to the signed-search checks; real-account and browser physics/network acceptance cannot be inferred from coverage. Current evidence is in `docs/08_IMPLEMENTATION_STATUS.md`, separate from deployment readiness.

## 5. Keep the first milestone to Demo and shared host audio
Date: 2026-10-01
Status: Decided
Context: Personal music authorization, import sources and artist-credit completeness still need validation, while optional all-device audio needs measured physical playback and drift evidence. Building those paths from unverified PoC assumptions would make the first playable milestone harder to explain and test.
Decision: Implement explicit Demo with bundled original clips and shared host-device sound first. Defer real-provider admission, all-device playback, mashup rounds, game accounts and device/identity recovery; Normal returns a clear unavailable result until its real integration is validated.
Alternatives considered: A fake authorization flag or silent Normal-to-Demo downgrade would misrepresent whose listening data is being used. Adding account recovery and synchronized audio everywhere now would introduce identity and browser timing work before the core game is accepted.
Consequences: The backend runs locally without music credentials and both feature domains can be tested fully with isolated fixtures. The current four-song runtime seed supports lobby checks; catalog population and browser acceptance are required for a complete playable match. Demo familiarity is fictional, and Normal/personal-history and physical device acceptance remain visible follow-up gates; this is a milestone boundary rather than a claim that the full product is complete.


Provider checkpoint clarification (2026-10-02; ADR-2/3/5): the user chose one
Spotify development app with at most five approved accounts, including the host,
for Normal mode. Demo retains its ten-player capacity and separate fictional
assignments. Spotify PKCE imports each player's top/recent tracks without a
client secret; Apple developer credentials provide catalog search, charts and
preview resolution without requiring Apple login from each player. Search remains
rate-limited with cache/budgets and explicit HTTP 429 handling. Multi-app Spotify
and history-file imports are future options, not the current implementation.

`backend/music/` owns normalized provider transport, preview resolution, bounded
imports and expiring cookie-bound admission receipts. Provider I/O runs outside
SQLite transactions; Rooms atomically revalidates membership/capacity and admits
only after a usable verified import. Normal requires ten playable personal songs
and permits one room identity per Spotify account. Migration 4 stores room-scoped
account digests and song pool kinds, never OAuth tokens. Observed unplayable songs
retain listener ownership if a later import supplies media. Incompatible title/
version or credited artists sharing a mislabeled ISRC receive distinct variant
identities. Frozen recording keys and verified credited-artist aliases support
cross-provider scoring; ISRC alone cannot award full song credit. Shared title
normalization handles Unicode/punctuation and trailing featured-credit labels
while preserving live/remix/instrumental/remaster distinctions.
Existing private-answer, roster, void-attempt and replacement rules remain.

The earlier Demo-only decision described the first milestone; this checkpoint
adds the explicit Normal provider path. The redesigned UI checkpoint is committed
at `a05e19e`; this provider checkpoint follows it on the same branch.
Live Apple catalog/reference checks passed, and native browser Web Audio decoded
a real Apple preview; physical audibility was not inferred from decoding.
Five Spotify account authorization, exact application callback registration/
allowlisting, complete-match browser decoding and
physical audio acceptance remain separate; the user deferred real-account setup
and QA until returning. See `docs/13_SPOTIFY_IMPLEMENTATION.md` and
`docs/08_IMPLEMENTATION_STATUS.md`.
