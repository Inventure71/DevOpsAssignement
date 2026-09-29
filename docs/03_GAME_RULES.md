# 03 — Game Rules

The core business logic of the Game domain. Everything here must be covered by unit tests.

## 1. Round flow
1. The system picks a song (see §5) and plays its clip (host device only, or all devices).
2. Each player answers within the answer time (10 / 20 / 30 s):
   - **Which song?** One of **4 options**
   - **Who listens to it?** Select one or more players, **or "Nobody"**
3. The round closes when the time runs out or everyone has answered. A player who didn't answer scores 0.
4. **Reveal:** song title, artist and cover, who listens to it (or "Nobody: decoy!"), and each player's points for the round.
5. The leaderboard updates. The **host taps "Next"** to start the next round.

## 2. Host settings that affect the rules
| Setting | Options | Default |
|---|---|---|
| Game difficulty | Easy / Mixed / Hard | Mixed |
| Decoy songs | On / Off | On |

(Rounds, answer time and audio mode are in `02_REQUIREMENTS.md`.)

## 3. Answer options (song guess)
- 1 correct song + **3 wrong options**, shuffled
- **Decoys on:** the 3 wrong options are **2 songs from the room + 1 decoy-pool song**, in every round. An unfamiliar option therefore doesn't give away a decoy round.
- **Decoys off:** all 3 wrong options are songs from the room
- A wrong option can't be the same song as the correct one (§7)

## 4. Scoring
Players who own the song are treated **exactly like everyone else**: they can earn the song points and the speed bonus, and selecting themselves is a correct pick. This is fair because everyone gets about the same number of their own songs (§6).

### Song part
- `speed_bonus = round(50 × (1 − seconds_taken / answer_time))`, only with a correct song
  - `seconds_taken` is measured **by the server**, from the round's start time to when the answer arrives, and kept between 0 and the answer time
- `song_points = 100 + speed_bonus` if the song is correct, otherwise `0`

### Who part
`who_score` is a number from 0 to 1:

| Real listeners | Answer | who_score |
|---|---|---|
| One or more | Some players | `max(0, correct − wrong) ÷ number of real listeners` |
| One or more | "Nobody" | 0 |
| None (decoy) | "Nobody" | 1 |
| None (decoy) | Some players | 0 |

- `who_points = 100 × who_score`
- **Why wrong picks cancel correct ones:** adding a name only pays off if it's more likely right than wrong. A pick that's right with probability *p* changes the score by (2p − 1) ÷ listeners, which is positive only if p > 50%. Selecting everyone therefore doesn't pay.

### Round total
- **Perfect round** = correct song **and** `who_score = 1` → ×1.5
- `round_score = round((song_points + who_points) × difficulty_multiplier × perfect_multiplier)`
- `difficulty_multiplier`: easy ×1 · medium ×1.5 · hard ×2 · **decoy ×1**
- **All rounding is half up** (2.5 → 3) and is done **once, at the end** of each formula
- **Use exact fractions** (Python's `fractions.Fraction`), not floats. With floats, 187.5 can come out as 187.4999… and round down. Python's built-in `round()` is also wrong here, because it rounds 2.5 to 2.

### Fairness of the speed bonus
In host-device mode, everyone hears the clip at the same moment. In all-devices mode, every phone starts at the server's start time (PoC Q5). Network delay (~0.1 s) is small compared to the answer time, and the phone's clock is never trusted.

### Worked examples
**Normal round.** Listeners = {Anna, Ben}, 8 players in the room, medium song (×1.5), answer time 20 s.

| Player | Song | Time | Who | who_score | Calculation | Points |
|---|---|---|---|---|---|---|
| Carl | ✅ | 4 s | Anna, Ben | 1 | (140 + 100) × 1.5 × 1.5 perfect | **540** |
| Anna *(listener)* | ✅ | 5 s | Anna, Ben | 1 | (138 + 100) × 1.5 × 1.5 perfect | **536** |
| Frank | ✅ | 19 s | Ben | ½ | (103 + 50) × 1.5 | **230** (229.5) |
| Dana | ✅ | 10 s | Anna, Carl | 0 (1 − 1) | (125 + 0) × 1.5 | **188** (187.5) |
| Hal | ✅ | 8 s | everyone else (7) | 0 (2 − 5) | (130 + 0) × 1.5 | **195** |
| Eve | ❌ | 2 s | Anna, Ben | 1 | (0 + 100) × 1.5 | **150** |
| Gina | ❌ | 5 s | Nobody | 0 | 0 | **0** |

**Decoy round.** No listeners, ×1, answer time 20 s.

| Player | Song | Time | Who | who_score | Calculation | Points |
|---|---|---|---|---|---|---|
| Carl | ✅ | 6 s | Nobody | 1 | (135 + 100) × 1 × 1.5 perfect | **353** (352.5) |
| Dana | ✅ | 10 s | Anna | 0 | (125 + 0) × 1 | **125** |
| Eve | ❌ | 3 s | Nobody | 1 | (0 + 100) × 1 | **100** |

## 5. Song difficulty (familiarity)
Each song a player adds gets a level, based on how often that player listens to it:

| Source | Easy | Medium | Hard |
|---|---|---|---|
| Apple Music | In **heavy rotation** | In **recently played** | Only in the **library** |
| Manual picks | Tagged "on repeat" | Tagged "sometimes" | Tagged "rarely" |

- If a song appears in several Apple lists, the **easiest** level wins
- If several players have the song, the level of the player it was **picked from** is used
- Decoys have no level (×1)

## 6. Picking songs for a game
**Game difficulty:**
- **Easy:** only easy songs; if there aren't enough, fill with medium, then hard
- **Hard:** only hard songs; if there aren't enough, fill with medium, then easy
- **Mixed:** any level

**Decoy rounds (when on):** exactly **1 in 5** of the rounds (5 rounds → 1, 10 → 2, 15 → 3), placed at **random positions** (never round 1). A fixed count keeps games comparable; random positions keep decoys unpredictable.

**Algorithm**
1. At game start: shuffle the player order, and choose the decoy round positions.
2. **Decoy round:** pick a random song from the decoy pool that no player in the room has (§7) and that hasn't been used in this game.
3. **Normal round:** take the next player in the rotation (decoy rounds don't use up a turn), so everyone's songs come up evenly (e.g. 4 players, 8 normal rounds → 2 each).
4. From that player's songs, keep those that match the difficulty, haven't been played in this game, and have a playable clip. Pick one at random.
5. If that player has no song left, move on to the next player. If nobody has songs left, the game ends early.
6. Randomness comes from a random generator passed in, so tests can use a fixed seed.

**Decoy pool:** Apple Music's public top charts (developer token only, no user login). In demo mode, a fixed list of songs. (Availability is tested in PoC Q7.)

## 7. Same song, several listeners
Two songs are the **same song** when:
- they have the same **ISRC** (a standard recording ID from Apple/Spotify), or
- for manual picks without an ISRC: the same **title + artist**, compared lowercase, with spaces trimmed and "(feat. …)" removed

All players who have the song count as its listeners. A decoy is only valid if it matches **no** player's song.

## 8. Leaderboard
- Total = sum of a player's round scores in the game
- **Ties share the same rank** (1, 1, 3…)
- A room's history (30 days) keeps each game's final ranking

## 9. Edge cases
| Case | Rule |
|---|---|
| Player doesn't answer | 0 points for the round |
| Player answers the song but not "who" | who_score = 0 |
| Every player listens to the song | Normal scoring: selecting everyone is then fully correct |
| Clip fails to load during a round | The round isn't scored and is replaced by another song, if one is available |
| Decoy pool empty or unavailable | That round becomes a normal round |
| Host leaves | The game ends for everyone (FR16) |

## 10. What to unit test (feeds ADR-4)
- **Scoring:** every row of both worked-example tables; the speed bonus (0 s, half time, full time, wrong song = no bonus); who_score for every row of the table in §4, including decoys and "Nobody"; perfect-round bonus; the minimum of 0; half-up rounding with exact fractions (187.5 → 188)
- **Difficulty levels** from Apple sources and manual tags, including "easiest wins"
- **Song picking:** rotation, even spread, no repeats, the difficulty fallback, skipping a player with no songs left, ending early, decoy count and positions (never round 1), decoys never matching a room song
- **Answer options:** 4 options, the correct one included, no duplicates, the 2 room + 1 decoy mix when decoys are on
- **Same-song matching:** ISRC, and normalised title + artist
- **Leaderboard:** totals and shared ranks
