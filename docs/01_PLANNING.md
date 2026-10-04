# 01 — Planning

Updated 2026-10-04 against `test/optimized-game` at `528952a`. Earlier targets
retain their original deadlines; the outcome column records later evidence
without backdating acceptance. Original planning versions remain in Git history.

## Name
**Who's On Repeat**

## Goal
A party game where friends guess each other's music taste.

## Product reasoning
The original idea was a music-taste guessing game with Apple Music input,
listening-based difficulty and possible mashups. Feasibility work changed that
plan: Normal now uses Spotify observations and Apple catalog/previews, while
Demo assigns simulated libraries. Difficulty estimates familiarity from provider
rank/recency rather than claiming exact listening counts. Mashups remain excluded.
Competitor comparisons were exploratory, not verified market evidence.

## Scope (v1)

Updated after the Sep 29 PoC and Sep 30 decisions: build the playable demo first with assigned hidden song data. Normal real-song play needs a validated automatic history import; manual picks are out. All-device audio remains conditional. The app will be written from scratch. The host also plays on their own screen. Normal mode requires each player's music-provider authorization; the host explicitly chooses Demo to bypass it.

| Feature | Status | Why |
|---|---|---|
| Classic rounds | **In** | The core of the game |
| Apple Music import | Conditional | Personal history was blocked by the tester's missing subscription; requires a subscribed tester |
| Manual song picks | **Out** | Players must not select or inspect their song pool before play |
| Demo mode | **In** | Host explicitly selects it; assign 36 hidden songs per player from the pinned 100-song pack (80 personal, 20 Nobody) without provider sign-in or API keys |
| Player characters | **In** | One fluid blob with selectable colors, friendly eyes and gameplay emotions in lobby, round and results |
| Automatic round loop | **In** | Synchronized countdown, guessing, reveal and leaderboard; host controls recovery rather than every next round |
| Leaderboard (per room) | **In** | Simple, and part of the game |
| Room history (30 days) | **In** | Keep rankings, rounds, guesses and scores; the deadline is 30 days after the last completed game, or room creation |
| Audio on all devices | Deferred | Host-device audio avoids per-device autoplay/timing failures; the ≤300 ms target is not accepted |
| Decoy songs (host can turn off) | **In** | Adds surprise: some rounds play a song nobody in the room has |
| Spotify import | Implemented; live acceptance pending | Normal uses up to five approved accounts; complete independent-account coverage/device acceptance remains unverified |
| Mashup rounds | **Out** for Assignment 1 | Extra media processing would divert effort from reliable gameplay and verification |
| Chat, user accounts | **Out** | Not needed for a party game played in one sitting |

## Sep 30 scope clarification (historical requirements)

Players neither select nor inspect their song pool before play. Demo mode uses assigned hidden data from the demo database. The host selects Normal or Demo when creating the room, before players join. Normal mode requires successful music authorization, including for the host, and automatic personal-history import; failed access never silently changes the room to Demo. Provider choice, source lists, candidate counts and familiarity mapping remain to be validated.

The following lifecycle requirements still apply: import the lobby pool once
and precheck the full round sequence plus reserves. Start freezes players, characters and settings. The loop is setup (at least 5 seconds), automatic readiness, countdown (3 seconds), guessing, reveal (5 seconds), leaderboard (5 seconds), then the next round. A later readiness timeout gives the host Retry or Continue without the unready players; those players remain in the game's roster and ranking. See `07_API_AND_RUNTIME.md`.

## Stakeholders
| Stakeholder | What they want |
|---|---|
| **Players** | A quick game on their own screen; no game account, music-provider sign-in in Normal mode |
| **Room host** (a player and the only admin) | Choose mode/settings, start/end, play normally and resolve readiness failures |
| **Operator (me)** | Cheap and easy to run; no keys leaked |
| **Apple (and Spotify)** | Their API terms respected, which limits what I store and how audio is played |

## Assumed scale
Demo targets 3–10 players per room; Normal is limited to 3–5 approved accounts
by the configured Spotify development app. Explicit playtest mode permits two
players. The design target is about 20 simultaneous rooms on a busy evening. This is the target for the SQLite/single-process design, not a measured capacity. At 500 ms polling it implies about 400 state requests per second at full occupancy.

## Feasibility
- **Technical:** Apple catalog access worked, and Spotify songs with Apple-resolved previews played in the PoC. Apple personal history is still unverified. Current Demo uses the 100-song pack, and Normal admission implements automatic Spotify import. Isolated HTTP/SQLite tests establish game flow; independent live-account coverage and physical phone playback still need validation.
- **Operational:** friends use a code, nickname and character on their own browser; Normal mode also requires music authorization. Nothing is installed on player devices.
- **Economic:** Demo needs no provider credentials, but its real recordings require approximately 98 MiB of media installed once. Normal requires operator-managed credentials and approved accounts; actual deployment costs belong to Assignment 2.

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

## SMART goals and outcomes

| # | Original measurable goal | Deadline (2026) | Outcome recorded on Oct 4 |
|---|---|---|---|
| G1 | Commit planning through API/runtime design and the corresponding ADRs | Sep 30, revised from Sep 29 after adding game/runtime rules | Design milestones are visible in Sep 27–30 commits; ADR-4/5 first landed Oct 1, so the complete deliverable followed the revised deadline. |
| G2 | Three human players complete an automatic ten-round key-free Demo, including readiness, host audio and rankings, started with `python -m backend` | Oct 1 | Historical three-session browser games and fresh isolated-source, real-pack ten-/fifteen-round HTTP/SQLite games are recorded. These establish software flow; current three-human/physical-speaker acceptance remains a distinct gate. The four-song Oct 1 seed was a temporary checkpoint, not final acceptance. |
| G3 | Measure at least 70% unit coverage of Rooms/Game core rules | Oct 2 | Met at the recorded Oct 2 checkpoint (94% then). Final Oct 4 unit coverage is 94.05% over five declared core modules, including round preparation (Rooms 92.13%, Game 94.79%); see README for the command. The script enforces 90% overall and per domain. |
| G4 | Three players import at least ten songs each, with at least 80% playable unique candidates, and complete a real-music game | Oct 3 | Not accepted: import is implemented, but retained three-independent-account coverage and complete live playback evidence do not establish this goal. Demo remains the assessment path. |
| G5 | Fresh-source README run; at least 12 meaningful commits over six days; five ADRs over three dates | Oct 4, 23:59 | Local history has 12 substantive non-merge commits over eight dates and ADR introductions on four dates. Remote evidence identifies six push dates; a clean no-pack copy starts ready in 0.459 s. The five-page report is regenerated; author review and commit-by-push distribution remain tracked in the submission checklist. Playable Demo still requires installed music. |

These outcomes report evidence as of Oct 4; they do not claim every original
deadline was met. The original combined Demo checkpoint remains on
`feature/demo-core` (`bcdcd3d`). Backend PR #1 merged into `integration`; the
redesigned UI, song-search contract and single-pack cleanup are now included in
`test/optimized-game` at `528952a`. Subsequent local edits remain uncommitted.
Current test/browser evidence is recorded in
[implementation status](08_IMPLEMENTATION_STATUS.md); publication and submission
gates are in [the assignment checklist](17_ASSIGNMENT_REVIEW.md).

Song answers use signed catalog selections rather than four displayed choices.
Search metadata does not populate a player's hidden playback pool. The supplied
brief states Oct 4, 23:59; use that deadline unless the professor confirms a change.
Conditional integrations were cut before core verification and documentation.

## SDLC model

**Iterative and incremental, informed by Agile principles.** Recorded loops were
requirements/rules → provider PoC → domain/schema design → Demo backend → browser
UI → provider integration → device feedback and cleanup. Provider uncertainty
justified an early experiment; feedback changed scoring, privacy, invitations and
audio recovery before more features were added.

This was not formal Scrum: there is no evidence of fixed sprints, a Scrum team
or ceremonies. Some integrations and visual work consumed verification time,
and documentation reconciliation occurred late; the dated outcomes above make
that deviation visible. The author still needs to confirm this account against
their own experience and explain the resulting code independently.
