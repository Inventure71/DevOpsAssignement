# 02 — Requirements

## How the game is played
Each player uses their own phone browser (no app to install). By default players are **together in the same place**: the **host's device plays the clip** out loud, and the other phones are used to answer. An **all-devices** mode is conditional: it will be enabled only after a two-device timing and audible-playback check; host-device audio is the first playable milestone. The app itself runs on a server (Azure in Assignment 2), so everyone opens the same URL.

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
| Rounds | 5 / 10 / 15 | 10 |
| Answer time | 10 s (flash) / 20 s / 30 s (slow) | 20 s |
| Audio playback | Host device only; All devices only after acceptance | Host device only |
| Game difficulty | Easy / Mixed / Hard | Mixed |
| Decoy songs | On / Off | On |

## Functional requirements

### Rooms & players
- **FR1** The system shall let a player create a room and receive a unique join code; the creator becomes the **host**.
- **FR2** The system shall let a player join a room with the join code and a nickname, with no account or password.
- **FR3** The system shall reject a nickname already used in the same room.
- **FR4** The system shall reject new joins when the room has 10 players or a game is in progress. Restoring an existing starting player is a reconnect, not a new join; a different browser cannot enter as a new identity mid-game.
- **FR5** The system shall recognise a returning player in the same browser while the room exists, without accounts. All starting players remain game participants until the game ends, even when disconnected.
- **FR6** The normal game shall load songs without players selecting them or inspecting their imported song lists before play. Real songs come from validated automatic personal-history imports; Apple/Spotify access and preview checks are still prerequisites. Manual song picking is excluded.
- **FR7** The system shall show each player's song count/import readiness in the lobby, without returning song titles, artists, covers or listener mappings to the browser.
- **FR8** The system shall let the host choose the number of rounds, the answer time, the available audio playback mode, the game difficulty and whether decoy songs are used.
- **FR9** The system shall let the host start the game only when there are 3–10 players and every player has at least 10 songs.

### Game
- **FR10** The system shall play a clip of one player's song each round, without showing the title, on the host's device only, or on all devices only if that conditional mode has passed acceptance and the host chose it.
- **FR11** The system shall let each player guess the song and which player(s) listen to it; several players can be selected, or "Nobody".
- **FR12** The system shall close a round when the answer time runs out or every starting player has answered. On timeout, a missing answer is recorded as blank with zero points; a disconnect does not remove that player or fabricate a "Nobody" answer.
- **FR13** The system shall reveal the correct song title, artist and cover from the frozen game snapshot, who listens to it, and the points earned after each valid round. Songs and their snapshots carry an optional `artwork_url` (a provider image URL or bundled demo asset URL); missing or failed artwork uses a bundled placeholder and does not prevent scoring.
- **FR14** The system shall not play the same song twice in one game.
- **FR15** The system shall show a room leaderboard after each round and a final ranking at the end.
- **FR16** An explicit host leave shall end the game immediately. If host connectivity is lost, the system shall allow 60 seconds after its last accepted heartbeat to reconnect, then end the game; a return after that deadline does not revive it.
- **FR20** The system shall start the next round only when the host taps "Next" after the reveal.
- **FR22** The system shall freeze song membership and the starting roster during play. Automatic re-imports or song changes are allowed only back in the lobby, and never alter a past game snapshot.
- **FR21** When decoys are on, the system shall include rounds with a song that no player in the room has, where the correct "who" answer is "Nobody".

### Data & history
- **FR17** The system shall retain the whole room until **30 days after its last completed game**, or after creation if no game completes, then delete the room and associated data together. Visits, heartbeats and aborted games do not extend retention; expired room codes no longer grant access.
- **FR18** The system shall retain final rankings, rounds, guesses and scores for that room lifetime, including answers from `void` attempts for diagnosis. Only `revealed` attempts contribute points to rankings. Anyone with a valid room code can initially view past games and final rankings; detailed round-history screens are deferred and the stored song pool is not exposed.

### Demo mode
- **FR19** The system shall offer demo mode with assigned fake players, hidden song pools and bundled playable clips, requiring no API keys or external music calls. Without a validated import provider, offer assigned demo data instead of manual real-song entry.

## Non-functional requirements
| ID | Category | Requirement |
|---|---|---|
| **NFR1** | Performance | A new round loads in **under 2 seconds**. |
| **NFR2** | Capacity | Supports 3–10 players per room and about 20 rooms at the same time. |
| **NFR3** | Usability | Works in a phone browser; joining takes only a code and a nickname. |
| **NFR4** | Reliability | If a song has no preview or Apple is unavailable, the game continues (the song is skipped); the app doesn't crash. |
| **NFR5** | Privacy | Stores nicknames, a digest of each random browser credential, room/presence timestamps, songs and game results for the room lifetime in FR17. Provider user tokens are used for an import and discarded; they are not persisted. Hide song pools through server response projections, rather than only hiding them in the UI. Session/callback details are decided in phase 07. |
| **NFR6** | Portability | Runs with no API keys (demo mode). |
| **NFR7** | Deployability (§7) | One start command; binds to `0.0.0.0`; port from `PORT`; SQLite file under `DATA_DIR`; all config through environment variables; no manual setup; ready within a few seconds. |
| **NFR8** | Architecture constraint | Single process, SQLite only; the 30-day cleanup runs inside the app (no cron job or separate worker). |
| **NFR9** | Maintainability | Unit tests cover **≥70%** of the rooms and game logic. |

## Decided later
- Scoring, difficulty and song selection are specified in `03_GAME_RULES.md`; domain boundaries and live updates are in `05_ARCHITECTURE.md`.
- Session/callback transport, room code format and heartbeat interval → phase 07 (security/API design); the 60-second host grace and retention anchor are decided in `06_DATA_MODEL.md`.
- The first real import provider and its familiarity mapping still need decisions. Manual song picking was removed on Sep 30; real-song play depends on a working automatic import.
- All-device audio needs retained evidence of ≤300 ms start drift and audible playback on both devices before it is enabled; `04_POC.md` records a functional check with timing still pending.
