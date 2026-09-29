# 02 — Requirements

## How the game is played
Each player uses their own phone browser (no app to install). By default players are **together in the same place**: the **host's device plays the clip** out loud, and the other phones are used to answer. The host can switch to **all devices**, so every phone plays the clip (useful when players aren't together). The app itself runs on a server (Azure in Assignment 2), so everyone opens the same URL.

## Game settings (chosen by the host)
| Setting | Options | Default |
|---|---|---|
| Rounds | 5 / 10 / 15 | 10 |
| Answer time | 10 s (flash) / 20 s / 30 s (slow) | 20 s |
| Audio playback | Host device only / All devices | Host device only |
| Game difficulty | Easy / Mixed / Hard | Mixed |
| Decoy songs | On / Off | On |

## Functional requirements

### Rooms & players
- **FR1** The system shall let a player create a room and receive a unique join code; the creator becomes the **host**.
- **FR2** The system shall let a player join a room with the join code and a nickname, with no account or password.
- **FR3** The system shall reject a nickname already used in the same room.
- **FR4** The system shall reject joining when the room has 10 players or the game has already started.
- **FR5** The system shall recognise a returning player after a page refresh, without accounts.
- **FR6** The system shall let a player add songs by importing their Apple Music history, or by picking songs manually.
- **FR7** The system shall show each player's song count in the lobby.
- **FR8** The system shall let the host choose the number of rounds, the answer time, the audio playback mode, the game difficulty and whether decoy songs are used.
- **FR9** The system shall let the host start the game only when there are 3–10 players and every player has at least 10 songs.

### Game
- **FR10** The system shall play a clip of one player's song each round, without showing the title, on the host's device only, or on all devices if the host chose that mode.
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
- **FR19** The system shall run with fake players and songs when no Apple Music keys are configured.

## Non-functional requirements
| ID | Category | Requirement |
|---|---|---|
| **NFR1** | Performance | A new round loads in **under 2 seconds**. |
| **NFR2** | Capacity | Supports 3–10 players per room and about 20 rooms at the same time. |
| **NFR3** | Usability | Works in a phone browser; joining takes only a code and a nickname. |
| **NFR4** | Reliability | If a song has no preview or Apple is unavailable, the game continues (the song is skipped); the app doesn't crash. |
| **NFR5** | Privacy | Stores only nicknames, a random session ID per player (for FR5), songs and game results, and deletes them after 30 days. Handling of Apple login tokens is decided in phase 07. |
| **NFR6** | Portability | Runs with no API keys (demo mode). |
| **NFR7** | Deployability (§7) | One start command; binds to `0.0.0.0`; port from `PORT`; SQLite file under `DATA_DIR`; all config through environment variables; no manual setup; ready within a few seconds. |
| **NFR8** | Architecture constraint | Single process, SQLite only; the 30-day cleanup runs inside the app (no cron job or separate worker). |
| **NFR9** | Maintainability | Unit tests cover **≥70%** of the rooms and game logic. |

## Decided later
- Scoring, difficulty and how songs are picked → `03_GAME_RULES.md`
- Token storage and room code format → phase 07 (security)
- How clips start at the same time on all devices → tested in `04_POC.md`, designed in architecture
