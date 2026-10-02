# 05 — Architecture

Date: 2026-10-01. Backend PR #1 is integrated; `feature/frontend` adds the
redesigned browser client and unrestricted selected-song metadata search. The
earlier `feature/demo-core` checkpoint retains its temporary UI. The 2026-10-02
checkpoint adds Spotify PKCE imports and Apple developer catalog search/previews;
live five-account acceptance and optional all-device audio remain separate gates.
See [implementation status](08_IMPLEMENTATION_STATUS.md) for current evidence.
The PoC source stays on `POC`; its findings inform this design without proving
production readiness. [07_API_AND_RUNTIME.md](07_API_AND_RUNTIME.md) defines the
browser, command and runtime contract; [06_DATA_MODEL.md](06_DATA_MODEL.md)
defines persistence.

## 1. Evidence and first milestone

Apple developer-token catalog lookup, ISRC matching, previews and charts worked
in the PoC. Personal Apple listening history remains unverified. Spotify
supplied personal songs with Apple-resolved previews, but unique-song counts
and preview coverage were not retained. The two-device room worked over LAN;
its start-time drift was not retained. See [04_POC.md](04_POC.md).

The first milestone is a three-browser demo game with shared audio from the
host device. The host also guesses and sees the same game as every player;
there is no required central display. Only the host has administrative controls.
Normal now uses one Spotify development app for at most five approved accounts,
including the host. Its import policy is specified below; actual account and
physical playback verification remains required.
All-device audio remains conditional on audible playback and timing acceptance.

## 2. Ownership and data flow

| Component | Owns | Boundary |
|---|---|---|
| Rooms | Room mode/code, admission, room-specific browser credentials, host membership, nickname/character, provider authorization and imports, shared songs and familiarity, demo catalog, presence | Returns values through its service; does not select rounds or score answers |
| Game | Frozen roster/settings/song facts, complete round plan and reserves, readiness generations, deadlines, selected-song answers, scores, reveals and rankings | Receives snapshots; does not query Rooms tables or hold provider credentials |
| Application coordination | Authorization, room command ordering, cross-domain lifecycle transactions, provider work and runtime tasks | Calls narrow domain interfaces; repositories retain table ownership |
| Music adapters | Spotify account/top/recent data, Apple developer catalog and conservative preview matching | Return normalized facts; do not select game rounds or calculate scores |
| Music admission jobs | Cookie-bound PKCE receipts and bounded background imports | No SQL; invokes atomic Rooms admission only after a usable verified import |
| Catalog search | Shared public metadata, bounded provider cache/budget, signed room-scoped selections | No personal-history import, playback download or hidden listener lookup |
| Browser | Stable phase presentation, animated components, automatic acknowledgements, estimated server-clock offset, host playback | Server remains authoritative for identity, phase and scoring |

```mermaid
flowchart TD
    Browser["Phone browsers: HTML / CSS / JS"] -->|"JSON commands, polling and automatic ACKs"| App["FastAPI routes and application coordination"]
    App --> Rooms["Rooms service: admission, import and presence"]
    App --> Game["Game service: plan, readiness and scoring"]
    Rooms --> History["History adapters / SQLite demo catalog"]
    History --> Providers["Optional external music APIs"]
    App --> Audio["Preview adapters"]
    Audio --> Providers
    Rooms --> RoomsStore["Rooms repository"]
    Game --> GameStore["Game repository"]
    RoomsStore --> SQLite[("One SQLite file")]
    GameStore --> SQLite
```

The application uses one server process for the API, catalog assets and frontend.
`/` serves the browser entry, `/ui/` browser modules/assets, `/ui-lab` isolated
visual fixtures, and `/static/demo/` catalog media. The browser polls every 500 ms
with no overlapping state reads. Heartbeats are separate,
every five seconds. This is a design choice, not a demonstrated capacity result:
20 rooms × 10 players × 2 polls/second means about 400 state requests/second.
Final rankings remain visible. Polling/heartbeats retain the room identity and
allow returning to its lobby; browser visibility pauses continuous animation.

## 3. Admission and lobby preparation

The host chooses **normal** or **demo** at room creation, before anyone joins.
Normal requires verified personal music authorization for every player, including
the host, before admission. Imported songs are prepared automatically in the
lobby; Start stays disabled until required imports/checks finish. Demo explicitly
bypasses provider authorization and assigns hidden random fixtures from the
seeded SQLite `demo_catalog`, including local clips and optional covers.
Import failure never silently changes a normal room into demo mode.

The backend imports each player's candidates using that player's authorization.
The host's account does not expose other players' histories. Spotify imports
short/medium/long top lists and recently played tracks, deduplicates by ISRC or
track identity and balances familiarity strata into at most 60 candidates.
Short-term top 20 are easy, other short/medium/recent tracks medium, and long-term
only tracks hard; overlap takes the easiest level. These are affinity/rank-based
estimates, not historical play counts. At least ten playable personal songs are
required; this still does not guarantee enough unique songs for every game size
and checked replacement plan.
For the creator, Apple charts provide up to 30 independent decoy candidates,
with at least three playable decoys required by the current import. Decoys lose
that role if an observed player import contains the same recording. Unavailable
observed personal songs retain memberships but do not enter a game until usable
media is supplied by another import. Listener facts therefore describe the
bounded imported dataset, not a lifetime listening claim.

Import once per lobby pool build, not once per round. Membership changes can
require a new build. Players neither inspect nor manually choose the song pool.

Rooms deduplicates within each room and stores familiarity on each player–song
relationship. Provider secrets stay outside snapshots, SQLite song/game data and
browser-visible responses; transient personal authorization is discarded after
its required import. Provider calls have bounded timeouts/concurrency and run
outside SQLite transactions. OAuth state/verifiers and tokens live in expiring
server memory: 15-minute receipts, at most 64 receipts and eight processing jobs,
with two import workers. A temporary HttpOnly cookie binds authorization to its
initiating browser. Callback/state validation is single-use; cancellation removes
an unfinished receipt without admitting its player. Rooms revalidates lobby,
capacity, nickname and account uniqueness when the worker commits admission.
Lobby responses expose nicknames, character IDs,
connection/import readiness, counts and settings, never songs or listener maps.

## 4. The boundary at Start

Start checks the host identity, room revision, player limits, mode readiness and
settings. In a short transaction it locks room membership/imports, creates a
`preparing` game and copies the starting roster, including nickname and
`character_id`. Starting player identities remain eligible throughout the game;
new identities cannot join until the room returns to the lobby.

The application passes Game a value snapshot: room ID/revision/host, roster,
shared song identity/title/display artists/structured artist IDs/ISRC, optional
artwork, preview facts and each listener's familiarity. Game receives no Rooms
connection or user token. Repositories participate in shared local transactions
without querying one another's domain tables.

Setup prepares the full requested sequence and checked reserves. Each original
requested slot allows its initial candidate and up to three distinct substitutes
across setup and later recovery. Exhausted slots are skipped. Cancel if
`skipped_original_slots / requested_round_count > 0.30`; exactly 30% is allowed.
Never change the denominator after skipping. Announce the actual playable count;
original slot numbers remain stable and the surviving decoy proportion can differ.
Unique candidates and reserve budgets are checked before play. Freeze the
validated song snapshot/plan at preparation completion; mutable readiness and
attempt state are stored separately. No normal provider lookup occurs per round.

The five-second setup countdown is a minimum presentation period, not an import
or network guarantee. Continue showing preparation if needed. The host preloads
all planned audio and checked reserves during setup. Other browsers receive only
the current round's public data. The host audio controller needs private future
playback references for preloading; these references can reveal provider metadata
and do not offer secrecy against a participant inspecting their own browser.
Never include future song labels, correct markers or listener mappings in public
payloads. See the API contract for this trust limit.

## 5. Preview and artwork adapters

| Interface | Returns |
|---|---|
| History import | Normalized identities, credited artist identities, source-list signals and optional artwork |
| Preview resolution | Playable URL/source or unavailable, optionally artwork/credited artist metadata from the resolved catalog entry |
| Demo catalog | Fixture songs, familiarity assignments, stable artist IDs and local asset references |

The current Normal preview chain is the configured Apple developer catalog by
ISRC, then its title/artist search. Title/version and lead artist must match even
when ISRC agrees. Missing mandatory Spotify/Apple configuration blocks Normal
admission; no silent provider or mode downgrade occurs. Apple charts supply
independent candidate decoys; Demo uses its fixture pool. iTunes/Deezer preview
alternatives remain research options, not the active Normal chain. Browser
decoding and audible playback still need independent verification.

Artwork is a reference, not image bytes in SQLite. The Apple adapter resolves
`attributes.artwork.url` `{w}`/`{h}` placeholders to 300 each. Game freezes optional
imported artwork or preview-match enrichment, including decoys, without writing
Rooms tables. The reveal contract uses the snapshot and requires a frontend
placeholder if the image is absent/broken; it makes no catalog request and never
changes scoring. The backend stores and exposes optional artwork references and serves the
bundled demo cover. The reveal component displays a music-icon fallback for
missing or broken images.

Application composition wires configured Spotify, Apple, importer and receipt
adapters explicitly. Each adapter owns its narrow cache/transport responsibility;
Game holds none of their credentials. Additional providers belong behind these
normalized interfaces rather than a general music service accumulating unrelated
concerns. Public metadata search remains independent, as described below.

## 6. Game phase and failure ownership

The normal loop is `setup` (minimum 5 s) → `ready` (automatic check-ins) →
`countdown` (3 s) → `answering` (10/20/30 s, or all starting players submit) →
`reveal` (5 s) → `leaderboard` (5 s) → next `ready`. The final leaderboard stays.
There is no routine host Next action.

Game scopes ACKs to attempt and readiness generation. State versions order
browser updates; another player’s ACK does not invalidate an ACK. Initially
all starting players must ACK within ten seconds; timeout aborts preparation and
returns everyone to the lobby with affected nicknames. A later timeout keeps the
same unstarted attempt and offers host Retry (new ten-second generation) or
Continue without named unready players **from the barrier only**. Their roster,
score and answer eligibility remain. The host's audio readiness is mandatory.

Once required ACKs arrive, Game publishes a common future `starts_at_ms`; clients
estimate clock offset. ACKs prove state readiness, not audible playback or exact
synchronization. Server ordering/time govern answer acceptance and scoring.
During play, all screens show each nickname/character and Listening/Submitted
status, separate from connectivity; other players' guesses remain private in every phase. Reveal includes only the authenticated player's own answer alongside public correct-song/listener facts and rankings.

| Failure | Required behavior |
|---|---|
| Import fails | Report it; normal mode stays normal and cannot start while required imports are incomplete |
| Setup exceeds five seconds | Show preparation; never start an unchecked sequence |
| Initial readiness timeout | Abort setup, return lobby, name missing ACK players |
| Later readiness timeout | Host Retry or Continue; no unstarted answer/score is created |
| Playback fails before closure | Retain answers, mark attempt `void`, exclude points; use only checked frozen reserves and the original slot's remaining replacement budget |
| Cumulative skips exceed 30% | Abort with a clear cause; preserve labelled partial results if play began |
| Failure report after reveal | Reject; revealed results are final |
| Artwork unavailable | Placeholder; continue |
| Non-host disconnects | Preserve identity/answers; missing submission earns zero at deadline |
| Host disconnects | Current timed round can close; wait before next readiness window; expire after 60 s from last accepted heartbeat |
| Host explicitly leaves | Abort immediately; save labelled partial rankings |
| Server restarts | Void interrupted unclosed attempts, abort preparing/playing games, preserve revealed scores, restore surviving rooms to lobby |

Host refresh restores its identity but can interrupt shared audio. One active
host audio-controller lease prevents competing tabs. Prechecking cannot eliminate
browser rejection/network/device failures; void handling remains necessary.
Neither a readiness exclusion nor a stale heartbeat bypasses host audio or the
60-second grace. Host transfer is excluded in v1.

An in-process lifespan task advances deadlines/phases and checks presence even
without polls. Requests enforce expiry before accepting commands/heartbeats.
Close/score atomically once; retained `void` answers never contribute to rankings.

## 7. Module placement and runtime

| Area | Purpose |
|---|---|
| `backend/app.py`, `backend/core/` | Dependency wiring, configuration, health and lifespan |
| `backend/api/` | HTTP routes, strict request schemas, origin checks, cookies and rate limits |
| `backend/application/` | Per-room mutation ordering, authorization, cross-domain transactions and audio leases |
| `backend/rooms/` | Admission/credentials, membership/characters, presence, demo fixtures and repository |
| `backend/game/` | Preparation/selection, readiness/phases, pure scoring and Game repository |
| `backend/storage/` | SQLite connections and versioned schema migrations |
| `catalog/` | Runtime Demo metadata, bundled clips/cover and provenance; real-song population remains pending |
| `frontend/` | Stable screens, reusable animated components, catalog typeahead, polling/ACKs and shared host audio |
| `backend/catalog/` | Public metadata cache and signed room selections; separate from personal import |
| `backend/music/` | Spotify authorization/history, Apple catalog/preview matching, media checks and bounded admission jobs |
| `tests/unit/`, `tests/integration/`, `tests/support/` | Pure rules, actual service/persistence paths and isolated fixture helpers |
| `tools/` | Optional development and capacity probes |

See [the codebase map](09_CODEBASE_MAP.md) for concrete module ownership and
change locations. Provider adapters and Normal admission are implemented at
these boundaries; live account/device acceptance remains separate. Both feature domains
persist their own data. Deploy one worker/replica with SQLite on a
persistent compatible local volume under `DATA_DIR`; do not run a second writer
process. Offload synchronous database work from the async event loop. Enable
foreign keys and a busy timeout per connection. WAL requires compatible storage;
validate the selected Azure volume before enabling it. Backups must preserve a
consistent database including WAL contents. Provider calls never hold room locks
or transactions across network waits.

## 8. Acceptance and remaining decisions

Verify pure scoring plus real service paths: partial artist credit, empty
submitted Nobody versus missing blank, stale ACKs/retries, deadlines/closure races,
immutable snapshots, strict 30% arithmetic, shared replacement budgets, host
lease/grace and final reveal immutability. Verify rollback/startup/retention and
both domains' persistence. Browser checks must exercise three players through a
full demo game, preloading, automatic check-ins/phases, character/status rendering,
readiness recovery, audio failure, reconnect and cover fallback. Load-test the
400-polls/second scenario and measure the defined readiness/start target.

The executable migration matches the schema. Automated application evidence
and remaining browser/load acceptance gates are recorded in the implementation
status. Five real Spotify accounts, preview coverage and physical/all-device
audio remain independent verification gates. See [07_API_AND_RUNTIME.md](07_API_AND_RUNTIME.md) for
commands, timings, security and operational acceptance.

## 9. Browser and song-search boundaries

`frontend/app.mjs` composes focused `application/`, `transport/`, `audio/`,
`game/` and screen modules. Screen lifecycle and header controls have separate
owners; application orchestration receives transport/audio/storage dependencies.
Room services own rules while their repositories own SQL. Screens keep their DOM mounted and update keyed player cards; reusable
Web Components own sprite, selection, typeahead and waveform presentation. The character rig owns motion; its shared scheduler respects reduced motion and
pauses hidden/offscreen characters. CSS owns layout and presentation. The
host computes normalized waveform levels from decoded audio and sends them with
preload checks; other players receive those levels without playback references.
Absent waveform data uses plain progress, rather than fabricated music bars.

Song search authenticates the room identity, then queries shared demo metadata or
the configured Apple developer catalog outside the room command lock. Without
Apple credentials, Demo retains the public iTunes metadata adapter. It never filters by a hidden
room pool or reveals the answer. A bounded process cache and single-flight calls
share provider requests. A selected result carries a room-scoped expiring HMAC
token; answer acceptance freezes verified facts and checks expiry after retry
receipts, without external I/O. Game compares those facts against the frozen
correct song. Migration `002_song_selections.sql` removes choice slots and converts
historical selections into song facts while preserving points and rankings.

Metadata discovery is independent of Spotify authorization and audio import.
The Apple developer adapter requests structured artist relationships; verified
recording matches preserve Spotify canonical credits and attach Apple artist
aliases only for matching credited names. Missing relationships are not invented.
Provider outages, HTTP 429 and local request-budget exhaustion produce explicit
errors. Apple catalog access does not require each guessing player to have an
Apple account, but request rates and storefront coverage are finite. See [Apple’s search parameters and limits](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html)
and [the frontend design](10_FRONTEND_DESIGN.md).
