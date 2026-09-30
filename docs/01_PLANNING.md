# 01 — Planning

## Name
**Who's On Repeat**

## Goal
A party game where friends guess each other's music taste.

## Similar products
Apps like Musical Roulette, SpotTheFan and TuneTaste already let friends guess who likes a song, which shows there's demand for the idea. Who's On Repeat is different in three ways:
- **Apple Music support** (the others use Spotify or manual picks only)
- **Difficulty based on how often someone listens** to a song
- **Mashup rounds** (stretch goal)

## Scope (v1)

Updated after the Sep 29 PoC and Sep 30 decisions: build the playable demo
first with assigned hidden song data. Normal real-song play needs a validated
automatic history import; manual picks are out. All-device audio remains
conditional. The app will be written from scratch.
The host also plays on their own screen. Normal mode requires each player's
music-provider authorization; the host explicitly chooses Demo to bypass it.

| Feature | Status | Why |
|---|---|---|
| Classic rounds | **In** | The core of the game |
| Apple Music import | Conditional | Personal history was blocked by the tester's missing subscription; requires a subscribed tester |
| Manual song picks | **Out** | Players must not select or inspect their song pool before play |
| Demo mode | **In** | Host explicitly selects it; assign hidden songs from a seeded SQLite catalog and bundled clips without provider sign-in or API keys |
| Player characters | **In** | Show nickname and character in the lobby, round roster and results |
| Automatic round loop | **In** | Synchronized countdown, guessing, reveal and leaderboard; host controls recovery rather than every next round |
| Leaderboard (per room) | **In** | Simple, and part of the game |
| Room history (30 days) | **In** | Keep rankings, rounds, guesses and scores; the deadline is 30 days after the last completed game, or room creation |
| Audio on all devices | Conditional | The two-device PoC worked, but the ≤300 ms timing target remains unmeasured |
| Decoy songs (host can turn off) | **In** | Adds surprise: some rounds play a song nobody in the room has |
| Spotify import | Conditional | Personal import worked for one tester; counts, preview coverage and allowed launch scope still need confirmation |
| Mashup rounds | Stretch | Fun, but not needed for the core game |
| Chat, user accounts | **Out** | Not needed for a party game played in one sitting |

## Sep 30 scope clarification

Players neither select nor inspect their song pool before play. Demo mode uses
assigned hidden data from the demo database. The host selects Normal or Demo
when creating the room, before players join. Normal mode requires successful
music authorization, including for the host, and automatic personal-history
import; failed access never silently changes the room to Demo. Provider choice,
source lists, candidate counts and familiarity mapping remain to be validated.

Import the lobby pool once and precheck the full round sequence plus reserves.
Start freezes players, characters and settings. The loop is setup (at least
5 seconds), automatic readiness, countdown (3 seconds), guessing, reveal
(5 seconds), leaderboard (5 seconds), then the next round. A later readiness
timeout gives the host Retry or Continue without the unready players; those
players remain in the game's roster and ranking. See `07_API_AND_RUNTIME.md`.

## Stakeholders
| Stakeholder | What they want |
|---|---|
| **Players** | A quick game on their own screen; no game account, music-provider sign-in in Normal mode |
| **Room host** (a player and the only admin) | Choose mode/settings, start/end, play normally and resolve readiness failures |
| **Operator (me)** | Cheap and easy to run; no keys leaked |
| **Apple (and Spotify)** | Their API terms respected, which limits what I store and how audio is played |

## Assumed scale
3–10 players per room, up to about 20 rooms at the same time on a busy evening.
This is the target for the SQLite/single-process design, not a measured capacity.
At 500 ms polling it implies about 400 state requests per second at full occupancy.

## Feasibility
- **Technical:** Apple catalog access worked, and Spotify songs with Apple-resolved previews played in the PoC. Apple personal history is still unverified. The first playable core uses assigned demo songs; real personal-song play requires a validated automatic import. Live import and all-device timing need further validation.
- **Operational:** friends use a code, nickname and character on their own browser; Normal mode also requires music authorization. Nothing is installed on player devices.
- **Economic:** demo play needs no provider credentials; hosting and real-provider costs depend on the eventual deployment/integration choices.

## Risks
| Risk | Mitigation |
|---|---|
| Apple personal history cannot be tested | Use assigned demo songs for the core; test Apple with a subscribed account before promising it |
| Spotify import is unsuitable for the launch audience | Keep it conditional; validate access for intended testers and retain import counts |
| A player cannot import personal history | Explain the Normal-mode admission/import failure; the host can explicitly create a Demo room, without silently substituting a player's pool |
| All-device timing is unreliable | Host-device audio is the core mode; require a measured two-device check before enabling all-device mode |
| A song has no usable preview | Try at most three replacements for that requested round slot; skip it if none works; cancel if skipped slots exceed 30% of requested rounds |
| A browser cannot prepare the round | Initial 10-second timeout returns to the lobby with names; later timeouts offer host Retry or Continue without those players in the readiness barrier |
| Running out of time | Stretch features are cut first |

## SMART goals
| # | Goal | Measured by | Deadline |
|---|---|---|---|
| G1 | **Design documented:** planning through API/runtime design and the corresponding ADRs committed | Files `docs/01`–`07` and ADRs in the repo | ~~Sep 29~~ **Sep 30** (moved: added game rules and runtime decisions) |
| G2 | **Playable core:** 3 human players, including the host, complete an automatic 10-round Demo game with no API keys, started with `python -m backend` | Three browsers play the game locally, including readiness, shared audio and final rankings | Oct 1 |
| G3 | **Tested logic:** unit tests cover the rooms and game logic | `pytest --cov` reports **≥70%** | Oct 2 |
| G4 | **Real music (conditional integration target):** 3 players automatically import at least 10 real songs each and complete a game; ≥80% of their unique candidate songs have a playable preview | Retained import/coverage report plus a browser playback check; requires a validated provider available to the three testers | Oct 3 |
| G5 | **Ready to hand in:** a fresh clone runs by following the README; ≥12 commits on ≥6 days; 5 ADRs over ≥3 dates | Fresh-clone test + `git log` | Oct 4 |

These are targets, not completed checks. The Demo core is now implemented on `feature/demo-core`; verification is recorded separately in `08_IMPLEMENTATION_STATUS.md`. The schedule remains tight: complete acceptance checks and cut conditional features before tests or documentation. G4 now requires automatic import because manual picks were removed on Sep 30; its provider prerequisites remain unverified for three testers. The brief says Oct 4; the introductory slides say Oct 12, so use Oct 4 until the official deadline is clarified.

## SDLC model
**Agile / iterative.** Work fast in short loops: document one phase, commit, move on. Build the core first (assigned demo data), then add automatic provider imports or all-device audio only when their prerequisites and acceptance checks are met. After each loop, adjust the plan based on what was learned (e.g. the PoC results).
