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
| Feature | Status | Why |
|---|---|---|
| Classic rounds | **In** | The core of the game |
| Apple Music import | **In** | Main music source; I already have an Apple Developer account |
| Manual song picks | **In** | For friends who don't have Apple Music |
| Demo mode | **In** | The app must run right after cloning, without API keys |
| Leaderboard (per room) | **In** | Simple, and part of the game |
| Room history (30 days) | **In** | Friends can look back at past games and scores |
| Audio on all devices (optional mode) | **In** | Lets the game work when players aren't together; host device only stays the default |
| Decoy songs (host can turn off) | **In** | Adds surprise: some rounds play a song nobody in the room has |
| Spotify import | Stretch | Depends on the professor's feedback |
| Mashup rounds | Stretch | Fun, but not needed for the core game |
| Chat, user accounts | **Out** | Not needed for a party game played in one sitting |

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
- **Technical:** probably yes, but Apple sign-in isn't proven yet, which is why the proof-of-concept phase comes next
- **Operational:** friends join with just a code and a nickname; there's nothing to install or set up
- **Economic:** no costs beyond the Apple Developer account I already have; all APIs used are free

## Risks
| Risk | Mitigation |
|---|---|
| Apple login or history doesn't work | Test it first (PoC); fall back to manual picks or Spotify |
| Spotify login or history doesn't work | Test it first (PoC); fall back to manual picks |
| Friends don't have Apple Music | Manual picks |
| A song has no preview clip | Skip it, or use a backup audio source |
| Running out of time | Stretch features are cut first |

## SMART goals
| # | Goal | Measured by | Deadline |
|---|---|---|---|
| G1 | **Design documented:** planning, requirements, game rules, PoC and architecture docs committed, with ADR-2 written | Files `docs/01`–`05` + ADR-2 in the repo | ~~Sep 29~~ **Sep 30** (moved: added a game rules phase) |
| G2 | **Playable core:** 3 demo players complete a 10-round classic game end to end, with no API keys, started with `python app.py` | A full demo game played locally without errors | Oct 1 |
| G3 | **Tested logic:** unit tests cover the rooms and game logic | `pytest --cov` reports **≥70%** | Oct 2 |
| G4 | **Real music:** at least 3 real players import their Apple Music history and play a game where ≥80% of rounds have a playable clip | A test game with friends | Oct 3 |
| G5 | **Ready to hand in:** a fresh clone runs by following the README; ≥12 commits on ≥6 days; 5 ADRs over ≥3 dates | Fresh-clone test + `git log` | Oct 4 |

All goals are **achievable** with the stretch features cut if needed, and **relevant** because each one maps to a graded part of the assignment.

## SDLC model
**Agile / iterative.** Work fast in short loops: document one phase, commit, move on. Build the core first (demo mode), then add Apple Music, then the stretch features only if there's time. After each loop, adjust the plan based on what was learned (e.g. the PoC results).
