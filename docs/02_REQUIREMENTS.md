# 02 — Requirements

## How the game is played
Each player uses their own phone browser (no app to install). By default players are **together in the same place**: the **host's device plays the clip** out loud, and the other phones are used to answer. An **all-devices** mode is conditional: it will be enabled only after a two-device timing and audible-playback check; host-device audio is the first playable milestone. The app itself runs on a server (Azure in Assignment 2), so everyone opens the same URL.

## Delivery boundary after the PoC

Demo/manual songs and host-device audio are the core. Apple history and Spotify
import are conditional integrations; personal Apple access remains unverified.
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
- **FR4** The system shall reject joining when the room has 10 players or the game has already started.
- **FR5** The system shall recognise a returning player after a page refresh, without accounts.
- **FR6** The system shall let a player pick songs manually. Apple Music history and Spotify imports are conditional additions after their access and preview checks pass.
- **FR7** The system shall show each player's song count in the lobby.
- **FR8** The system shall let the host choose the number of rounds, the answer time, the available audio playback mode, the game difficulty and whether decoy songs are used.
- **FR9** The system shall let the host start the game only when there are 3–10 players and every player has at least 10 songs.

### Game
- **FR10** The system shall play a clip of one player's song each round, without showing the title, on the host's device only, or on all devices only if that conditional mode has passed acceptance and the host chose it.
- **FR11** The system shall let each player guess the song and which player(s) listen to it; several players can be selected, or "Nobody".
- **FR12** The system shall close a round when the answer time runs out or every player has answered.
- **FR13** The system shall reveal the correct song, who listens to it, and the points earned after each round.
- **FR14** The system shall not play the same song twice in one game.
- **FR15** The system shall show a room leaderboard after each round and a final ranking at the end.
- **FR16** The system shall end the game for everyone if the host leaves.
- **FR20** The system shall start the next round only when the host taps "Next" after the reveal.
- **FR21** When decoys are on, the system shall include rounds with a song that no player in the room has, where the correct "who" answer is "Nobody".

### Data & history
- **FR17** The system shall store each room's songs and game results for **30 days**, then delete them automatically.
- **FR18** The system shall let anyone with the room code view that room's past games and final scores during those 30 days.

### Demo mode
- **FR19** The system shall offer demo mode with fake players, songs and bundled playable clips, requiring no API keys or external music calls. Without provider keys, real song entry remains manual.

## Non-functional requirements
| ID | Category | Requirement |
|---|---|---|
| **NFR1** | Performance | A new round loads in **under 2 seconds**. |
| **NFR2** | Capacity | Supports 3–10 players per room and about 20 rooms at the same time. |
| **NFR3** | Usability | Works in a phone browser; joining takes only a code and a nickname. |
| **NFR4** | Reliability | If a song has no preview or Apple is unavailable, the game continues (the song is skipped); the app doesn't crash. |
| **NFR5** | Privacy | Stores only nicknames, a random session ID per player (for FR5), songs and game results, and deletes them after 30 days. Provider user tokens are used for an import and discarded; they are not persisted. Session and callback details are decided in phase 07. |
| **NFR6** | Portability | Runs with no API keys (demo mode). |
| **NFR7** | Deployability (§7) | One start command; binds to `0.0.0.0`; port from `PORT`; SQLite file under `DATA_DIR`; all config through environment variables; no manual setup; ready within a few seconds. |
| **NFR8** | Architecture constraint | Single process, SQLite only; the 30-day cleanup runs inside the app (no cron job or separate worker). |
| **NFR9** | Maintainability | Unit tests cover **≥70%** of the rooms and game logic. |

## Decided later
- Scoring, difficulty and song selection are specified in `03_GAME_RULES.md`; domain boundaries and live updates are in `05_ARCHITECTURE.md`.
- Session/callback handling, room code format and host-disconnect grace period → phase 07 (security/API design).
- All-device audio needs retained evidence of ≤300 ms start drift and audible playback on both devices before it is enabled; `04_POC.md` records a functional check with timing still pending.
