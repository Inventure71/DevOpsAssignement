# 02 — Requirements

## How the game is played
Each player uses their own phone browser (no app to install). By default players are **together in the same place**: the **host's device plays the clip** out loud, and the other phones are used to answer. An **all-devices** mode is conditional: it will be enabled only after a two-device timing and audible-playback check; host-device audio is the first playable milestone. The app itself runs on a server (Azure in Assignment 2), so everyone opens the same URL.
The host is also a guessing player and the only admin. Everyone sees their own
options, reveal and leaderboard; a central presentation screen is not required.

## Delivery boundary after the PoC

Bundled demo songs and host-device audio form the first milestone. Normal
players do not choose or inspect their song pool; manual picks are excluded.
Apple/Spotify imports remain subject to validation,
and personal Apple access remains unverified.
Requirements below describe the core unless explicitly marked conditional.
The app is built from scratch; PoC implementation and mocked tests do not count
as finished application features. See `04_POC.md` and `05_ARCHITECTURE.md`.

## Game settings (chosen by the host)
| Setting | Options | Default |
|---|---|---|
| Room mode (chosen before joins) | Normal / Demo | Host must choose explicitly |
| Rounds | 5 / 10 / 15 | 10 |
| Answer time | 10 s (flash) / 20 s / 30 s (slow) | 20 s |
| Audio playback | Host device only; All devices only after acceptance | Host device only |
| Game difficulty | Easy / Mixed / Hard | Mixed |
| Decoy songs | On / Off | On |

## Functional requirements

### Rooms & players
- **FR1** The system shall let a player create a room with an explicit Normal/Demo mode and receive a unique six-character join code using unambiguous uppercase letters/digits; the creator becomes the host, sole admin and a player. Generate codes randomly and retry collisions.
- **FR2** The system shall let a player join with the code, nickname and character, without a game account/password. In Normal mode successful music-provider authorization is mandatory before admission, including for the creator; Demo skips that authorization. The backend imports each player's own songs during the lobby, not from the host's account on everyone's behalf.
- **FR3** The system shall reject a nickname already used in the same room.
- **FR4** The system shall reject new joins when the room has 10 players or a game is in progress. Restoring an existing starting player is a reconnect, not a new join; a different browser cannot enter as a new identity mid-game.
- **FR5** The system shall restore a player through a room-scoped browser cookie while the room exists; rooms do not overwrite each other's identity and same-room tabs share one identity. No nickname-based recovery or device transfer is offered in v1. All starting players remain participants/ranking entries even when disconnected or excluded from a readiness barrier.
- **FR6** The normal game shall load songs without players selecting them or inspecting their imported song lists before play. Real songs come from validated automatic personal-history imports; Apple/Spotify access and preview checks are still prerequisites. Manual song picking is excluded.
- **FR7** The system shall show nicknames, characters, song counts/import readiness and settings in the lobby, without returning song titles, artists, covers or listener mappings.
- **FR8** The system shall let the host choose the number of rounds, the answer time, the available audio playback mode, the game difficulty and whether decoy songs are used.
- **FR9** The system shall enable Start only with 3–10 players, at least 10 imported/assigned songs each and completed lobby imports. Those counts do not guarantee enough unique playable songs; preparation must also validate the full planned sequence and reserves.

### Game
- **FR10** After automatic readiness and a three-second countdown on all participating screens, the system shall start shared host-device audio and guessing at a common server time. Only the current options are exposed; the correct song marker remains hidden. All-device audio stays conditional on acceptance.
- **FR11** Each player shall have one final submission per attempt: one of four title/credited-artist options and zero or more selected listener IDs. A submitted empty listener list means "Nobody". No submission at timeout means "No answer" and zero points. Identical retries return the existing receipt; changed second answers are rejected. Artist-only matches earn partial credit as defined in `03_GAME_RULES.md`.
- **FR12** The system shall close a round when the answer time runs out or every starting player has answered. On timeout, a missing answer is recorded as blank with zero points; a disconnect does not remove that player or fabricate a "Nobody" answer.
- **FR13** For five seconds after each valid round, the system shall reveal the correct song, credited artists, cover, real listeners, every player's guesses and points. Artwork comes from the frozen optional `artwork_url`; missing/failed images use a bundled placeholder without preventing scoring.
- **FR14** The system shall not play the same song twice in one game.
- **FR15** The system shall show the round leaderboard for five seconds after reveal, then advance automatically. The final ranking remains visible.
- **FR16** An explicit host leave shall end the game immediately. If host connectivity is lost, the system shall allow 60 seconds after its last accepted heartbeat to reconnect, then end the game; a return after that deadline does not revive it.
- **FR20** The normal loop shall advance automatically through readiness, countdown, guessing, reveal and leaderboard. The host chooses Start, End and readiness recovery; no routine "Next" tap is required. Host absence blocks beginning the next readiness cycle within the 60-second grace.
- **FR22** Start shall freeze roster, characters, mode/settings and membership. Setup freezes the prepared song sequence, options, reserves and credited-artist facts before play. Imports/changes are allowed only back in the lobby and cannot alter an old snapshot.
- **FR21** When decoys are on, the system shall include rounds with a song that no player in the room has, where the correct "who" answer is "Nobody".
- **FR23** During guessing, the system shall show each starting player's nickname, character and "Listening"/"Submitted" status, with connectivity separately; submitted guesses stay private until reveal. Only the active host audio tab receives playback references.
- **FR24** Automatic browser acknowledgements shall gate each round's common start time. Initial readiness has a 10-second limit; failure aborts setup and returns to the lobby naming unready players. A later timeout offers the host Retry (same unstarted attempt, fresh 10-second generation) or Continue excluding named players only from that barrier. Their identities/scores/answer eligibility remain; absent answers still receive zero. Host audio readiness cannot be bypassed.
- **FR25** The system shall use a five-second minimum setup countdown while finalizing the full sequence and checking audio; show "Preparing…" if unfinished. Each original candidate has at most three replacements. Skip an original requested slot when none works, and cancel with a clear error when skipped slots exceed 30% of the original requested count. Display the actual playable count otherwise. No repeated personal-history import is required per round.

### Data & history
- **FR17** The system shall retain the whole room until **30 days after its last completed game**, or after creation if no game completes, then delete the room and associated data together. Visits, heartbeats and aborted games do not extend retention; expired room codes no longer grant access.
- **FR18** The system shall retain final rankings, rounds, guesses and scores for that room lifetime, including answers from `void` attempts for diagnosis. Only `revealed` attempts contribute points to rankings. Anyone with a valid room code can initially view past games and final rankings; detailed round-history screens are deferred and the stored song pool is not exposed.

### Demo mode
- **FR19** The host shall explicitly choose Demo before joins. Human players receive hidden random assignments from a seeded SQLite demo catalog with bundled clips, requiring no provider sign-in, API keys or external calls. Failed Normal imports never silently switch modes; the host can explicitly create a Demo room instead.

## Non-functional requirements
| ID | Category | Requirement |
|---|---|---|
| **NFR1** | Performance | Under the defined supported-browser/network load test, round preparation through data delivery, required automatic acknowledgements and distribution of the common start time takes **under 2 seconds**. Preloaded data should shorten this interval; the intentional countdown is excluded. Client-readiness timeout is 10 seconds. Music authorization/lobby import and whole-game setup are separate measurements. |
| **NFR2** | Capacity | Supports 3–10 players per room and about 20 rooms at the same time. |
| **NFR3** | Usability | Works in a phone browser; joining uses code, nickname and character, plus mandatory provider authorization in Normal mode. Readiness is automatic. |
| **NFR4** | Reliability | Precheck the complete sequence and checked reserves before play; apply FR25's replacement/skip policy. Runtime audio failures remain recoverable as retained `void` attempts using frozen checked reserves; reveal is final. No crash or silent mode downgrade. |
| **NFR5** | Privacy | Store nicknames, character IDs, credential digests, import readiness/provenance, timestamps, songs and results for FR17's lifetime. Provider user tokens are transient and discarded after import. Room-scoped cookies are HttpOnly, SameSite=Lax and Secure under HTTPS. Project responses by phase rather than hiding secrets only in the UI; see `07_API_AND_RUNTIME.md`. |
| **NFR6** | Portability | Runs with no API keys (demo mode). |
| **NFR7** | Deployability (§7) | One start command; binds to `0.0.0.0`; port from `PORT`; persistent writable SQLite storage under `DATA_DIR`; environment configuration; automatic schema setup/versioned upgrades and demo seeding; liveness/readiness endpoints. Demo startup needs no outbound provider calls and targets readiness within a few seconds. |
| **NFR8** | Architecture constraint | Single process, SQLite only; the 30-day cleanup runs inside the app (no cron job or separate worker). |
| **NFR9** | Maintainability | Unit tests cover **≥70%** of the rooms and game logic. |

## Decided later
- Scoring, difficulty and song selection are specified in `03_GAME_RULES.md`; domain boundaries and live updates are in `05_ARCHITECTURE.md`.
- Browser identity, room codes, five-second heartbeats, phase timing and readiness recovery are specified in `07_API_AND_RUNTIME.md`; the 60-second host grace and retention anchor remain fixed.
- The first real import provider and its familiarity mapping still need decisions. Manual song picking was removed on Sep 30; real-song play depends on a working automatic import.
- Provider-specific authorization/callback implementation, source lists/candidate counts and complete credited-artist metadata still need real-provider validation; Demo does not wait for them.
- All-device audio needs retained evidence of ≤300 ms start drift and audible playback on both devices before it is enabled; `04_POC.md` records a functional check with timing still pending.
