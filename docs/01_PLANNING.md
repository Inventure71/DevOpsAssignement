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

| Feature | Status | Why |
|---|---|---|
| Classic rounds | **In** | The core of the game |
| Apple Music import | Conditional | Personal history was blocked by the tester's missing subscription; requires a subscribed tester |
| Manual song picks | **Out** | Players must not select or inspect their song pool before play |
| Demo mode | **In** | The app must run right after cloning, without API keys |
| Leaderboard (per room) | **In** | Simple, and part of the game |
| Room history (30 days) | **In** | Keep rankings, rounds, guesses and scores; the deadline is 30 days after the last completed game, or room creation |
| Audio on all devices | Conditional | The two-device PoC worked, but the ≤300 ms timing target remains unmeasured |
| Decoy songs (host can turn off) | **In** | Adds surprise: some rounds play a song nobody in the room has |
| Spotify import | Conditional | Personal import worked for one tester; counts, preview coverage and allowed launch scope still need confirmation |
| Mashup rounds | Stretch | Fun, but not needed for the core game |
| Chat, user accounts | **Out** | Not needed for a party game played in one sitting |

## Sep 30 scope clarification

Players neither select nor inspect their song pool before play. Demo mode uses
assigned hidden data. Real-song play requires automatic personal-history import;
the first provider and its familiarity mapping are still to be chosen. If live
import is unavailable, offer demo mode rather than a manual selection fallback.

## Stakeholders
| Stakeholder | What they want |
|---|---|
| **Players** | A fun, quick game with no signup |
| **Room host** (a player with extra controls) | To start a game fast and control it (start, next round, end) |
| **Operator (me)** | Cheap and easy to run; no keys leaked |
| **Apple (and Spotify)** | Their API terms respected, which limits what I store and how audio is played |

## Assumed scale
3–10 players per room, up to about 20 rooms at the same time on a busy evening. That's small enough that SQLite and a single process are enough.

## Feasibility
- **Technical:** Apple catalog access worked, and Spotify songs with Apple-resolved previews played in the PoC. Apple personal history is still unverified. The first playable core uses assigned demo songs; real personal-song play requires a validated automatic import. Live import and all-device timing need further validation.
- **Operational:** friends join with just a code and a nickname; there's nothing to install or set up
- **Economic:** no costs beyond the Apple Developer account I already have; all APIs used are free

## Risks
| Risk | Mitigation |
|---|---|
| Apple personal history cannot be tested | Use assigned demo songs for the core; test Apple with a subscribed account before promising it |
| Spotify import is unsuitable for the launch audience | Keep it conditional; validate access for intended testers and retain import counts |
| A player cannot import personal history | Offer assigned demo data; catalog access alone does not supply that player's listening history |
| All-device timing is unreliable | Host-device audio is the core mode; require a measured two-device check before enabling all-device mode |
| A song has no preview clip | Skip it, or use a backup audio source |
| Running out of time | Stretch features are cut first |

## SMART goals
| # | Goal | Measured by | Deadline |
|---|---|---|---|
| G1 | **Design documented:** planning, requirements, game rules, PoC and architecture docs committed, with ADR-2 written | Files `docs/01`–`05` + ADR-2 in the repo | ~~Sep 29~~ **Sep 30** (moved: added a game rules phase) |
| G2 | **Playable core:** 3 demo players complete a 10-round classic game end to end, with no API keys, started with `python app.py` | A full demo game played locally without errors | Oct 1 |
| G3 | **Tested logic:** unit tests cover the rooms and game logic | `pytest --cov` reports **≥70%** | Oct 2 |
| G4 | **Real music (conditional integration target):** 3 players automatically import at least 10 real songs each and complete a game; ≥80% of their unique candidate songs have a playable preview | Retained import/coverage report plus a browser playback check; requires a validated provider available to the three testers | Oct 3 |
| G5 | **Ready to hand in:** a fresh clone runs by following the README; ≥12 commits on ≥6 days; 5 ADRs over ≥3 dates | Fresh-clone test + `git log` | Oct 4 |

These are targets, not completed checks. With no application built yet, the schedule is tight: build the demo core first and cut conditional features before tests or documentation. G4 now requires automatic import because manual picks were removed on Sep 30; its provider prerequisites remain unverified for three testers. The brief says Oct 4; the introductory slides say Oct 12, so use Oct 4 until the official deadline is clarified.

## SDLC model
**Agile / iterative.** Work fast in short loops: document one phase, commit, move on. Build the core first (assigned demo data), then add automatic provider imports or all-device audio only when their prerequisites and acceptance checks are met. After each loop, adjust the plan based on what was learned (e.g. the PoC results).
