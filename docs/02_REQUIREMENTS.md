# 02 — Requirements

## How the game is played

Players share a room and hear clips from the host device while answering on their own browsers. The host also plays and controls settings, Start, End and readiness recovery.

Demo assigns simulated libraries from the installed music pack. Real (`normal` in the API) imports each player's Spotify listening data and uses Apple catalog/previews. Apple personal listening and synchronized device audio are deferred.

## Game settings

| Setting | Options | Default |
|---|---|---|
| Room mode, before joins | Real / Demo | Explicit choice |
| Rounds | 5 / 10 / 15 | 10 |
| Answer time | 10 / 20 / 30 seconds | 20 seconds |
| Difficulty | Easy / Mixed / Hard | Mixed |
| Decoys | On / Off | On |

## Functional requirements

### Rooms & players

- **FR1** Create a room with a random, unique six-character unambiguous uppercase/digit code, retrying collisions. The creator is host and player.
- **FR2** Join with code, nickname and character. Real requires each player's successful music connection/import before membership; Demo uses assigned data through the same import/admission pipeline. Cancellation before commit prevents admission; completed delivery is accepted before acknowledging its admission ID.
- **FR3** Nicknames are unique within a room.
- **FR4** Admit up to five Real or ten Demo players, before a game starts. Real account identity is provider-qualified and unique per room; explicit playtest permits shared accounts. Spotify's five approved accounts are shared across rooms. Starting players can reconnect during play.
- **FR5** Restore identity through room-scoped cookies. Same-room tabs share identity; different rooms keep separate credentials. Starting players retain their roster/ranking entry after disconnect or readiness exclusion.
- **FR6** Import hidden personal libraries automatically from verified top/recent tracks with checked previews. Players discover songs during play.
- **FR7** The lobby exposes names, characters, counts, readiness and settings. Hidden titles, artists, covers and listener mappings stay server-side. One reusable blob character supports color and gameplay moods.
- **FR8** Only the host changes rounds, answer time, difficulty and decoys.
- **FR9** Start requires 3–5 Real or 3–10 Demo players, ten songs each and completed imports. Setup validates enough distinct playable candidates and reserves. Playtest allows two players.

### Game

- **FR10** Automatic readiness and a three-second countdown lead to a common server start time for guessing and host audio. During play, expose timing and submission status; search uses shared public catalog metadata.
- **FR11** Accept one final signed song selection and listener set per attempt. Resolve or clear typed search text before submission. Identical retries return the receipt; changed answers are rejected. An empty submitted listener set means Nobody; timeout without submission earns zero. [Game rules](03_GAME_RULES.md) define artist and release-edition credit.
- **FR12** Close a round at its deadline or when all starting players answer. Disconnected players remain eligible; missing answers are retained with zero points.
- **FR13** Reveal the song, credited artists, cover, actual listeners and the caller's own answer/points for five seconds. Other players' answers remain private, including from the host. Failed artwork uses a bundled placeholder.
- **FR14** Play each recording at most once per game.
- **FR15** Show the leaderboard for five seconds after reveal, then advance. Keep the final ranking visible.
- **FR16** Explicit host Leave ends play immediately. Lost host connectivity allows 60 seconds after its last heartbeat to reconnect; expiry ends the game permanently.
- **FR20** Advance automatically through readiness, countdown, guessing, reveal and leaderboard. Host absence pauses the next readiness cycle during the grace period.
- **FR21** With decoys enabled, include songs whose correct listener set is Nobody.
- **FR22** Start freezes roster, characters, settings and membership; setup freezes the sequence, reserves and artist facts. Later lobby changes leave old snapshots intact.
- **FR23** Show names, characters and Listening/Submitted status, with connectivity separately. Only the active host audio tab receives playback references.
- **FR24** Readiness has a ten-second limit. Initial failure returns to the lobby naming unready players; later failure offers Retry with a fresh generation or Continue excluding those players from that barrier. Their scores and answer eligibility remain. Host audio readiness is required. Prepare upcoming rounds during reveal/leaderboard and carry fresh check-ins forward.
- **FR25** Setup has a five-second minimum countdown and shows Preparing if work remains. Try up to three replacements per original candidate, skip exhausted slots and cancel if skips exceed 30% of requested rounds. Otherwise display the playable count. Import libraries once per lobby.

### Data & history

- **FR17** Delete each room and associated data 30 days after its last completed game, or creation if none completes. Visits, heartbeats and aborted games leave the expiry anchor unchanged.
- **FR18** Retain rankings, rounds, guesses and scores for that lifetime, including diagnostic void answers. Only revealed attempts contribute points. Valid room codes give access to past-game rankings; detailed round-history screens are deferred.

### Demo

- **FR19** Choose Demo explicitly before joins. Hidden assignments, catalog search and playback use the installed pinned pack and work offline. Missing media disables Demo until installation and restart. Failed Real imports remain Real failures; the host can create a Demo room separately.

## Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| **NFR1** | Performance | Target under two seconds from round preparation through acknowledgements and common-start delivery, excluding intentional countdowns. Measure authorization/setup separately; readiness timeout is ten seconds. |
| **NFR2** | Capacity | 3–5 Real or 3–10 Demo players per room, roughly 20 concurrent rooms; Spotify allowance is global. |
| **NFR3** | Usability | Phone-browser joining, automatic readiness and clear recovery. |
| **NFR4** | Reliability | Precheck sequence/reserves and apply FR25. Runtime audio failures retain void attempts and use frozen reserves; reveal is final. |
| **NFR5** | Privacy | Store room identity digests, import provenance, songs and results for FR17's lifetime. Discard transient provider user tokens after import. Use room-scoped HttpOnly, SameSite=Lax cookies, Secure under HTTPS, and phase-specific server projections. |
| **NFR6** | Portability | Demo runs without provider credentials. |
| **NFR7** | Deployability | One start command; `0.0.0.0`; `PORT`; writable SQLite under `DATA_DIR`; automatic versioned schema setup/seeding; liveness/readiness endpoints. Server readiness takes a few seconds without provider calls. |
| **NFR8** | Architecture | Single process and SQLite; in-process retention cleanup. |
| **NFR9** | Maintainability | At least 70% unit coverage of Rooms/Game logic; project gate is 90%. |

Scoring and familiarity are defined in [game rules](03_GAME_RULES.md); identity, timing and recovery in [API/runtime](07_API_AND_RUNTIME.md); provider setup in [music integration](13_SPOTIFY_IMPLEMENTATION.md).
