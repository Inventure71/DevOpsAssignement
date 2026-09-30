# 07 — API and Runtime Contract

Date: 2026-09-30. Accepted gameplay decisions and API/runtime contracts.
Demo endpoints now exist; real provider admission is explicitly unavailable.
See [implementation status](08_IMPLEMENTATION_STATUS.md) for test evidence. Read alongside [03_GAME_RULES.md](03_GAME_RULES.md),
[05_ARCHITECTURE.md](05_ARCHITECTURE.md) and
[06_DATA_MODEL.md](06_DATA_MODEL.md).

## 1. Participants and admission

The host is a player and the sole room admin. Everyone uses their own browser
for guesses, reveals and rankings. The host device plays the shared audio;
there is no required presenter display or host transfer in v1.

Choose `normal` or `demo` at room creation, before players join. Normal admission
requires verified personal music authorization for every player, including the
host. The server validates authorization rather than accepting a browser's
`music_connected=true` claim. Demo bypasses that authorization and assigns
hidden songs from seeded SQLite fixtures. A normal import failure never silently
switches mode. Mode cannot change under admitted players in v1; create a new room
for a different mode.

The backend imports each player's songs once per lobby pool build, using that
player's authorization. Imports/checks complete before Start is enabled. The
host's account alone cannot supply other players' history. Provider selection,
source-list policy, familiarity mapping and candidate quantities remain pending;
provider-specific authorization routes follow that validation. Do not make
external import calls part of a promised five-second countdown.

## 2. Browser identity and authorization

Generate a random room-specific credential and store only its digest in Rooms.
Use an `HttpOnly`, `SameSite=Lax` cookie, with `Secure` in HTTPS deployments and
`Path=/api/rooms/{room_id}` so joining a second room does not overwrite the first
credential. Cookies must have distinct room-specific names as well. All protected
room API routes share this prefix; local plain-HTTP development is the explicit
exception to `Secure`. Cookie lifetime must not exceed room retention and expiry
is checked server-side regardless of whether a browser keeps a cookie.
Refresh its expiry after a completed game renews the room lifetime; never renew
room retention merely because a cookie, poll or heartbeat is refreshed. These
flags follow the [cookie contract](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Refresh and another tab in the same browser recover the same player. Nicknames
are not credentials. No identity recovery/device transfer exists in v1. A fresh
identity can join only in the lobby with a unique normalized nickname; it cannot
join a running game. Lost cookies do not let a browser reclaim the host nickname
or authority. Provider tokens and browser credentials are never placed in URLs,
localStorage, snapshots, command receipts or logs.

Room codes are six random characters from an unambiguous uppercase letter/digit
alphabet; retry collisions. A code allows lobby admission and access to final
ranking history, not administrative authority. Every protected request resolves
its credential, checks room membership, then checks host status when required.
Apply configurable room-creation/join limits. Unsafe requests use same-origin
JSON plus Origin validation; reject untrusted cross-origin requests and do not
configure permissive credentialed CORS.

## 3. Suggested API surface

`/api` is the v1 API prefix; incompatible future changes receive a separate
version rather than changing this contract silently. Bodies use opaque IDs and
UTC milliseconds. State responses include `server_now_ms`, monotonically
increasing `state_version`, phase and applicable deadlines. Clients ignore older
poll responses. Domain internals and provider credentials are not API models.

| Method and path | Access | Effect |
|---|---|---|
| `POST /api/rooms` | Admission checks, including normal host authorization | Create room with mode, host nickname/character; issue host cookie |
| `GET /api/room-codes/{code}` | Code holder | Resolve room ID/mode/join availability; no hidden pool or host privileges |
| `POST /api/rooms/{room_id}/join` | Valid code and admission proof | Join lobby, issue room cookie; no new identities during preparing/play |
| `GET /api/rooms/{room_id}/state` | Member | Current public phase plus caller-specific submission/admin state |
| `POST /api/rooms/{room_id}/heartbeat` | Member | Update presence after enforcing expiry |
| `PATCH /api/rooms/{room_id}/player` | Member, lobby only | Update own nickname/character |
| `PATCH /api/rooms/{room_id}/settings` | Host, lobby only | Validate settings and advance room revision |
| `POST /api/rooms/{room_id}/start` | Host | Idempotently freeze roster/settings and create preparation |
| `POST /api/rooms/{room_id}/games/{game_id}/end` | Host | Abort the game with partial rankings, keeping host/room membership for another game |
| `POST /api/rooms/{room_id}/games/{game_id}/preload-check` | Active host controller, setup only | Report loading/decoding outcomes for server-issued candidates before freezing the final plan |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/ready` | Starting player | Automatic ACK scoped to the current readiness generation |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/answers` | Starting player | Immutable final submission |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/retry` | Host | New readiness generation for the same unstarted attempt |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/continue` | Host | Exclude specified unready non-host players from barrier only |
| `POST /api/rooms/{room_id}/audio-controller` | Host | Claim/renew/release one host-tab playback lease |
| `GET /api/rooms/{room_id}/games/{game_id}/audio` | Active host controller | Private setup/current playback references; no listener maps |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/audio-failure` | Active host controller | Report current unclosed playback failure; void/replace as allowed |
| `POST /api/rooms/{room_id}/leave` | Member | Host aborts immediately; non-host departure preserves frozen game identity |
| `GET /api/room-codes/{code}/history` | Code holder | Final rankings with completed/aborted labels; no detailed guesses/pools |
| `GET /health/live`, `GET /health/ready` | Probe | Process liveness / initialized usable database and runtime readiness |

Credential cookies are issued at the protected room path even by the creation
endpoint. Protected history or later provider routes also use that prefix.
Normal-mode admission proof must be verified, short-lived and scoped to the
joining flow; its concrete provider protocol remains a real-integration gate.
Do not implement a placeholder accepting arbitrary authorization claims.

## 4. Phase-specific state

| Phase | Public information |
|---|---|
| Lobby | Mode, nickname/character, connectivity, import readiness, counts/settings, Start eligibility |
| Setup | Frozen roster, requested round count, preparation progress/errors, minimum setup countdown |
| Ready/countdown | Current four title/credited-artist options, frozen roster, automatic check-in progress, readiness generation, common start time when scheduled |
| Answering | Same options/roster, deadline, named Listening/Submitted statuses and caller's own receipt |
| Reveal | Correct song/credited artists/cover, real listeners, every player's guesses or No answer, per-player points |
| Leaderboard | Revealed-attempt totals and ranks, next phase timing |
| Finished | Persisted final or labelled partial rankings and end cause |

Do not expose correct-option markers, listener membership, per-song familiarity
or other guesses before reveal. Nicknames and characters come from the frozen
roster during games. Listening/Submitted describes answer state, not proof of
audible listening; show connectivity separately. Missing submissions become
No answer at closure. Failed cover loading uses the bundled placeholder.

Only the active host audio tab receives full planned/reserve audio references
for setup preloading. Non-hosts receive no future-round song data. Provider URLs
and cached media can disclose metadata to a host inspecting their own browser;
shared host playback cannot promise cryptographic song secrecy from the host.
Do not include future title/artist labels, correct markers or listeners in the
public response or audio preload manifest.

## 5. Full-game setup and replacements

Start freezes membership/settings and creates a `preparing` game. Normal imports
are already complete. Game selects the complete requested sequence and reserves,
checks preview candidates and four-option feasibility, then freezes song facts
and `round_plan_json`. The host loads/decodes planned and reserve clips as far as
the supported browser permits. Explicitly enable host audio through a user tap;
loading a URL alone does not prove audible playback.
The host automatically reports loading/decoding outcomes through `preload-check`,
scoped to the current preparation and private candidate manifest; reports cannot
introduce arbitrary songs/URLs. Persist outcomes/substitution use before freezing
the plan. Implementation must bound this host-validation window as well as
provider checks, rather than wait forever for a missing report. Its configured
timeout returns setup to the lobby with a host-preparation error; it does not
consume or reset the later ten-second round-readiness window. Tune this separate
whole-game preload limit using supported-browser measurements, not NFR1.

Each original requested slot has one initial candidate plus up to three distinct
replacement candidates. This budget is shared between setup and runtime recovery,
never reset after a failed attempt. Skip a slot if no candidate succeeds. Cancel
when `skipped_original_slots / original_requested_count > 0.30`:
5 rounds allow 1 skip, 10 allow 3, 15 allow 4. Exactly 30% is allowed. Show the
actual playable count; preserve original slot numbers and disclose that skips
can change the surviving decoy proportion. Never replay an already failed/played
song or retrieve new provider candidates in the normal per-round path.

The five-second setup countdown is a minimum; show Preparing if validation or
host preloading takes longer. Initial readiness has its own ten-second limit,
not an unlimited external-provider deadline. An initial timeout aborts setup,
returns the room to the lobby and names all players whose ACKs are missing.

## 6. Automatic readiness and synchronization

An ACK is sent by browser code, not a manual button. It identifies `round_id` and
`readiness_generation`; repeated identical ACKs succeed, stale generations fail.
ACKs confirm current round data is prepared; host ACK additionally needs a valid
audio lease and local audio readiness. State versions order display responses,
but do not scope ACK validity: one player's ACK must not invalidate another's.

Initially every starting player is required. For later rounds, a ten-second
window starts only with the host present; wait for host return under the agreed
grace before opening it. If required ACKs remain missing, retain the same
unstarted attempt and let the host choose:

- **Retry:** clear previous check-ins, increment generation, open a fresh
  ten-second window and require the full starting roster again.
- **Continue without named unready players:** exclude only the chosen non-host
  missing-ACK players from this generation's barrier. Continue once every
  remaining required player ACKs. Exclusions expire at the next round/generation.

Neither action creates an answer or points. Excluded players retain roster
identity, previous scores, leaderboard position and answer eligibility. They may
reconnect and answer before the deadline. The early-close condition still counts
all starting players; otherwise their missing answer becomes zero at timeout.
Host audio readiness cannot be excluded. Show affected nicknames and a waiting
state on all clients; administrative buttons appear only to the host.

When required ACKs arrive, publish one future start time, three seconds ahead.
Browsers estimate server-clock offset from timestamped responses and show that
countdown. ACKs alone do not synchronize clocks, guarantee perfect simultaneity
or prove audio will play. Measure supported-browser start drift; do not claim
all-device synchronized audio from this shared-host-audio design.

## 7. Answers, time and scoring

Accept one immutable final answer per starting player per attempt. Payload:
`song_option` (0–3 or null) and `who_player_ids` (unique frozen-roster IDs).
A submitted empty list means Nobody; an omitted song earns zero song points.
No Submit by closure means `missing`, `blank` and zero total points. Reject
out-of-roster IDs, malformed options and requests outside the answering phase.

An identical repeat returns the original receipt, including after closure; it
cannot rescore. A different second payload conflicts. Attempts have separate
answer identities. This is semantic answer idempotency, not permission to
change answers through a new request ID.

Server acceptance is serialized per room. Capture `received_at_ms` after gaining
the room's command turn and before insertion; accept only
`starts_at_ms <= received_at_ms < deadline_at_ms`. Client send times do not decide
acceptance/speed points. Request queueing/network delay therefore affects score;
keep command work short and measure it. Enforce due transitions before mutation.
At all-roster submission or deadline, close and score once in one transaction.
Stop audio, show reveal for five seconds, then leaderboard for five seconds.

Correct song earns 100 plus the existing server-timed speed bonus. A wrong song
sharing at least one structured credited-artist identity with the correct song
earns 50, no speed bonus and no perfect-round bonus. Other wrong songs earn zero.
Listener/difficulty/exact half-up rules remain in [03_GAME_RULES.md](03_GAME_RULES.md).
Artist identities are provider-qualified IDs (or stable demo IDs), not substring
matches against display names; validate real cross-provider reconciliation before
using it. Frozen options include the matching facts needed by Game, but browser
responses never mark shared correctness.

## 8. Failure, presence and command retries

Prevalidation reduces clip failures; browser playback/network/device failures
remain possible. Host reports are accepted for the current `ready`/`playing`
attempt before closure. A failed attempt becomes `void`; retain submitted answers
and any diagnostic points, exclude them from every ranking, and use only the
remaining checked reserves/budget for that original slot. A replacement is a new
attempt with a new readiness generation. If exhausted, skip the slot; cumulative
skips exceeding 30% abort with a clear error and labelled partial rankings.
Revealed attempts are final; late reports cannot invalidate them.

Send presence heartbeats every five seconds. Polling and readiness ACKs are not
heartbeats. Host grace is sixty seconds from the last accepted heartbeat. Check
expiry before accepting a returning heartbeat. During absence, a scheduled round
can finish; phase progression must not open a new readiness window until return.
Explicit host leave aborts immediately. Non-host disconnects never remove frozen
identities. No host transfer exists in v1.

Only one host tab holds an audio-controller lease. Claim/takeover is explicit;
renew it alongside the host's heartbeat. The old lease cannot ACK/report playback
or control a new lease's attempt. A refresh that interrupts unclosed playback
voids that attempt; merely restoring the same browser credential does not prove
playback continued. Startup reconciliation handles crashes the browser cannot
report. Grace duration does not grant a second competing audio controller.

Host Start, End, preload reports, Retry, Continue, audio failure and Leave use `request_id` and expected
attempt/generation where applicable. Store durable accepted command receipts in
Game's `game_commands`, bound to actor, type and normalized payload; repeated
identical requests return their outcome. Reusing an ID with a different payload
conflicts. `games.start_request_id` deduplicates Start even across a lost response
and process restart. Commands never apply blindly to whichever round is current.
Minimal receipt results contain effects/IDs, not private audio or credentials.

Use structured errors `{error: {code, message, retryable, details}}`, with stable
codes for identity/host failures, stale commands, readiness timeout, missing
provider authorization, setup cancellation and deadline closure. Do not name a
player as the cause of a provider-wide/database failure; timeout names apply to
missing client ACKs. HTTP statuses reflect validation, authorization, conflict,
expiry/rate limits and infrastructure failure consistently.

## 9. Process, database and operations

Run one worker and one replica, binding `0.0.0.0` on `PORT`. Persist SQLite under
`DATA_DIR` on a compatible durable local volume. Validate the chosen Azure storage
and restore behavior; WAL is not a blanket solution for network-mounted storage.
Enable foreign keys and a busy timeout per connection. Database connections/
transactions execute outside the async event loop. Serialize room mutations;
never hold SQLite transactions or room locks during provider calls.

FastAPI lifespan initializes bounded versioned migrations, demo fixture seed and
startup recovery before readiness succeeds. A one-second presence/deadline task
advances phases without browser requests; a periodic task enforces whole-room
retention. Requests also reject expired rooms/deadlines. Cancel/await tasks and
close resources on shutdown. This is in-process orchestration, not another worker.
Use [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) for these
startup/shutdown boundaries. The [SQLite WAL contract](https://www.sqlite.org/wal.html)
explains why storage compatibility and consistent backup matter.

On restart, reconcile preparing/playing games in a local transaction: void any
interrupted unclosed attempt, preserve revealed results, abort with server-restart
cause and save labelled partial ranks, restore surviving rooms to lobby, and
clear obsolete audio/readiness ownership. Never pretend the game completed or
extend retention for an abort. Game data is deleted before Rooms data on expiry,
in one transaction. Completed games alone renew the retention anchor.

Liveness tests process response; readiness checks schema/database accessibility
and required runtime initialization, not optional provider uptime. Log bounded
IDs, phases, latency, cause codes and provider availability without credentials,
unrevealed guesses, song/listener pools or private playback URLs. Collect round
preparation/ACK/start, audio failure and SQLite contention timings. Back up through
a SQLite-consistent method including active WAL contents; verify a restore.
Operational thresholds/configuration and provider adapters still need deployment
validation. No new hosted service is required for demo.

## 10. Verification contract

| Check | Required evidence |
|---|---|
| Admission/identity | Room-specific cookies, host-only controls, normal verified admission, demo bypass, midgame new-identity rejection |
| Setup | Full sequence/reserves frozen; three replacements shared across setup/recovery; strict 30% boundary and original denominator |
| Readiness | Automatic ACKs, stale/duplicate generations, initial named timeout, later Retry/Continue, host cannot be excluded |
| Scoring | Worked examples, artist overlap/none, correct title/full points, empty submitted Nobody versus no submission |
| Races/retries | Deadline boundary, answer/close/failure race, identical receipts, changed-answer conflict, lost Start response/restart |
| Recovery | Host grace/lease takeover, missing players retaining eligibility, refresh/void, revealed finality, restart and partial rankings |
| Browser game | Three real browsers complete ten demo rounds with characters, named statuses, automatic phases, host audio and cover fallback |
| Load/timing | About 400 state polls/second plus commands/heartbeats, no overlapping polls, database contention and server event-loop responsiveness |
| Operations | Durable data, health probes, migrations/startup recovery, consistent backup/restore, expiry without requests |

The two-second round target starts when the server begins preparing the current
round payload and ends after required client ACKs and common start-time delivery
are confirmed in the test trace. It includes public data delivery and automatic
check-ins, not provider import, prior full-game preload or the subsequent
three-second countdown. Measure all required clients under stated network/device
conditions; missed ACKs fail the target and trigger the ten-second recovery
limit. Publishing a timestamp alone is not proof every client received it.
Client traces record received start times for validation; scoring remains server
owned. Timing/coverage targets are planned acceptance gates, not passed results.

Real music admission/import must wait for provider capability/authorization,
familiarity and candidate-quantity decisions. Demo foundation, pure scoring,
persistence, room identity, phase/readiness services and their tests can be built
against this contract. All-device audio and detailed history screens remain
outside the first milestone.

## 12. Implemented Demo transport details

Start includes `request_id`, `room_revision` and the active host `lease_id`.
Preload reports include `request_id`, `candidate_id`, `ok` and `lease_id`; the
manifest uses the `X-Audio-Lease` header. Ready includes `readiness_generation`
and, for the host, `lease_id`. Answer includes nullable `song_option` (0–3) and
`who_player_ids`; an empty list is submitted Nobody. Host recovery commands
include `request_id` and `readiness_generation`. Continue names all currently
unready non-host IDs in `exclude_player_ids`; Retry opens a fresh window.
Audio failure additionally includes `lease_id` and a bounded diagnostic `reason`.

Browser audio uses fetch plus Web Audio decoding of every issued candidate,
then schedules the active buffer at the common start time. The setup preload
window defaults to 60 seconds (`SETUP_TIMEOUT_MS` tunes it within 10–120 seconds). Missing reports abort with
`host_preparation_timeout`; complete reported failures use the strict skip rule.
Current implementation settings are process-local in the lobby and frozen in
SQLite at Start. Restart restores the last frozen settings, or defaults.
Controller renewal uses its tab ID every five seconds. An unchanged tab may
renew an unclaimed lease after a delay; a different tab receives a new lease and
voids any unclosed current attempt. Late lease holders cannot use the new lease.

See `backend/api/schemas.py` for strict request models,
`backend/api/routes.py` for HTTP handlers, and `backend/game/views.py` for public
projections. Origin checks, room cookies and rate limits live in separate
`backend/api/` modules; cross-domain commands enter `backend/application/coordinator.py`.
Normal requests return `provider_unavailable`; they accept no fabricated
authorization proof. Physical audio and readiness/load targets remain separate
acceptance gates.
