# 07 — API and Runtime Contract

Transport, identity and runtime behavior. [Game Rules](03_GAME_RULES.md) owns gameplay/scoring; [Architecture](05_ARCHITECTURE.md) owns component boundaries; [Data Model](06_DATA_MODEL.md) owns persistence.

## 1. Participants and admission

The host is a player and sole room admin. Each player guesses and sees results on their own browser; the host device plays shared audio.

`GAME_MODE=demo` permits Demo. `GAME_MODE=normal` also permits configured Real connections. `GET /api/config` publishes enabled modes and reasons. Demo requires a validated installed media pack; its absence leaves server/database readiness available with Demo disabled. Demo works locally without provider credentials; Real session admission requires the configured shared HTTPS origin. Unavailable-mode requests return `mode_unavailable` (409).

Choose mode before admission. Demo assigns hidden listening pools; each new Real player, including the host, completes verified personal music connection before membership (§12). Imports finish in the lobby before Start. Real currently supports five approved Spotify accounts including the host; Demo supports ten players. Real admission needs at least ten playable personal songs. Source observations and familiarity are described in [Game Rules](03_GAME_RULES.md#5-song-difficulty-familiarity).

## 2. Browser identity and authorization

Each room issues a random credential and stores its digest. Its cookie has a room-specific name and `Path=/api/rooms/{room_id}`, with `HttpOnly`, `SameSite=Lax` and `Secure` under HTTPS. Room-specific names/paths let one browser join several rooms. Cookie expiry is bounded by room retention and checked server-side; completion renews that lifetime, while polls and heartbeats only refresh presence. See the [cookie contract](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

An explicit `?room=…` URL restores the same player through its cookie. The plain entry opens Create/Join; an invite opens Join. Nicknames are display identities. New identities can join only in the lobby; lost credentials require a new admission with an available nickname. Credentials and provider tokens stay out of URLs, browser storage, snapshots and logs.

Room codes are six random characters from an unambiguous uppercase letter/digit alphabet, with collision retries. Codes permit lobby discovery/admission and final history lookup; cookies establish membership and host authority. Protected requests authenticate membership and then host status where required. Creation/join rate limits are configurable. Unsafe requests require same-origin JSON and trusted Origin validation.

## 3. API surface

The prefix is `/api`. Bodies use opaque IDs and UTC milliseconds. State includes `server_now_ms`, monotonic `state_version`, phase and applicable deadlines; clients ignore older poll responses. `/docs` and `/openapi.json` expose request schemas. `/` serves the browser, `/ui` its modules, and `/static/demo/local` installed media.

| Method and path | Access | Effect |
|---|---|---|
| `GET /api/config` | Entry browser | Launch profile and enabled/reason values for Demo and Real (`normal`); no secrets |
| `GET /api/demo/preview` | Public metadata | One active Demo catalog sample for the UI lab; title, artist, local preview URL and optional artwork; no player listening evidence |
| `POST /api/rooms` | Demo admission | Create Demo room with host nickname/character; issue host cookie. Real requires the staged music connection flow below |
| `GET /api/room-codes/{code}` | Code holder | Resolve room ID/mode/capacity/join availability; no hidden pool or host privileges |
| `GET /api/music/config` | Connection browser | `providers` keyed by provider ID, with `id`, `label`, `enabled`, `reason`; Spotify also supplies canonical `application_url` / `requires_shared_url`; Apple Music is disabled as Coming later |
| `POST /api/music/admissions` | Same-origin JSON, admission checks | Begin connection for required `provider`, nickname/character and optional target room; return `authorization: {kind: "redirect", url}` for Spotify; no membership yet |
| `GET /api/music/spotify/callback` | Matching admission cookie and one-use OAuth state | Provider-specific registered callback; queue verified import and redirect to `/?music=processing` or generic `/?music=error` |
| `GET /api/music/status` | Matching admission cookie | Pending/processing/failed/complete receipt with provider and nonsecret connection draft; completion issues room cookie and returns room/code/player IDs |
| `POST /api/music/cancel` | Same-origin JSON | Cancel unfinished work before membership; if already complete, recover its admitted session instead of discarding it |
| `POST /api/music/acknowledge` | Same-origin JSON | Body `{admission_id}`; retire only the matching completed receipt; mismatch returns false, matching unfinished returns 409 |
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

## 4. Phase-specific state

`character_id` stores a blob color: `coral`, `periwinkle`, `lavender`, `lemon`, `lilac`, `sage`, `sky` or `rose`. Coral is the admission default; game colors freeze at Start.

| Phase | Public information |
|---|---|
| Lobby | Mode, names/colors, connectivity, import counts/readiness, settings and Start eligibility |
| Setup | Frozen roster, requested round count, preparation progress/errors and minimum countdown |
| Ready/countdown | Current waveform if available, roster, check-in progress/generation and scheduled start |
| Answering | Waveform/roster, deadline, named Listening/Submitted status and caller's receipt |
| Reveal | Correct song/credits/cover, actual listeners and caller's guesses, correctness and points |
| Leaderboard | Revealed-attempt totals/ranks and next-phase timing |
| Finished | Persisted final or labelled partial rankings and end cause |

Submitted song/listener guesses are visible only to their owner, including in host responses. Correct song/listeners appear at reveal. Status and totals are shared. Missing submissions become No answer; covers use the inline music placeholder on failure. Listening/Submitted describes answer state, while connectivity is separate.

The active host audio tab receives private planned/reserve playback references. Public responses and preload labels omit future titles, artists and listeners. A host inspecting provider URLs may still infer metadata.

## 5. Full-game setup and replacements

Start freezes roster/settings and creates a preparing game. The complete sequence and reserves use the frozen imported pool. Host preload reports validate server-issued candidates and persist decode outcomes; they cannot introduce arbitrary songs or URLs. All issued clips are loaded/decoded before play, without playing future songs aloud.

Setup lasts at least five seconds. If preparation continues, show Preparing. Its host-validation timeout defaults to sixty seconds, configurable by `SETUP_TIMEOUT_MS` within 10–120 seconds. Missing reports abort with `host_preparation_timeout`. The later round-ready window starts separately.

[Game Rules](03_GAME_RULES.md#6-preparing-the-full-game-sequence) defines candidate uniqueness, the original-plus-three substitution budget and strict 30% skip limit. Per-round recovery uses checked reserves; provider retrieval remains outside the timed game path.

## 6. Automatic readiness and synchronization

`application/round-readiness.mjs` sends automatic ACKs. Guests need current-round data; the host also needs a decoded clip, running audio context and valid lease. ACKs contain `round_id` and `readiness_generation`; identical repeats succeed, stale generations fail. State versions order display updates independently of ACK validity. Session/generation guards cancel stale browser work.

At closure, a separate `upcoming_round` is exposed during reveal/leaderboard. Guests receive `{id, round_number, readiness_generation}`; the host also receives `audio_candidate_id`. Visible browsers renew preparation every two seconds with `{browser_id, readiness_generation, lease_id?}`. Promotion accepts check-ins no older than five seconds from connected players, with the current lease for the host. Complete preparation enters the three-second countdown immediately after leaderboard. A consumed preparation returns 409; it cannot acknowledge the promoted round or start audio early.

Initially all starting players must acknowledge within ten seconds; timeout aborts to lobby with missing names. Later ready windows open with the host present. On timeout the host can:

- **Retry:** clear ACKs, increment generation and reopen ten seconds for the full roster.
- **Continue:** exclude named unready non-host players from this barrier. Remaining required players must acknowledge.

Exclusions expire next round/generation. Excluded players keep prior scores and answer eligibility. Early closure still counts the full starting roster. Host audio readiness is always required.

Passing the barrier publishes a server start time three seconds ahead. Browser clock estimates drive the displayed countdown and host scheduling. ACKs establish prepared data; measured playback/start drift establishes device timing.

## 7. Answers, time and scoring

An answer is `{song_guess_token: string | null, who_player_ids: [...]}`. Player IDs must be unique members of the frozen roster. An empty submitted list means Nobody; no submission becomes missing with zero total points. Signed selections must be authentic, room-scoped, resolved and unexpired at new acceptance. Game stores the selected facts in `song_guess_json`.

Each starting player has one immutable answer per attempt. Identical resends return the original receipt, even after closure or token expiry. A changed second payload conflicts. After acquiring the room's command turn, the server captures acceptance time and applies due transitions; new answers are accepted only in `[starts_at_ms, deadline_at_ms)`. Network/queueing delay affects speed points. Closure scores once in a transaction when all starting players submit or the deadline arrives.

[Scoring rules](03_GAME_RULES.md#4-scoring) define exact half-up arithmetic, structured artist overlap and relaxed release-label guesses. Strict recording matching remains separate. Accepted answer and closure paths use frozen facts without provider requests.

### Public song search

Authenticated `GET /api/rooms/{room_id}/song-search?q=...` accepts normalized queries of 2–100 characters. Search/Enter sends requests; typing alone does not. `local=true` prefers shared metadata before provider fallback. Results have this shape:

```json
{
  "songs": [{"token": "signed-selection", "title": "Billie Jean", "artist": "Michael Jackson", "artwork_url": null}],
  "source": "apple",
  "cached": false
}
```

Demo searches the installed catalog locally, including misses, returning `source: "catalog"`. Real searches shared public metadata and configured Apple results, up to twenty songs with structured credits. Results are independent of hidden listener pools and omit playback URLs/correctness flags. See [Apple catalog search](https://developer.apple.com/documentation/applemusicapi/search-for-catalog-resources) and [public Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html).

Search uses a five-minute/128-query memory cache and coalesces identical requests. Provider coverage persists for a day; empty coverage expires sooner. Configured Apple search has a local protective budget of sixty requests/minute, an eight-second transport timeout and bounded responses. Failures cache for ten seconds. Apple HTTP 429 returns `apple_rate_limited`; exhausted local budget returns `song_search_busy` (429); empty success remains 200. Search runs outside room locks/write transactions.

Bulk metadata may return `resolve_required: true`. Selecting it sends its signed token to `song-selection`, which verifies provider matches and saves scoped `guess`/`recording` links. Positive verification survives unchanged identity; preview expiry is separate. Unresolved references cannot be submitted.

Tokens authenticate room ID, song facts and a twenty-minute expiry using a process-local secret. Restart rotates the secret and aborts interrupted games. Stored answers retain authenticated facts rather than tokens.

`round.my_answer` is null until submission, then contains `{song_guess: {title, artist, artwork_url} | null, who_player_ids}`. Reveal contains `{song, listener_ids, my_answer}`; its caller-owned answer adds `player_id`, `status`, `points` and `song_match` (`correct|artist|wrong|unanswered`). Missing answers have null song/listener guesses and zero points; submitted Nobody has `who_player_ids: []`. Other answer rows remain private.

## 8. Failure, presence and command retries

Audio failures apply only to the current ready/playing attempt before closure. [Game Rules](03_GAME_RULES.md#6-preparing-the-full-game-sequence) defines voiding, checked replacements, skips and partial results. Late failures leave published reveal scores final.

Presence heartbeats run every five seconds, separately from polls/ACKs. Host grace lasts sixty seconds from its last accepted heartbeat; expiry is checked before accepting a returning heartbeat. Current timed phases can finish during absence, but the next ready window waits for return. Explicit host Leave aborts immediately. Non-host absence preserves frozen identity.

One host tab holds the audio-controller lease and renews it with heartbeats. Explicit takeover replaces ownership; stale leases cannot ACK or report playback. Refresh interrupting an unclosed attempt voids it. Session restoration alone cannot establish uninterrupted audio.

Host commands carry `request_id` and expected attempt/generation where applicable. Accepted receipts bind actor, type and normalized payload; identical retries return their stored result and changed reuse conflicts. `start_request_id` also deduplicates Start after restart. Receipts contain effect IDs rather than audio or credentials.

Errors use `{error: {code, message, retryable, details}}`. Stable codes distinguish validation, authorization, stale/conflicting requests, readiness/setup failures, expiry, rate limits and infrastructure errors. Missing-ACK timeout details name affected players.

## 9. Process, database and operations

Run one worker/replica on `0.0.0.0:PORT`. Persist `DATA_DIR/whos_on_repeat.sqlite3` on compatible local storage, with WAL, foreign keys and busy timeouts. Room locks, leases, receipts, settings and query budgets are process-local. Blocking storage/provider work runs outside the async event loop; external I/O stays outside room locks and transactions.

Lifespan applies application migrations and initializes recovery/catalog state before readiness. An installed Demo pack validates before seeding; an absent pack disables Demo while configured Real remains available. The launcher installs missing media; runtime initialization uses existing assets. A one-second task advances phases and a periodic task cleans expired rooms. Shutdown cancels/awaits tasks and closes resources.

Restart voids interrupted unclosed attempts, preserves revealed scores, stores server-restart partial results and restores surviving rooms to lobby. Abort leaves retention unchanged. Expiry deletes Game history before Rooms data transactionally; completed games renew retention. See [Data Model](06_DATA_MODEL.md).

Liveness checks process response; readiness checks initialized database/runtime availability. Logs contain bounded IDs, phases, latency and cause codes, excluding credentials, guesses and private pools/media. SQLite-consistent backups include active WAL state and require restore verification. [README](../README.md) contains configuration and run commands.

## 10. Verification contract

[Testing Strategy](18_TESTING_STRATEGY.md) covers policy units, SQLite/API integration, browser modules and device playtests. Verify admission/identity, setup limits, readiness freshness/generations, answer privacy, scoring boundaries, retries/races, host recovery and restart/expiry.

The two-second preparation target measures current-round payload preparation through required client ACKs and start-time delivery. Provider import, full-game preload and the subsequent three-second countdown are separate. Measure all required clients under stated network/device conditions, with client traces confirming start-time receipt.

## 11. Implemented Demo transport details

| Command | Required fields beyond path IDs |
|---|---|
| Start | `request_id`, `room_revision`, `lease_id` |
| Preload check | `request_id`, `candidate_id`, `ok`, `lease_id`; optional `waveform` |
| Current ready | `readiness_generation`; host also `lease_id` |
| Upcoming ready | `browser_id`, `readiness_generation`; host also `lease_id` |
| Answer | Nullable `song_guess_token`, `who_player_ids` |
| Retry / Continue | `request_id`, `readiness_generation`; Continue adds `exclude_player_ids` |
| Audio failure | `request_id`, `readiness_generation`, `lease_id`, bounded `reason` |

Private audio manifests require `X-Audio-Lease`. Host-decoded waveform samples contain 8–64 normalized levels in `[0,1]`; absent data stays null. Setup preloads the complete manifest and schedules the current decoded buffer at the common start. Lobby settings are process-local until frozen at Start; restart restores the last frozen settings or defaults.

Strict payloads are in [schemas.py](../backend/api/schemas.py), HTTP handlers in [routes.py](../backend/api/routes.py), and public projections in [views.py](../backend/game/views.py).

## 12. Real music connection runtime

Entry chooses Real or Demo. A new Real player stages nickname/color and selects a provider before membership. A guest's resolved room determines mode; an existing room cookie restores identity. Spotify is enabled when configured; Apple Music shows Coming later while Apple catalog search/previews remain available. Demo uses simulated listening data.

`GET /api/music/config` returns provider capabilities. `POST /api/music/admissions` takes `{provider: "spotify", nickname, character_id, room_id?}` and returns `{authorization: {kind: "redirect", url}}`. Unknown/unavailable providers fail before membership. The temporary `repeat_music_admission` cookie is HttpOnly, SameSite=Lax, scoped to `/api/music`, Secure under HTTPS, and expires after fifteen minutes. Browser storage holds only the recoverable connection draft.

`SpotifyAuthorization` owns PKCE state/verifier, callback validation and token exchange. The registered callback is `/api/music/spotify/callback`; it consumes matching cookie/provider/state once, queues import and redirects to `/?music=processing` or sanitized `/?music=error`. `MusicAdmissions` owns neutral receipts and jobs, bounded to 64 receipts, eight queued/processing imports and two workers. Source/preview work runs outside room transactions; final delivery atomically rechecks receipt and Rooms constraints.

Personal account digests include room, provider and account identity. Default admission rejects duplicate accounts within a room. `PLAYTEST_MODE=true` permits two-player games and shared verified accounts under independent nicknames/credentials. State publishes `minimum_players` and `playtest`; persisted exemptions preserve those admissions, while disabling playtest restores duplicate rejection. All ordinary song, preload and scoring rules still apply.

`GET /api/music/status` returns `pending`, `processing`, `failed` with a sanitized error, or `complete` with `admission: {room_id, code, player_id}`. Every receipt also contains an opaque noncredential `admission_id`, provider and nonsecret connection draft. Complete delivery can reissue the room cookie after a lost response. The browser polls every 750 ms and recovers status after refresh or authorization return.

Cancel and final commit share a receipt lock. `POST /api/music/cancel` removes unfinished work before SQL admission; a completion that already committed returns its actual room session. The browser accepts that session before sending `POST /api/music/acknowledge` with `{admission_id}`. Acknowledgement retires only the matching completed receipt. A different current receipt returns `{acknowledged: false}`; matching unfinished work returns 409; already-retired receipts acknowledge harmlessly. The endpoint sets or deletes no cookie, so delayed acknowledgements cannot erase a newer connection. Empty bodies fail validation.

Leave retires outstanding completed receipts, and delivery checks the persisted session is live. Process restart loses receipts, requiring unfinished connections to retry.

The callback defaults to `http://127.0.0.1:8000/api/music/spotify/callback` and must match provider registration exactly. Browser entry and callback share the canonical origin so the cookie returns. Cross-device Real play uses a reachable shared HTTPS origin. Spotify PKCE uses a client ID; Apple developer catalog access uses its server signing key, independently of player authorization.
