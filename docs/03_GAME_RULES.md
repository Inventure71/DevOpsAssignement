# 03 — Game Rules

Players guess the song and who listens to it. The host plays the shared audio and controls the room; the server controls phases and scoring. Admission settings are in [Requirements](02_REQUIREMENTS.md), and transport details are in the [API contract](07_API_AND_RUNTIME.md).

## 1. Game and round flow

1. **Lobby:** choose Real (`normal` internally) or Demo. Each player has a nickname, color and imported or assigned hidden song pool.
2. **Setup:** Start freezes roster/settings and prepares the full sequence and reserves (§6). Setup lasts at least five seconds; show Preparing while checks or host decoding continue.
3. **Ready:** browsers automatically acknowledge current-round data. The host also prepares audio. Initially all starting players have ten seconds to acknowledge; a timeout returns the room to the lobby and names missing players.
4. **Countdown:** publish a common server start time three seconds ahead.
5. **Answering:** play audio on the host device. Players submit once within 10, 20 or 30 seconds, selecting a song and zero or more listener names. An empty submitted listener list means **Nobody**. No submission means **No answer**.
6. **Closure:** close when all starting players submit or the deadline passes. Score once, stop audio and start preparing the next round separately.
7. **Reveal (five seconds):** show the correct song, credited artists, cover, actual listeners and the caller's own guesses, correctness and points. A missing or broken cover uses the placeholder. Revealed scores are final.
8. **Leaderboard (five seconds):** show rankings while next-round preparation continues. Fresh complete preparation leads directly to countdown; otherwise open the ready gate. Progression waits for an absent host within its sixty-second grace.
9. **Finish:** persist final rankings, return the room to the lobby and keep results visible.

Players see shared submission status, correct answers after reveal and rankings. Submitted guesses remain private to their owner, including from the host. Private host preload references contain the audio needed for the full plan; provider URLs can reveal metadata to someone inspecting that browser. Public responses omit future song labels and listener mappings.

The frozen roster remains eligible throughout the match. Disconnected or barrier-excluded players can reconnect and answer before the deadline; missing answers score zero. Colors are cosmetic and frozen at Start.

## 2. Host settings that affect the rules

| Setting | Options | Default |
|---|---|---|
| Game difficulty | Easy / Mixed / Hard | Mixed |
| Decoy songs | On / Off | On |

Room mode, round count and answer time are defined in [Requirements](02_REQUIREMENTS.md).

## 3. Song guess: searchable catalog

Search or Enter looks up public title/artist metadata independently of the hidden room pool. Demo searches its complete pinned catalog locally; Real uses shared metadata and configured Apple search. Empty results, provider failures and rate limits have separate states. [Apple Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html) describes the public metadata service.

Selecting a result supplies a signed, room-scoped token containing song facts. Typing alone supplies no guess. The server validates signature and expiry and stores the selected facts; acceptance and scoring need no provider request. Search leaves listening pools and familiarity unchanged. A player may submit only the listener part.

## 4. Scoring

Listeners earn the same points as everyone else and can correctly select themselves.

### Song part

- Correct song: `song_points = 100 + speed_bonus`.
- Wrong song sharing a credited artist identity: `song_points = 50`, with no speed bonus.
- Other wrong song or no selection: `song_points = 0`.
- `speed_bonus = half_up(50 × (1 − seconds_taken / answer_time))`, awarded only for a correct song. Server acceptance time measures elapsed time in `[start, deadline)`.

Full song credit requires the same nonempty stable song key, or equal normalized guess titles with at least one common structured artist key or verified alias. Artist overlap uses identities, not display-name substrings; several shared artists still earn 50 once. ISRC equality alone does not establish a correct guess.

Guess normalization folds Unicode, case, diacritics, punctuation and whitespace. It removes trailing featured credits and recognized release labels: Taylor's Version, Remaster/Remastered with an optional year, and Deluxe Edition. Labels must be trailing parentheses, brackets or a spaced dash suffix. Live, remix, acoustic, karaoke and instrumental versions remain distinct, as do identical titles by different artists. This scoring rule leaves strict recording identity, playback matching and listener ownership unchanged.

### Who part

| Actual listeners | Submitted answer | `who_score` |
|---|---|---|
| One or more | Player names | `max(0, correct − wrong) / actual_listener_count` |
| One or more | Nobody | 0 |
| None (decoy) | Nobody | 1 |
| None (decoy) | Player names | 0 |

`who_points = 100 × who_score`. Wrong picks cancel correct ones. Selecting everyone earns full who credit only when everyone listens. A submitted listener-only answer can earn who points; a missing submission always earns zero total points.

### Round total

`round_score = half_up((song_points + who_points) × difficulty_multiplier × perfect_multiplier)`

| Multiplier | Value |
|---|---|
| Easy / medium / hard / decoy | 1 / 1.5 / 2 / 1 |
| Perfect: correct song and `who_score = 1` | 1.5 |
| Other answer, including artist-only credit | 1 |

Use exact fractions and round half up once at the end of each formula (2.5 → 3).

### Fairness of the speed bonus

Players share the host's audio output. Server acceptance time determines speed points, so network and command queueing delay can affect them. Client timestamps do not determine scores.

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

Familiarity belongs to each player/song relationship. When a song has several listeners, use the level of the player it was picked from. Decoys use ×1.

| Source | Easy | Medium | Hard |
|---|---|---|---|
| Spotify | Short-term top 20 | Other short-term, medium-term or recent observations | Long-term-only observations |
| Demo | Assigned easy | Assigned medium | Assigned hard |

Spotify overlaps keep the easiest level. Demo assigns simulated levels. These are familiarity estimates from bounded observations; players do not choose songs or tag difficulty. Apple personal listening remains planned.

## 6. Preparing the full game sequence

Easy prefers easy → medium → hard; Hard prefers hard → medium → easy; Mixed accepts any level.

1. Import or assign pools in the lobby. Start requires at least ten playable songs per player.
2. Shuffle the frozen roster and rotate the source player for normal slots. Decoys do not consume a player turn.
3. With decoys enabled, choose one in five requested slots (5 → 1, 10 → 2, 15 → 3), at random positions excluding the first. A decoy must match no listener; unavailable decoys become normal songs.
4. Select distinct candidates and reserves, favoring the slot's source player/difficulty. Each original slot has one candidate plus at most three substitutions, shared across setup and runtime recovery.
5. The host loads and decodes the complete sequence and usable reserves. Freeze checked candidates and outcomes before play. Setup has a separate bounded timeout, default sixty seconds.
6. Skip exhausted original slots. Cancel when `10 × skipped_slots > 3 × requested_rounds`.

| Requested rounds | Maximum skips | Cancel at |
|---|---|---|
| 5 | 1 | 2 |
| 10 | 3 | 4 |
| 15 | 4 | 5 |

Exactly 30% is allowed. Count each skipped original slot once; replacements are not skips. The denominator stays the requested round count, and surviving slots keep their original numbers. Skips can change the surviving decoy fraction. Played or failed candidates are never reused.

A playback failure before closure voids the attempt and uses a checked frozen reserve. Retain its answers but exclude its points from rankings. Exhausted reserves skip the slot; cumulative skips above the threshold abort with partial rankings. Revealed attempts remain final. Readiness Retry changes the barrier, not the song or substitution budget.

## 7. Same song, several listeners

Rooms groups imports by ISRC when available, otherwise by stable source song key. Matching identities must also have compatible normalized recording titles and credited artists; conflicting metadata is stored as a separate variant. Strict recording titles retain release/version labels that guess scoring may ignore (§4).

Every player attached to that recording is a listener, including observations whose preview lookup failed. A later checked import can make the recording playable without changing those listeners. A decoy must have no listener in the frozen roster.

## 8. Leaderboard

Total points sum only revealed attempts. Ties share ranks (1, 1, 3…). All starting players remain ranked, including departed players. Aborted games store labelled partial rankings.

Rooms retain history for thirty days from creation or the last completed game. Aborts, polls and heartbeats do not renew that anchor. Public history exposes final rankings; retained guesses stay private.

## 9. Edge cases

| Case | Behavior |
|---|---|
| Later readiness timeout | Host retries with a fresh ten-second generation or excludes named unready non-host players from this barrier |
| Excluded player returns | Keeps scores and answer eligibility; exclusions reset next round/generation |
| Host unready | Shared audio must be ready; host cannot be excluded |
| Stale acknowledgement | Reject old attempt/generation or consumed preparation |
| Identical answer resend | Return original receipt, including after closure; changed second answer conflicts |
| New browser joins mid-game | Reject new identity; existing credentials can reconnect |
| Pool, color or membership edit during setup/play | Allow edits again in the lobby |
| Host explicitly leaves | Abort immediately with partial results |
| Host disconnects | Heartbeats every five seconds; sixty-second grace; next ready gate waits for return |
| Host refresh interrupts unrevealed playback | Restore identity, void interrupted attempt and use recovery policy |
| Cover fails | Placeholder; scoring and reveal continue |

## 10. What to test (feeds ADR-4)

Cover scoring examples and boundaries, deterministic planning and replacement limits, readiness generations and promotion, answer privacy, idempotency, transactional closure, host recovery and retention. Browser checks cover audible playback, timing, reconnect and artwork fallback. See [Testing Strategy](18_TESTING_STRATEGY.md) for test ownership and commands.
