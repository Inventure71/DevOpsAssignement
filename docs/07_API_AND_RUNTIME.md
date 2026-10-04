# 07 — API and Runtime Contract

Updated 2026-10-04. Current gameplay and API/runtime contracts. Complete offline
Demo and Normal Spotify PKCE/import admission are implemented, with Apple catalog
search/previews and durable public metadata verification. Physical-device and
real-account acceptance remain separate from automated HTTP verification.
Read alongside [03_GAME_RULES.md](03_GAME_RULES.md),
[05_ARCHITECTURE.md](05_ARCHITECTURE.md) and
[06_DATA_MODEL.md](06_DATA_MODEL.md).

## 1. Participants and admission

The host is a player and the sole room admin. Everyone uses their own browser
for guesses, reveals and rankings. The host device plays the shared audio;
there is no required presenter display or host transfer in v1.

The launch selects a `GAME_MODE` profile: `demo` allows only Demo; `normal` also
allows configured Spotify. Demo is always available. `GET /api/config` exposes
that profile and enabled/reason values for both creation options. The browser
shows both but disables unavailable Spotify; application commands also reject
Spotify creation, joins and restored sessions under the Demo-only launch with
`mode_unavailable` (409).
Demo uses local HTTP without provider settings; Normal uses configured shared
HTTPS and rejects insecure session requests before admission.

Choose the available room type before players join. Normal admission
requires verified personal music authorization for every player, including the
host. The server validates authorization rather than accepting a browser's
`music_connected=true` claim. Demo bypasses that authorization and assigns
36 personal songs per player from the pinned 80-song personal pool; 20 independent
decoys supply Nobody rounds. The complete Demo catalog contains 100 recordings. A normal import failure never silently
switches mode. Mode cannot change under admitted players in v1; create a new room
for a different mode.

The backend imports each player's songs once per lobby pool build, using that
player's authorization. Imports/checks complete before Start is enabled. The
host's account alone cannot supply other players' history. Normal uses one
Spotify development app with at most five approved accounts including the host;
this account allowance applies across rooms. Demo permits ten players. Spotify
supplies short/medium/long top lists and recently played tracks, balanced into
at most 60 distinct candidates; admission needs at least ten playable songs.
Short-term top 20 are easy, other short/medium/recent tracks medium, and
long-term-only tracks hard, with the easiest overlap winning. These are bounded
affinity-based estimates. Apple supplies preview matches and independent chart
candidates. Do not make external imports part of a promised five-second countdown.

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

## 3. API surface

`/api` is the current active-development API prefix. The selected-song contract
replaces the earlier option-slot draft; no legacy option-answer compatibility
path is retained. Released APIs will need explicit versioning for incompatible changes. Bodies use opaque IDs and
UTC milliseconds. State responses include `server_now_ms`, monotonically
increasing `state_version`, phase and applicable deadlines. Clients ignore older
poll responses. Domain internals and provider credentials are not API models.

The service exposes `/docs` and `/openapi.json` for API discovery, serves catalog
assets at `/static/demo/local`, and serves the frontend at `/` with its assets at
`/ui`. After one-time pinned pack installation, Demo supports default ten-round
and optional fifteen-round matches offline without provider credentials. Start still requires at
least ten songs per player; public search does not add songs to a game pool.

| Method and path | Access | Effect |
|---|---|---|
| `GET /api/config` | Entry browser | Launch profile and enabled/reason values for Demo and Spotify; no secrets |
| `GET /api/demo/preview` | Public metadata | One active Demo catalog sample for the UI lab; title, artist, local preview URL and optional artwork; no player listening evidence |
| `POST /api/rooms` | Demo admission | Create Demo room with host nickname/character; issue host cookie. Normal requires the Spotify admission flow below |
| `GET /api/room-codes/{code}` | Code holder | Resolve room ID/mode/capacity/join availability; no hidden pool or host privileges |
| `GET /api/music/spotify/config` | Entry browser | Configuration availability, minimum/maximum players, playtest flag, canonical application URL, search provider and `requires_shared_url` for LAN browsers facing a loopback callback; no secrets |
| `POST /api/music/spotify/admissions` | Same-origin JSON, admission checks | Begin cookie-bound PKCE for nickname/character and optional target room; return Spotify authorization URL |
| `GET /api/music/spotify/callback` | Matching admission cookie and one-use OAuth state | Queue verified import, redirect to processing UI; invalid callback goes to a generic verification error |
| `GET /api/music/spotify/status` | Matching admission cookie | Pending/processing/failed/complete receipt; complete issues room cookie and returns room/code/player IDs |
| `POST /api/music/spotify/cancel` | Same-origin JSON | Cancel unfinished receipt and clear temporary cookie; cancelled import cannot create a room |
| `POST /api/rooms/{room_id}/join` | Demo admission or an existing member's room cookie | Join Demo lobby or restore existing identity; new Normal identities receive `music_sign_in_required` |
| `GET /api/rooms/{room_id}/state` | Member | Current public phase plus caller-specific submission/admin state |
| `GET /api/rooms/{room_id}/song-search?q=...` | Member | Search shared Demo/configured Apple catalog metadata; return signed selections without room-pool/listener data |
| `POST /api/rooms/{room_id}/song-selection` | Member | Resolve a signed bulk metadata reference into a verified provider selection; cache successful public identity links |
| `POST /api/rooms/{room_id}/heartbeat` | Member | Update presence after enforcing expiry |
| `PATCH /api/rooms/{room_id}/player` | Member, lobby only | Update own nickname/character |
| `PATCH /api/rooms/{room_id}/settings` | Host, lobby only | Validate settings and advance room revision |
| `POST /api/rooms/{room_id}/start` | Host | Idempotently freeze roster/settings and create preparation |
| `POST /api/rooms/{room_id}/games/{game_id}/end` | Host | Abort the game with partial rankings, keeping host/room membership for another game |
| `POST /api/rooms/{room_id}/games/{game_id}/preload-check` | Active host controller, setup only | Report loading/decoding outcomes for server-issued candidates before freezing the final plan |
| `POST /api/rooms/{room_id}/games/{game_id}/preparations/{preparation_id}/ready` | Starting player | Renewable upcoming ACK during results; browser ID/generation required, active host lease required for host |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/ready` | Starting player | Automatic ACK scoped to the current readiness generation |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/answers` | Starting player | Immutable final submission |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/retry` | Host | New readiness generation for the same unstarted attempt |
| `POST /api/rooms/{room_id}/games/{game_id}/rounds/{round_id}/continue` | Host | Exclude specified unready non-host players from barrier only |
| `POST /api/rooms/{room_id}/audio-controller` | Host | Claim/renew one host-tab playback lease; explicit takeover replaces its owner |
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

`character_id` selects a color for the shared blob rig: `coral`, `periwinkle`,
`lavender`, `lemon`, `lilac`, `sage`, `sky` or `rose`. Admission defaults to coral;
lobby edits persist the caller's own color. Starting roster colors are frozen.

The caller's revealed answer includes `song_match`: `correct`, `artist`, `wrong` or
`unanswered`, computed from frozen song facts with the scoring classifier.
Missing and submitted listener-only answers both have unanswered song matching,
while their answer status remains distinct. The field is withheld before reveal.
The frontend celebrates correct songs, responds happily to artist partial credit,
uses sadness for wrong songs and stays neutral for unanswered songs. Listener
points do not decide the emotion.

| Phase | Public information |
|---|---|
| Lobby | Mode, nickname/character, connectivity, import readiness, counts/settings, Start eligibility |
| Setup | Frozen roster, requested round count, preparation progress/errors, minimum setup countdown |
| Ready/countdown | Current waveform (if supplied), frozen roster, automatic check-in progress, readiness generation, common start time when scheduled |
| Answering | Same waveform/roster, deadline, named Listening/Submitted statuses and caller's own receipt |
| Reveal | Correct song/credited artists/cover, real listeners, caller's own guesses or No answer, caller's own correctness and points |
| Leaderboard | Revealed-attempt totals and ranks, next phase timing |
| Finished | Persisted final or labelled partial rankings and end cause |

Do not expose correct-song flags, listener membership or per-song familiarity
before reveal. Never expose another player's submitted song guess or listener
selection in any phase, results or history; the host has no exception. Keep all
answers internally for scoring, retries and diagnosis, including answers on void
attempts. Shared submission status and ranking totals do not disclose their
underlying answer rows. Nicknames and characters come from the frozen
roster during games. Listening/Submitted describes answer state, not proof of
audible listening; show connectivity separately. Missing submissions become
No answer at closure. The frontend must use the inline music-icon fallback for
missing or failed covers.

Only the active host audio tab receives full planned/reserve audio references
for setup preloading. Non-hosts receive no future-round song data. Provider URLs
and cached media can disclose metadata to a host inspecting their own browser;
shared host playback cannot promise cryptographic song secrecy from the host.
Do not include future title/artist labels, correct markers or listeners in the
public response or audio preload manifest.

## 5. Full-game setup and replacements

Start freezes membership/settings and creates a `preparing` game. Normal imports
are already complete. Game selects the complete requested sequence and reserves,
checks distinct preview candidates and replacement availability, then freezes song facts
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

An ACK is sent by `application/round-readiness.mjs`, not a manual button. Guests
acknowledge current state independently of the host audio adapter. Host readiness
also needs the decoded clip, running audio context and active lease. Session/generation cancellation
prevents stale responses from updating a later room or readiness window.
An ACK identifies `round_id` and
`readiness_generation`; repeated identical ACKs succeed, stale generations fail.
ACKs confirm current round data is prepared; host ACK additionally needs a valid
audio lease and local audio readiness. State versions order display responses,
but do not scope ACK validity: one player's ACK must not invalidate another's.

During reveal and leaderboard, visible browsers renew `upcoming_round` check-ins
every two seconds through `application/upcoming-readiness.mjs`. The guest
projection contains only its ID, round number and readiness generation; the host
also receives the candidate ID. Promotion carries only acknowledgements no older
than five seconds from connected players, with a matching current audio lease for
the host. When all required participants are prepared, leaderboard ends directly
in the three-second countdown. A late request for a consumed preparation returns
409; it cannot acknowledge a promoted round or start playback early.

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
`song_guess_token` (a signed search-result token or null) and `who_player_ids`
(unique frozen-roster IDs).
A submitted empty list means Nobody; an omitted song earns zero song points.
No Submit by closure means `missing`, `blank` and zero total points. Reject
out-of-roster IDs, malformed/tampered/other-room selections and requests outside
the answering phase. New selections must not be expired at acceptance. Store
the authenticated selected-song facts in `song_guess_json`; never make a provider
request during submission or closure.

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

Full song credit requires the same nonempty stable song/track key, or normalized
title and at least one common frozen structured artist key/alias. Shared title
normalization uses Unicode decomposition, case folding, diacritic removal and
word-based punctuation/whitespace handling; it removes only trailing bracketed
or parenthesized featured credits. Live/remix/instrumental/remaster labels remain
distinct. Do not use fuzzy matching or accept ISRC equality alone.
Correct song earns 100 plus the existing server-timed speed bonus. A wrong song
sharing at least one structured credited-artist identity with the correct song
earns 50, no speed bonus and no perfect-round bonus. Other wrong songs earn zero.
Listener/difficulty/exact half-up rules remain in [03_GAME_RULES.md](03_GAME_RULES.md).
Artist identities are provider-qualified IDs (or stable demo IDs), not substring
matches against display names; validate real cross-provider reconciliation before
using it. Apple developer relationships provide structured credits; preview
matching can attach verified Apple ID aliases to canonical Spotify credits when
credited names agree. Full recording credit requires a matching frozen key or
compatible normalized title with a shared structured key/alias; ISRC alone is
insufficient because catalog identifiers can be mislabeled.
Public iTunes fallback provides only its primary artist ID; featured credits are
not inferred from display strings. Imports retain frozen keys and aliases. Browser search responses do
not mark correctness. Game state exposes only the caller’s own `song_guess`
display facts and listener selection; reveal adds their own correctness and points.

### Public song search

`GET /api/rooms/{room_id}/song-search?q=...` authenticates the room member before
searching. A normalized query contains 2–100 characters. Browser Search/Enter
explicitly sends a query; typing alone sends no requests. The client uses
`local=true`, preferring the shared metadata index before a provider fallback.
A successful selectable response has this shape:

```json
{
  "songs": [{"token": "signed-selection", "title": "Billie Jean", "artist": "Michael Jackson", "artwork_url": null}],
  "source": "apple",
  "cached": false
}
```

Matching shared Demo fixtures return `source: "catalog"` and work offline.
Normal never substitutes Demo fixture suggestions. Other queries use the
configured Apple developer catalog, requesting up to 20 songs with structured
artist relationships. Without Apple configuration, Demo retains public iTunes
Search with `media=music`, `entity=song` and at most 20 results. Results are
independent of hidden room membership/listeners and the selected game sequence.
Responses contain signed metadata, never provider preview URLs; the search path
does not download audio. See [Apple catalog search](https://developer.apple.com/documentation/applemusicapi/search-for-catalog-resources)
and the [public Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html).

The process shares a five-minute, 128-query memory cache and coalesces identical
in-flight lookups. Successful provider query coverage is also persisted for a day;
empty coverage expires sooner. Public metadata and permanent verified links
survive process restarts. Configured Apple catalog search has a local
60-request/minute protective budget; public iTunes fallback has 18/minute.
These local budgets are implementation safeguards, not guaranteed provider quotas. External I/O has
a four-second timeout and bounded response size. Provider failures are cached
for ten seconds; auth/unavailability errors remain explicit and Apple HTTP 429
returns `apple_rate_limited`. Local exhausted budget returns `song_search_busy`
(429). Successful empty results remain a distinct 200 response. Search runs
outside the room command lock and outside write transactions.

Bulk MusicBrainz metadata can return `resolve_required: true`. Selecting it calls
`POST /api/rooms/{room_id}/song-selection` with its signed token. Positive matching
stores every supported target in the provider/storefront scope, separately for
guessing and recording resolution. Unchanged successful verification has no
time-based expiry; fingerprints and matching-rule version control validity.
Temporary preview URLs expire separately. Answers reject unresolved references;
submission and closure never wait for a provider. Public search receives permitted
Demo fixture values through `RoomCommands`, with no SQL access to private Rooms
or listener tables.

Each token authenticates normalized song facts, room ID and a twenty-minute
expiry using the process's in-memory signing secret. The browser cannot replace
metadata or reuse a token in another room. The API verifies the signature; Game
checks expiry for a new answer after checking for an identical stored receipt.
Thus an accepted identical retry remains idempotent after closure or token expiry.
Search tokens are not music-provider credentials and are not persisted in SQLite.
Restart rotates the secret while aborting interrupted matches; do not depend on
old selections to start or continue a game after restart.

`round.my_answer` is null until submission; afterwards it contains
`{song_guess: {title, artist, artwork_url} | null, who_player_ids: [...]}`.
The reveal object is `{song, listener_ids, my_answer}`. `song` contains the
correct song's display facts; `listener_ids` contains its actual frozen listeners.
`reveal.my_answer` belongs only to the authenticated caller and contains
`{player_id, status, points, song_guess, song_match, who_player_ids}`. A missing
answer has `status: "missing"`, `points: 0`, `song_guess: null`,
`song_match: "unanswered"` and `who_player_ids: null`. A submitted Nobody answer
has `status: "submitted"` and `who_player_ids: []`. No `answers` list, other
players' selections, round options or correct-option index are sent, including
to the host. All underlying answer rows remain stored privately.

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
`DATA_DIR/whos_on_repeat.sqlite3`, the single active database path, on compatible
local storage. Assignment 1 uses a local process; any future Azure deployment
must separately validate volume and restore behavior. WAL is not a blanket
solution for network-mounted storage.
Enable foreign keys and a busy timeout per connection. Database connections/
transactions execute outside the async event loop. Serialize room mutations;
never hold SQLite transactions or room locks during provider calls.

FastAPI lifespan applies application migrations 1 through 6, preserving retained
answer facts, character values and account constraints. Catalog schema version 3
is tracked separately in `component_schema_versions`, preserving the application's
`PRAGMA user_version=6`. Startup validates the installed Demo pack and initializes
the Demo seed, recovery and public catalog before readiness succeeds. There is no
separate-catalog import path. The launcher installs a missing pinned pack before
starting the process; runtime startup never downloads Demo music. A one-second presence/deadline task
advances phases without browser requests; a periodic task enforces whole-room
retention. Requests also reject expired rooms/deadlines. Cancel/await tasks and
close resources on shutdown. This is in-process orchestration, not another worker.
`GameService` owns timed transitions; application coordination invokes them and
reconciles room state. Scoped `RoomLocks` retains entries only while holders or
waiters exist. Requests pass through injected `RoomCommands`/`GameCommands`,
leaving HTTP concerned with transport values rather than SQL/workflows.

On restart, reconcile preparing/playing games in a local transaction: void any
interrupted unclosed attempt, preserve revealed results, abort with server-restart
cause and save labelled partial ranks, restore surviving rooms to lobby, and
clear obsolete audio/readiness ownership. Never pretend the game completed or
extend retention for an abort. Game data is deleted before Rooms data on expiry,
in one transaction. Completed games alone renew the retention anchor.

Liveness tests process response; readiness checks schema/database accessibility
and required runtime initialization, not optional provider uptime. Log bounded
IDs, phases, latency, cause codes and provider availability without credentials,
private guesses, song/listener pools or private playback URLs. Collect round
preparation/ACK/start, audio failure and SQLite contention timings. Back up through
a SQLite-consistent method including active WAL contents; verify a restore.
Operational thresholds/configuration and provider adapters still need deployment
validation. `requirements.txt` is the single root dependency manifest for runtime
and verification; native browser modules require no npm build. Startup accepts
environment configuration without a required `.env` file or manual migrations.
No authored Docker/CI workflow or hosted service is required for Assignment 1.

## 10. Verification contract

| Check | Required evidence |
|---|---|
| Admission/identity | Room-specific cookies, host-only controls, normal verified admission, demo bypass, midgame new-identity rejection |
| Setup | Full sequence/reserves frozen; three replacements shared across setup/recovery; strict 30% boundary and original denominator |
| Readiness | Automatic ACKs, stale/duplicate generations, initial named timeout, later Retry/Continue, host cannot be excluded |
| Scoring | Worked examples, artist overlap/none, correct title/full points, empty submitted Nobody versus no submission |
| Answer privacy | Caller-only reveal for every identity including host; others' guesses absent from all phases/results/history; submitted status and ranking totals remain shared; retained void/missing/Nobody records stay distinct |
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
owned. Network timing needs measured device evidence; automated coverage results
are recorded separately in the README.

Provider adapter, admission and browser integration are implemented against
this contract. Live five-account authorization, preview coverage and browser
decoding/audibility still need independent verification. All-device audio and
detailed history screens remain outside the current checkpoint.

## 11. Implemented Demo transport details

Start includes `request_id`, `room_revision` and the active host `lease_id`.
Preload reports include `request_id`, `candidate_id`, `ok` and `lease_id`, plus
optional `waveform` (8–64 normalized levels between 0 and 1). The host computes
these from the decoded clip; the current public round exposes them without its
playback URL. Missing waveform data is null and must not become invented audio
bars. The manifest uses the `X-Audio-Lease` header. Ready includes `readiness_generation`
and, for the host, `lease_id`. Answer includes nullable `song_guess_token` and
`who_player_ids`; an empty list is submitted Nobody. Host recovery commands
include `request_id` and `readiness_generation`. Continue names all currently
unready non-host IDs in `exclude_player_ids`; Retry opens a fresh window.
Audio failure additionally includes `lease_id` and a bounded diagnostic `reason`.

The browser audio adapter must load and decode every issued candidate
and schedule the active buffer at the common start time. The backend already
accepts the scoped preload reports and provides private manifest references.
The setup preload window defaults to 60 seconds (`SETUP_TIMEOUT_MS` tunes it within 10–120 seconds). Missing reports abort with
`host_preparation_timeout`; complete reported failures use the strict skip rule.
Current implementation settings are process-local in the lobby and frozen in
SQLite at Start. Restart restores the last frozen settings, or defaults.
Controller renewal uses its tab ID every five seconds. An unchanged tab may
renew an unclaimed lease after a delay; a different tab receives a new lease and
voids any unclosed current attempt. Late lease holders cannot use the new lease.

See `backend/catalog/` for metadata search/cache and signed selections,
`backend/api/schemas.py` for strict request models,
`backend/api/routes.py` for HTTP handlers, and `backend/game/views.py` for public
projections. Origin checks, room cookies and rate limits live in separate
`backend/api/` modules; HTTP calls named use cases in
`backend/application/commands.py`, which enter coordinator ordering/transactions.
Normal accepts only an imported account verified by the server's Spotify
adapter. A browser cannot submit fabricated song ownership or authorization
proof. Physical audio and readiness/load targets remain separate acceptance gates.

## 12. Normal music-admission runtime

The host selects Spotify at entry; joining resolves the room mode. A valid room
cookie restores an existing identity without a fresh provider login. A new Normal
identity starts `POST /api/music/spotify/admissions` with `{nickname,
character_id, room_id?}`. The server sets `repeat_music_admission`, an HttpOnly,
SameSite=Lax cookie scoped to `/api/music/spotify`, with Secure under HTTPS and a
15-minute expiry. No player or room is created yet.

The callback validates its cookie and state once, then exchanges the PKCE code
and imports in the background. Receipts are bounded to 64 and queued/processing
imports to eight, with two workers. Each import resolves previews with bounded
outbound work outside SQLite transactions. Admission finally revalidates room
lobby/capacity/nickname/account constraints atomically. At most one verified
Spotify account identity is admitted per room by default. With the explicit
server setting `PLAYTEST_MODE=true`, the minimum roster is two and the same
verified account can join under distinct nicknames and independent credentials.
Room state publishes `minimum_players` and `playtest` for lobby readiness and
the visible testing notice. Shared-account admissions retain the account hash
and a persisted exemption from the ordinary unique-account index; turning the
setting off restores duplicate rejection against those identities as well.
Both player IDs remain listeners to their shared recordings. Provider admission,
song counts, room capacity, preloading and scoring still run normally.

Status returns `pending`, `processing`, `failed` with a sanitized error, or
`complete` with `admission: {room_id, code, player_id}`. A complete status retry
can reissue its room cookie after a lost response. The browser polls at 750 ms,
retries connection failures finitely and offers manual connection retry without
restarting import. Explicit new authorization cancels the prior unfinished
receipt first. A generic callback verification error does not consume another
browser's valid receipt. Restart loses unfinished receipts; it does not recover
OAuth identity through a nickname.

The application callback defaults to
`http://127.0.0.1:8000/api/music/spotify/callback` and must be registered exactly;
the PoC's `http://127.0.0.1:8765/callback` is a different URL. Browser entry and
callback must share their canonical origin so the temporary cookie returns.
Five physical devices need a reachable HTTPS origin with a registered callback;
loopback only works on the server computer. Spotify PKCE needs the client ID,
not a client secret. Apple developer catalog search/previews use the server's
signing key; guessing players need no Apple login. Apple request limits and
HTTP 429 are handled explicitly, with cached/single-flight search and a local
protective request budget rather than an unlimited-access claim.
