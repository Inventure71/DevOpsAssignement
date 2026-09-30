# 05 — Architecture

Date: 2026-09-29. High-level design for the app we will build from scratch.
The PoC source stays on `POC`; only its findings inform this design. The
diagram below describes the target structure, not an implemented application.

## 1. What the PoC changes

- Apple developer-token access worked for catalog search, ISRC matching,
  previews and charts. It does not grant personal listening-history access.
- Apple personal history is unverified because the available account could
  not obtain a Music User Token without a subscription.
- Spotify supplied personal songs and Apple-resolved previews played in the
  browser. The unique-song count and preview coverage were not retained.
- The two-device room worked after enabling LAN access. Its start-time drift
  was not retained, so synchronized playback has no quantitative acceptance yet.

The first playable milestone uses assigned demo songs and host-device audio.
The Sep 30 clarification hides the normal song pool and removes player song
selection from play; manual picks are excluded.
Apple history, Spotify import and all-device audio remain subject to validation.
History import and preview delivery therefore have separate interfaces.
See [the PoC results](04_POC.md#question-outcomes) for the evidence and limits.

## 2. Two feature domains

| Domain | Owns | Does not own |
|---|---|---|
| **Rooms** | Room codes, host/player membership, player identification, song lists, per-player familiarity, imports and lobby song counts | Round selection, guesses, scoring and game results |
| **Game** | Game settings, game snapshots, round selection, answer options, deadlines, guesses, scoring, reveals and rankings | Player identity, live membership edits and personal-history imports |

Each domain has a narrow service interface and its own SQLite persistence
code. A room can have several past games. Rooms history pages obtain those
results through Game's public service, without querying Game's tables.
Rooms maps source-list signals to familiarity; demo fixtures assign fixed
levels. Each room deduplicates its own song identities and keeps
familiarity on the player–song relationship. Game applies the
scoring and selection rules in [03_GAME_RULES.md](03_GAME_RULES.md).

## 3. Target architecture

```mermaid
flowchart TD
    Browser["Phone browsers: HTML / CSS / JS"] -->|"JSON requests and polling"| App["FastAPI routes and application coordination"]
    App --> Rooms["Rooms service"]
    App --> Game["Game service"]
    Rooms -->|"RoomSnapshot returned to application"| App
    Rooms --> History["History interface: assigned demo / validated imports"]
    App --> Preview["Preview interface: demo clips / Apple / iTunes / Deezer"]
    History --> Providers["Optional external music APIs"]
    Preview --> Providers
    Rooms --> RoomsStore["Rooms repository"]
    Game --> GameStore["Game repository"]
    RoomsStore --> SQLite[("One SQLite file")]
    GameStore --> SQLite
```

Everything except the browsers and external APIs runs in one process. The same
process serves the frontend. Use plain HTML/CSS/JavaScript and JSON polling
every 500 ms while in a lobby or game; stop polling after the game ends.
Polling is simpler than WebSockets for this scale. Its responsiveness and the
20-room target still need verification; the diagram is not a capacity result.

## 4. The boundary at game start

The application calls `rooms.service.get_room_snapshot(room_id)`, then gives
the snapshot to Game. The snapshot is an immutable value containing:

- Room ID, room revision and host player ID.
- Player IDs and nicknames.
- Song identity, title, artist and optional `artwork_url`, with each player's familiarity level.
- The listener IDs for each song, including shared songs.

The application resolves preview candidates before starting scored rounds and
passes those results separately. Game persists the snapshot facts it needs for
rounds and scoring. Imports and song changes are rejected during play and allowed again in the
lobby. Later changes cannot alter a game snapshot. Starting player identities
remain in Game even if they disconnect; new joins during play are rejected.
Before play, lobby responses expose counts/readiness, never the imported song
pool or listener mappings. Hiding an HTML element is not this boundary. Game receives values, not a database connection to Rooms or a
provider token. Returning players are identified by Rooms before a command
reaches Game; host-only commands are checked on the server.

Provider calls stay outside SQLite transactions. After preview preparation,
start-game coordination checks that the room revision still matches the
snapshot; membership, song or setting changes abort preparation for a retry.
It then validates the lobby, freezes membership/imports, saves the snapshot
and creates the game in one local SQLite transaction. Both
repositories participate in that transaction while retaining ownership of
their tables. A failed start leaves the room in its lobby state.
This is a local transaction, not a promise that a later distributed split is free.

## 5. History and preview interfaces

| Interface | Returns | Responsibility |
|---|---|---|
| History import | Normalized song entries, source-list labels and optional `artwork_url` | Convert provider-specific listening data into Rooms input |
| Preview resolution | A preview URL and source, or unavailable; optional artwork from the matched catalog song | Find playable audio and normalize available artwork without deciding listeners or score |

Demo assigns hidden song data and local short clips without credentials or a
remote API. Normal real-song play uses automatic import and server-side preview
resolution. Manual song picking is excluded. The first real import provider and its
familiarity mapping still need decisions; the PoC does not establish those
product choices.

For real songs, the preview chain is Apple by ISRC, then iTunes by title/artist,
then Deezer by ISRC. Missing credentials skip that provider; missing previews
make a song unavailable. Apple charts supply optional real decoys; demo mode
has a separate fixed pool. Provider calls happen during preparation, with
timeouts and bounded concurrency, not in scoring or the answer path.

Rooms persists artwork supplied with imported songs; demo fixtures supply
root-relative asset URLs. When an Apple catalog match supplies artwork, its
adapter resolves `attributes.artwork.url` placeholders `{w}` and `{h}` to
300 each. The application passes this optional artwork with preview results
during preparation; Game uses it when the incoming song has no artwork and
freezes the final reference for normal and decoy songs. Game never writes
Rooms tables. Reveal loads the image from that reference, with a bundled
placeholder on absence/load failure; no catalog lookup runs during reveal.
SQLite stores references, not image bytes. See the source details in
[the data model](06_DATA_MODEL.md#3-shared-songs-and-frozen-game-data).

`app.py` selects concrete adapters from environment configuration and passes
them into services. Use adapters and explicit dependencies; no global provider
singleton or general-purpose music service. Add more abstractions only when
the implementation needs them. Personal tokens are used for an import and
discarded afterwards; they are not part of the game snapshot or SQLite data.

## 6. Control flow and failure handling

1. **Lobby:** create/join a room, load songs without exposing their pool, choose
   settings. Rooms enforces the
   player limits and rejects joins once the game starts.
2. **Preparation:** validate song counts, resolve playable candidates, load the
   decoy pool and create the game snapshot. If preparation cannot build a
   playable round with four distinct options, starting fails with an explanation.
3. **Playing:** the server announces a future start time after host audio is
   ready. The browser preloads the clip; the server owns start/deadline times.
   Each answer is accepted at most once and timestamped by the server.
4. **Reveal:** close when all players answer or the deadline passes, calculate
   scores once, persist the result and show the answer and ranking. Cover art
   comes from the frozen snapshot; a missing/broken reference uses the bundled
   placeholder without failing the round or requiring a provider call.
5. **Next/finished:** only the host advances after reveal. Final rankings plus
   rounds, guesses and scores are saved; a completed game updates the room
   retention anchor in the same transaction. The room returns to its lobby.

Before handling a game request, Game checks whether an active round's deadline
has passed. Polling exposes the transition without a separate worker; late
answers are rejected even if the browser still shows the answering screen.
The polling interval is not the scoring clock.

| Failure | Planned behavior |
|---|---|
| Provider unavailable | Keep existing room songs; report the failed import or try the next preview provider |
| Clip fails during a round | Save the answers, mark the attempt `void`, exclude its points from rankings and replace the song if possible |
| Cover absent or image fails | Use the bundled placeholder and continue reveal/scoring |
| Empty decoy pool | Use a normal round, as specified in the game rules |
| Player refreshes | Restore identity and load the server's current state |
| Host explicitly leaves | Abort immediately for everyone and retain labelled partial results |
| Host disconnects | End after a 60-second grace from the last accepted heartbeat; late reconnects do not revive it |
| Non-host disconnects | Preserve the starting identity and accepted answers; missing answers are blank with zero points at timeout |
| No requests arrive | Enforce deadlines on the next request; never accept a late answer |
| Process restarts during a game | Mark the interrupted game as aborted; preserve already saved results without pretending the game completed |

A closed tab cannot reliably send a leave command. An in-process presence
check enforces the agreed 60-second host grace even if no browser is polling;
requests also enforce the deadline before accepting a returning heartbeat.
There is no external worker. The heartbeat interval, blocked-host-audio behavior
and exact retry protocol will be specified in the API/security design.

## 7. Implementation boundaries

| Area | Purpose |
|---|---|
| `app.py`, `config.py`, database setup | Start the server, wire dependencies, configure SQLite and coordinate cross-domain actions |
| `rooms/` | Public snapshot contract, membership/import service, familiarity logic, repository and history adapters |
| `game/` | Game service, round selection, pure scoring, result repository |
| `audio/` | Preview interface, adapters and demo clips |
| `static/` | Plain frontend, state polling and audio playback |
| `tests/` | Rooms and Game business-logic tests, persistence checks and a few integration checks |

This is a responsibility map, not a requirement to create an empty file for
every component. Final schema and file layout come with the low-level design.
Both domains must read/write SQLite to count toward the assignment.

## 8. Verification and next steps

- Unit-test scoring, selection, identity matching, familiarity, membership
  limits and state transitions, using a fixed random seed and fake adapters.
- Verify each domain's SQLite persistence and rollback on a failed game start.
- Check late/duplicate answers, repeated host commands, refresh, failed clips
  and interrupted games through the actual service paths.
- Check retained void-attempt answers never affect rankings, and frozen cover
  references use a placeholder on absence or load failure without a provider call.
- Play a 10-round demo game with three browsers and no API keys, including
  host-device audio. Then measure core-logic coverage against the 70% target.
- Check the deployment contract: one process, root `requirements.txt`, one
  start command, `0.0.0.0`, `PORT`, SQLite under `DATA_DIR`, automatic setup.
- Verify whole-room expiry 30 days after the last completed game (creation
  if none completes); Game deletes its data before Rooms, in one transaction.
  Heartbeats, visits and aborted games do not extend retention.
- Check the fixed roster, reconnect/new-join distinction, blank timeout answers,
  hidden lobby song data and both host-ending paths.

The planned schema and ADR-3 are now in [06_DATA_MODEL.md](06_DATA_MODEL.md).
Next: choose the first real import provider and its familiarity mapping, then
define API/session behavior and the testing approach. Remaining ADRs will be
added when those decisions are made; the app and its tests do not exist yet.
