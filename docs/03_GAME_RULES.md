# 03 — Game Rules

The core business logic of the Game domain must be covered by unit tests.
Cover rendering and its load-failure fallback also need browser verification.

After the Sep 30 clarification, the first playable milestone uses assigned demo
songs and host-device audio. Manual song picking is excluded.
Apple familiarity levels apply only when personal imports
are validated. Spotify familiarity mapping is not decided here; all-device
audio is conditional (see `02_REQUIREMENTS.md` and `05_ARCHITECTURE.md`).

## 1. Game and round flow
The host plays on their own screen and is the only admin. The backend, not
that browser, imports each player's songs and coordinates the match.

1. **Lobby:** the host chooses Normal or Demo before joins. Normal requires
   each player's music authorization; Demo assigns hidden songs from the seeded
   database. Import the pool once in the lobby; no manual picks or per-round
   history requests. Every player has a nickname and character.
2. **Setup:** Start freezes the roster/settings and shows a five-second minimum
   setup countdown. Prepare and check the complete requested sequence and
   reserves (§6). If unfinished at zero, show "Preparing…" rather than start
   unchecked audio. Announce the actual playable count after any skipped slots.
3. **Readiness:** deliver current-round options and roster to players, and
   prepare audio on the active host tab. Browser acknowledgements are automatic,
   bound to the attempt and readiness generation. Initially every starting
   player must acknowledge within ten seconds; otherwise abort setup and return
   to the lobby with the timeout names. For later timeouts, the host chooses
   Retry or Continue without unready players (§9).
4. **Countdown:** only after the barrier passes, publish a common server start
   time three seconds ahead. Browsers estimate their clock offset and display
   the countdown. Readiness alone is not a synchronization measurement.
5. **Guessing:** music starts on the host device and each player can submit once
   within 10 / 20 / 30 seconds. Pick one of four title/credited-artist options and
   zero or more listener names. Submitting an empty listener list means
   **Nobody**; never submitting means **No answer**. Show nicknames, characters
   and Listening/Submitted status, with connectivity separately; hide guesses.
6. **Closure:** all starting players have submitted, or the server deadline
   passes. A disconnected or barrier-excluded player stays in that roster and
   can answer after reconnecting before the deadline. Missing answers become
   blank with zero points. Close/score once and stop audio; no early fabricated
   Nobody answer.
7. **Reveal (5 seconds):** show title, credited artists, frozen cover reference,
   real listeners (or "Nobody: decoy!"), every player's guesses and earned points.
   Missing/broken artwork uses the bundled placeholder. A published reveal is final.
8. **Leaderboard (5 seconds):** show current rankings, then automatically
   prepare the next round. There is no routine host Next tap. While the host is
   disconnected, finish current timed phases and wait on the leaderboard within
   the 60-second grace before starting another readiness cycle.
9. **Finish:** keep the final ranking visible. Save results and return the room
   to its lobby for another game. The full starting roster remains in rankings.

The host preloads the planned clips and checked reserves during setup. Future
song labels, correct-option markers and listener mappings are withheld from
ordinary state responses; players receive only current-round options. Private
host preload references can disclose metadata to someone inspecting that browser,
as described in the API contract. Characters are cosmetic
and frozen at Start, not a scoring input. See `07_API_AND_RUNTIME.md` for the API.

## 2. Host settings that affect the rules
| Setting | Options | Default |
|---|---|---|
| Game difficulty | Easy / Mixed / Hard | Mixed |
| Decoy songs | On / Off | On |

(Room mode, rounds, answer time and audio mode are in `02_REQUIREMENTS.md`.)

## 3. Answer options (song guess)
- 1 correct song + **3 wrong options**, shuffled; each shows title and credited artists
- Build all option sets during setup, including reserve replacements; do not regenerate them from a live pool during play
- **Decoys on:** the 3 wrong options are **2 songs from the room + 1 decoy-pool song**, in every round. An unfamiliar option therefore doesn't give away a decoy round.
- **Decoys off:** all 3 wrong options are songs from the room
- **Decoy pool unavailable:** use a normal round and take all 3 wrong options from the room; never block a round on an unavailable decoy distractor
- A wrong option can't be the same song as the correct one (§7)

## 4. Scoring
Players who own the song are treated **exactly like everyone else**: they can earn the song points and the speed bonus, and selecting themselves is a correct pick. Preparation aims to balance whose songs appear (§6); skips and substitutions can change the final distribution.

### Song part
- `speed_bonus = round(50 × (1 − seconds_taken / answer_time))`, only for the
  correct song option. Server time measures acceptance relative to the announced
  start; client timestamps never determine points. The API specifies the ordering
  boundary; submissions are accepted only in `[start, deadline)`.
- Correct song option: `song_points = 100 + speed_bonus`.
- Wrong option with at least one matching **credited artist identity**:
  `song_points = 50`, without speed bonus.
- Wrong option with no matching artist, or no song option: `song_points = 0`.
- Match sets of structured artist keys in the frozen correct/wrong song facts.
  Multiple common artists still award 50, not 50 each. Display-string substring
  matching is not artist identity. Demo fixtures supply explicit identities;
  real-provider credit completeness/canonicalization is an integration gate.

### Who part
`who_score` is a number from 0 to 1:

| Real listeners | Answer | who_score |
|---|---|---|
| One or more | Some players | `max(0, correct − wrong) ÷ number of real listeners` |
| One or more | "Nobody" | 0 |
| None (decoy) | "Nobody" | 1 |
| None (decoy) | Some players | 0 |

- `who_points = 100 × who_score`
- A submitted empty listener list is Nobody and uses the corresponding table row.
  A missing submission is No answer: zero for the entire round, not a scored Nobody guess.
  A submitted listener guess with no song option can still earn who points.
- **Wrong picks cancel correct ones:** selecting everyone scores zero when real listeners are at most half the roster. It can earn partial points when a majority listens, and full who points when everybody really listens; it is not a guaranteed winning strategy.

### Round total
- **Perfect round** = correct song option **and** `who_score = 1` → ×1.5
- Artist-only partial credit never qualifies for the perfect bonus
- `round_score = round((song_points + who_points) × difficulty_multiplier × perfect_multiplier)`
- `difficulty_multiplier`: easy ×1 · medium ×1.5 · hard ×2 · **decoy ×1**
- **All rounding is half up** (2.5 → 3) and is done **once, at the end** of each formula
- **Use exact fractions** (Python's `fractions.Fraction`), not floats. With floats, 187.5 can come out as 187.4999… and round down. Python's built-in `round()` is also wrong here, because it rounds 2.5 to 2.

### Fairness of the speed bonus
In host-device mode, players share the same audio output. The server measures answers from the announced round start, so network delay can still affect the speed bonus. The PoC did not retain all-device timing measurements; that mode stays conditional until drift and audible playback are checked. A client's own clock never determines scoring.

### Worked examples
**Normal round.** Listeners = {Anna, Ben}, 8 players in the room, medium song (×1.5), answer time 20 s.

| Player | Song | Time | Who | who_score | Calculation | Points |
|---|---|---|---|---|---|---|
| Carl | ✅ | 4 s | Anna, Ben | 1 | (140 + 100) × 1.5 × 1.5 perfect | **540** |
| Anna *(listener)* | ✅ | 5 s | Anna, Ben | 1 | (138 + 100) × 1.5 × 1.5 perfect | **536** |
| Frank | ✅ | 19 s | Ben | ½ | (103 + 50) × 1.5 | **230** (229.5) |
| Dana | ✅ | 10 s | Anna, Carl | 0 (1 − 1) | (125 + 0) × 1.5 | **188** (187.5) |
| Hal | ✅ | 8 s | everyone else (7) | 0 (2 − 5) | (130 + 0) × 1.5 | **195** |
| Eve | ❌ no shared artist | 2 s | Anna, Ben | 1 | (0 + 100) × 1.5 | **150** |
| Ben *(listener)* | ❌ shared credited artist | 2 s | Anna, Ben | 1 | (50 + 100) × 1.5, no perfect bonus | **225** |
| Gina | ❌ | 5 s | Nobody | 0 | 0 | **0** |

**Decoy round.** No listeners, ×1, answer time 20 s.

| Player | Song | Time | Who | who_score | Calculation | Points |
|---|---|---|---|---|---|---|
| Carl | ✅ | 6 s | Nobody | 1 | (135 + 100) × 1 × 1.5 perfect | **353** (352.5) |
| Dana | ✅ | 10 s | Anna | 0 | (125 + 0) × 1 | **125** |
| Eve | ❌ no shared artist | 3 s | Nobody *(submitted empty list)* | 1 | (0 + 100) × 1 | **100** |
| Gina | ❌ shared credited artist | 3 s | Nobody | 1 | (50 + 100) × 1, no perfect bonus | **150** |
| Frank | No submission | — | No answer | — | No answer always scores zero | **0** |

## 5. Song difficulty (familiarity)
Each automatically loaded song gets a level per player, based on the available
listening signal; demo data supplies fixed levels. Players never tag or choose
the songs themselves:

| Source | Easy | Medium | Hard |
|---|---|---|---|
| Apple Music | In **heavy rotation** | In **recently played** | Only in the **library** |
| Demo | Assigned easy level | Assigned medium level | Assigned hard level |

- Song identity is deduplicated within each room. Familiarity belongs to a player's relationship to a song, not the shared song record. Players do not inspect the source lists or choose the game's pool before play; manual picks and manual familiarity tags are excluded.
- If a song appears in several Apple lists, the **easiest** level wins
- If several players have the song, the level of the player it was **picked from** is used
- Decoys have no level (×1)

## 6. Preparing the full game sequence
**Game difficulty:**
- **Easy:** prefer easy songs; fill with medium, then hard
- **Hard:** prefer hard songs; fill with medium, then easy
- **Mixed:** any level

When decoys are on, plan exactly **1 in 5 requested slots** (5 → 1, 10 → 2,
15 → 3), at random positions excluding slot 1. If there is no suitable decoy,
use a normal song. Skipped slots retain their original slot numbers; the
surviving sequence may have a different decoy fraction. Do not silently change
historical listeners or difficulty to repair that fraction.

**Preparation algorithm**
1. Import/assign candidate pools once in the lobby, keeping familiarity per
   player. At least ten songs each is an admission/start minimum, not proof of
   enough distinct songs and reserves. Source lists and import count are still
   a real-provider decision.
2. At Start, shuffle the frozen roster and choose all requested decoy positions.
   For normal slots, rotate the source player; decoys do not consume a turn.
3. Choose each original candidate by difficulty with the fallback above. Reserve
   distinct replacement candidates from the imported pool; favor preserving its
   source player/difficulty, moving on when necessary. Decoys must have no frozen
   listener; an unavailable decoy can become normal. No live pool edits/imports.
4. Resolve/check previews and have the host preload the complete selected
   sequence and usable reserves. A provider URL or HTTP success alone is not
   audible-playback evidence. Check the host browser's loading/decoding support
   without playing future songs aloud. Each slot may try its original candidate
   plus **at most three substitutions**. Candidate exhaustion can fail it sooner.
   Freeze the chosen song, fixed option order, source player, difficulty,
   checked reserves and diagnostic check results before scored play.
5. If no candidate works, mark the **original requested slot** skipped. After
   checks, cancel setup with a clear error when
   `10 × skipped_slots > 3 × requested_rounds`. Otherwise announce how many
   rounds will actually play and retain the surviving prepared order.
6. Inject the random generator so tests can use a fixed seed. Build enough
   distinct distractors for every chosen/reserve candidate; inability to create
   four options is a preparation failure, not a partially playable round.

| Requested rounds | Maximum skipped slots without cancellation | Cancel at |
|---|---|---|
| 5 | 1 | 2 |
| 10 | 3 | 4 |
| 15 | 4 | 5 |

Exactly 30% skipped is allowed. Count a skipped slot once; failed candidates
that obtain a usable replacement do not count as skips. The denominator remains
requested rounds throughout, rather than imports, attempts or surviving rounds.

**Runtime recovery:** prechecking lowers risk but cannot guarantee future
playback. Accept a current host failure report only before closure/reveal; void
that attempt, retain its answers and use only a checked frozen reserve. The
same original slot retains its total three-substitution budget across setup
and recovery. If exhausted, skip the slot; apply the cumulative strict 30%
threshold, including setup skips. If exceeded after play began, abort with a
clear error and labelled partial rankings. Readiness Retry does not substitute
songs or consume this budget. Never replay a failed/played song.

**Decoy pool:** Apple public charts remain conditional on credentials/validation.
Demo uses separately seeded decoy candidates that are not assigned as personal
songs. Lack of suitable decoys converts that slot/options to normal as in §3.
The PoC records metadata/preview discovery, not this preparation implementation.

## 7. Same song, several listeners
Two songs are the **same song** when:
- they have the same **ISRC** (a standard recording ID from Apple/Spotify), or
- when an ISRC is missing: the same **title + artist**, compared case-insensitively, with spaces trimmed and "(feat. …)" removed; preserve Unicode letters

All players who have the song count as its listeners. A decoy is only valid if it matches **no** player's song.

## 8. Leaderboard
- Total = sum of a player's scores from `revealed` attempts in the game
- Only `revealed` attempts contribute to totals or final rankings. Keep answers from `void` attempts for diagnosis, but exclude any recorded points from them.
- **Ties share the same rank** (1, 1, 3…)
- The room retains final rankings, rounds, guesses and scores until 30 days after its last completed game (or creation if none completes). The initial history UI shows final rankings only; detailed screens are deferred. Aborted games retain clearly labelled partial rankings and do not extend retention.

## 9. Edge cases
| Case | Rule |
|---|---|
| Player disconnects or does not submit | Keep the starting identity and wait until deadline; missing answer gets zero |
| Player submits no listener names | Explicit Nobody, even with no song option; a valid decoy who guess can earn points |
| Player selects wrong title but a common credited artist | 50 song points, no speed/perfect bonus; ordinary who/difficulty rules still apply |
| Every player listens to the song | Selecting everyone is fully correct |
| Same accepted answer is retried | Return its original receipt; a changed second answer conflicts |
| Initial automatic readiness times out | After 10 seconds return to lobby naming the unready players; no scored round starts |
| Later readiness times out | Host can Retry the same unstarted attempt with fresh 10 seconds, or Continue excluding unready players from that barrier only |
| Barrier-excluded player reconnects | Same identity and prior points; can submit before this round's deadline, otherwise zero |
| Host is unready | Cannot Continue without its audio readiness; do not start silent shared audio |
| Stale readiness acknowledgement | Reject an old attempt/generation; it cannot start the current round |
| Clip fails before reveal | Void/retain/exclude points; use checked reserves within the shared three-substitution budget and 30% skip rule |
| Clip failure reported after reveal | Reveal is final; reject correction and keep published scoring |
| Cover missing or fails | Bundled placeholder; reveal/scoring continue |
| New browser joins mid-game | Reject new identity; existing same-browser identities can reconnect |
| Import, character or membership edit during setup/play | Reject; allow again in lobby |
| Host explicitly leaves | Abort immediately, retain labelled partial results |
| Host loses connectivity | Five-second heartbeats, 60-second grace; no new readiness cycle until return, and no late revival |
| Host refresh loses current audio | Restore identity but void interrupted unrevealed playback; do not silently replay the same song |

## 10. What to test (feeds ADR-4)
- **Scoring:** every worked example; half-up exact arithmetic; correct song speed
  boundaries; wrong song sharing one/multiple credited artist IDs (50 once,
  no speed/perfect); no common artist; listener-only submission; submitted empty
  Nobody versus missing zero; who-score clamps and all-listeners case.
- **Preparation:** fixed-seed rotation/difficulty fallback, deduplication, no
  reused played/failed songs, full sequence/options/reserves frozen; originals
  plus at most three substitutions; candidate exhaustion; skipped-slot counting
  and strict 30% boundary for 5/10/15 rounds; decoy fallback and shortened ratio.
- **Readiness/phases:** automatic ACKs, common future time and interval boundary;
  initial timeout names/lobby reset; later Retry/Continue; stale generations;
  no host exclusion; excluded players still answer/reconnect and remain ranked;
  5-second setup minimum, 3-second countdown, 5-second reveal/leaderboard and
  automatic advance; host-absence/grace behavior.
- **Persistence/API:** immutable characters/artist identities/memberships;
  same-payload retry receipts versus changed answers/commands; transactional
  closure races, missing rows, final ranks and retained void answers; host-only
  mutation checks; phase-projected responses hide guesses until reveal.
- **Lifecycle:** host leave/expiry, restart abort/reconciliation, no retention
  renewal on aborted setup/game, whole-room cleanup and room-scoped identity.
- **Browser acceptance:** actual shared audio and countdown drift, first/load
  failure handling, artwork fallback, character/status display, refresh/rejoin,
  automatic loop and host recovery controls; then NFR1/load verification.
