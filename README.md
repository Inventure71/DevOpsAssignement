# Who's On Repeat

A music party game for **3–5 approved Spotify accounts in Normal mode**, or
3–10 people in explicit Demo mode. The host also plays; everyone guesses on
their own screen and the host device supplies the shared speaker. This branch
contains the game backend, redesigned browser UI and Spotify/Apple provider
integration. Demo still has four temporary fictional songs and hidden assignments. The lobby and round design uses
one animated fluid blob with selectable pastel colors, direct player selection
and catalog song search. Friendly idle eyes and sad/correct-song reactions use
server-revealed outcomes.
Normal admission uses Spotify authorization and top/recent-song imports, with
Apple developer catalog search and preview resolution. Real five-account and
physical-audio acceptance remain pending; implementation is separate from those
live checks. Real-song Demo catalog population is also pending.

The [provider checkpoint](docs/13_SPOTIFY_IMPLEMENTATION.md) describes setup,
boundaries and remaining checks. The [music provider comparison](docs/12_MUSIC_PROVIDER_OPTIONS.md)
preserves alternatives and tradeoffs; the accepted scope is one Spotify app with
five approved accounts, including the host.

## Run locally

Python 3.12+ is recommended. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend
```

Open **`http://127.0.0.1:8000/`**. Choose Spotify for Normal mode or Demo for
no-credentials lobby checks. Spotify needs the configuration below and the exact
callback registered in its developer dashboard. The browser UI
uses native ES modules (`.mjs`) and Web Components; no npm manifest, installation
or frontend build is required. `/docs` contains the interactive API reference, `/openapi.json` its
schema, and `/health/live` and `/health/ready` the process/initialization checks.
`/ui-lab` displays isolated design fixtures and standalone character components;
it does not create a real room or start a match.

For friends on the same Wi-Fi, open this computer's LAN address instead of
`localhost` (for example `http://192.168.1.80:8000/`). The server already listens
on all interfaces. **Invite friends** includes the room code and uses that
reachable origin; when the host opens a loopback address, the server detects its
outbound private IPv4 address instead. Allow Python through the computer's
firewall if prompted. Guest Wi-Fi isolation can prevent devices from connecting.
Set `APP_PUBLIC_URL` to override detection for multiple interfaces, a proxy, or
HTTPS hosting. LAN HTTP supports Demo joining; Normal Spotify admission still
requires the shared HTTPS address and registered callback described below.

Create a Demo room through `POST /api/rooms` with a nickname and character, then
join using its room code from separate browser sessions. The API sets a
room-specific identity cookie; keep that cookie when requesting room state or
issuing commands. See [the API contract](docs/07_API_AND_RUNTIME.md) and the
interactive request schemas for the complete fields and host-audio lease flow.

The four-song seed supports admission, lobby, persistence and media-delivery
checks. It is too small for a complete match: Start requires at least ten songs
per player, and planning needs distinct songs, an independent decoy pool and
checked replacements. A Start request with this seed returns
`insufficient_songs`. Larger isolated test fixtures exercise the full game loop.
The minimum and selection rules remain in force while the catalog is populated.

The frontend enables host audio with a tap, preloads the planned clips and
reserves, sends automatic check-ins, and displays countdowns, reveals and
rankings. A three-session ten-round browser run passed with isolated larger
metadata fixtures. Physical-device audio and synchronization acceptance remain
pending. Only the active host audio controller receives the private playback
manifest. Demo familiarity is fictional; it does not import anyone's listening
history. Normal mode verifies each player's own Spotify account before adding
them to a room. Missing configuration or failed imports produce explicit errors
and never silently change to Demo. Its five-account allowance belongs to the
Spotify application, not to each room; the room also enforces at most five
players and one identity per Spotify account.

## Song guesses

Type a title or artist and select a result from the loading search list. Guesses
are not limited to four round choices. Shared fictional catalog metadata is
searched locally in Demo; other queries use the configured Apple developer
catalog, or the public iTunes metadata fallback when Apple is not configured.
Loading, empty, failure and rate-limit states are explicit. Search does not import
songs or change the four-track Demo playback catalog. Apple catalog search uses
server credentials; guessing players do not need Apple accounts or Spotify
catalog authorization. It is rate-limited, not unlimited.

The server signs each selected song for the room, then verifies that selection
on submission and freezes its metadata in the answer. Scoring uses recording
identity or a compatible normalized title with a shared structured artist identity.
ISRC helps locate recordings but does not alone establish a correct guess.
Apple preview matching adds artist aliases only when the resolved recording's
credited names match; artist partial credit uses those frozen identities.
No provider request runs at the answer deadline. Missing featured credits remain
unavailable rather than being guessed from a display string. See
[the matching rules](docs/03_GAME_RULES.md) and [the provider checkpoint](docs/13_SPOTIFY_IMPLEMENTATION.md).

## Configuration and storage

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | HTTP port; binds to `0.0.0.0` |
| `APP_PUBLIC_URL` | empty | Reachable HTTP(S) origin for invitations; otherwise use the request origin or detect LAN IPv4 for loopback requests |
| `DATA_DIR` | `./data` | SQLite directory |
| `COOKIE_SECURE` | `false` | Set `true` when served over HTTPS |
| `PLAYTEST_MODE` | `false` | Allow two-player games and the same Spotify account in separate player sessions; lobby displays a playtest notice |
| `SETUP_TIMEOUT_MS` | `60000` | Bounded full-game preload window (10000–120000 ms) |
| `ROOM_CREATE_LIMIT` | `10` | Room creation attempts per client address per minute |
| `ROOM_JOIN_LIMIT` | `30` | Join attempts per client address per minute |
| `SPOTIFY_CLIENT_ID` | empty | Development app for per-player OAuth PKCE imports |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8000/api/music/spotify/callback` | Exact callback registered in the Spotify app; default follows `PORT` |
| `SPOTIFY_CLIENT_SECRET` | empty | Optional Spotify public-search adapter; not required for the active PKCE/Apple flow |
| `APPLE_TEAM_ID` | empty | Apple developer token issuer |
| `APPLE_KEY_ID` | empty | MusicKit signing key identifier |
| `APPLE_PRIVATE_KEY_PATH` | empty | Absolute path to the private `.p8` key, outside the repository |
| `APPLE_STOREFRONT` | `es` | Apple catalog storefront |

Configuration is read from the process environment; private files are not
automatically loaded. Keep keys and secrets outside Git. Normal mode requires
Spotify client/callback configuration and a readable Apple signing key. The
PoC's callback `http://127.0.0.1:8765/callback` is different and does not register
the application's callback. Five real accounts must be approved in the same
Spotify development app. Five separate devices need a reachable HTTPS game URL
and its exact callback, rather than the server computer's loopback address.
When a LAN device opens a server configured with a loopback callback, the UI
explains that multiplayer Spotify sign-in needs network setup; it never sends
that device to `127.0.0.1`. A local `localhost` browser can still follow the
configured loopback address for sign-in on the server computer.

If Spotify displays **Invalid redirect URI**, register exactly
`http://127.0.0.1:8000/api/music/spotify/callback` for local testing, or the exact
HTTPS `SPOTIFY_REDIRECT_URI` for shared-device testing. The redirect URI must
match the dashboard entry, including its path. An authorization link reaching
Spotify's login page does not verify the callback registration or allowlist;
check the round trip after signing in with an approved account.
Failed imports stay on the music-loading screen with the provider's safe error
message and available preview counts. Return to sign-in explicitly to retry.
Server diagnostics record failure codes and, for unexpected exceptions, source
frames without exception messages, credentials, or personal listening data.

For Normal mode, fill an ignored `.env` using [.env.example](.env.example), then:

```bash
set -a
source .env
set +a
python -m backend
```

For a two-device playtest with one Spotify account, set `PLAYTEST_MODE=true`
before starting the server. Use separate devices or browser sessions and different
nicknames. Both players still complete Spotify sign-in and preview checks, and
each receives a separate room credential. Shared songs count both players as
listeners. The ten-song minimum, audio checks and room capacity still apply.
The lobby displays a playtest notice. Set the flag back to `false` and restart
to restore three-player starts and duplicate-account rejection; existing account
hashes remain available to that rejection check.

SQLite lives at **`DATA_DIR/whos_on_repeat.sqlite3`**. Startup applies versioned
migrations, seeds the catalog and recovers interrupted games automatically.
Startup refreshes the shared fixture catalog; existing room songs and frozen
snapshots stay unchanged and can still reference assets from an earlier catalog.
Create a new room, or use a fresh `DATA_DIR`, when checking the four-song seed.
No music credentials, ffmpeg, Dockerfile or manual migration are needed to start
the Demo app. Searching beyond shared fixtures needs network access to Apple;
startup remains independent of provider availability. Use **one process / worker / replica**, with
persistent local storage that supports SQLite WAL.

Only a completed game renews the whole room's 30-day retention. A restart aborts
unfinished games, retains revealed scores, and returns surviving rooms to the
lobby. Lobby settings are process-local until Start freezes them; a restart
restores the last game's settings, or defaults before the first game. Back up a
running database with SQLite's backup API, rather than copying only its main
file while WAL writes are active.

Room credentials are random HttpOnly cookies scoped to that room, with only
SHA-256 digests stored. Room URLs preserve each tab’s room across refresh, while room cookies restore the player; a nickname never recovers
lost identity. Multiple host tabs must explicitly take over audio ownership.
Moving the controller during an unrevealed attempt voids that attempt rather
than replaying the song.

## Structure

| Directory | Responsibility |
|---|---|
| `backend/api/` | HTTP routes, request validation, cookies, origin checks and rate limits |
| `backend/application/` | Command ordering, cross-domain lifecycle transactions and host audio leases |
| `backend/rooms/` | Admission, membership, familiarity, demo assignment and room snapshots |
| `backend/game/` | Frozen plans, readiness, phases, scoring, guesses and rankings |
| `backend/storage/` | SQLite connections and versioned migrations |
| `backend/core/` | Configuration, shared errors and repository-relative resource paths |
| `backend/catalog/` | Public metadata search/cache and room-scoped signed selections |
| `backend/music/` | Spotify PKCE/history, Apple catalog/previews and bounded admission jobs |
| `frontend/` | Browser composition, API transport, audio, screens and reusable components |
| `catalog/` | Four temporary song records, bundled clips/cover and their provenance |
| `tests/` | Python unit/integration tests and isolated metadata fixtures |
| `tools/` | Optional development and measurement commands |

`backend/app.py` wires the application and owns startup, health and background
work. Run it through `python -m backend`. Catalog assets live in
`catalog/assets/` and are served at `/static/demo/`. Browser assets are served
separately at `/ui/`; catalog media does not belong to presentation code. Runtime packages are in `requirements.txt`;
tests and measurements add `requirements-dev.txt`. See the
[codebase map](docs/09_CODEBASE_MAP.md) for module boundaries and change locations.

Browser code groups command/state orchestration in `frontend/application/`, HTTP
in `frontend/transport/`, playback in `frontend/audio/`, pure display projections
in `frontend/game/`, and presentation in `frontend/screens/` and
`frontend/components/`. The isolated lab keeps its fixtures, studio and controller
in `frontend/lab/`.

Both domains persist through SQLite. Game receives plain snapshot values from
Rooms and does not query Rooms tables. Submitted empty listener selections mean
Nobody; absent submissions mean No answer and score zero. Artist partial credit
uses frozen structured identities. Rankings count revealed attempts only;
void attempts retain diagnostic answers. Artwork references are optional; the reveal UI displays a music-icon fallback
when an image is missing or fails. Results show the correct song, actual listeners
and your own answer feedback. Other players' guesses remain private, including
from the host; shared standings show scores and ranks.

## Verify

Use Node 24 or newer for the native frontend module tests. No npm setup is needed.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
node --test tests/frontend/*.test.mjs
```

Tests use real temporary SQLite databases and injected server clocks. They
exercise both domains, ten-round games, concurrent final submissions, exact
deadlines, immutable snapshots, retries, readiness exclusions, replacement
budgets, host expiry, restart and retention. Catalog integration tests check
startup and media delivery, frontend serving, signed catalog selections and
version-1 database upgrades. Frontend module tests exercise receipts, polling,
clock estimates, submission races, owner-only result fixtures, decoded waveform
measurements and OAuth callback/import polling recovery. Current evidence and
remaining acceptance work are recorded in
[implementation status](docs/08_IMPLEMENTATION_STATUS.md).

A successful automated run does not prove physical audibility, phone-browser
compatibility, the optional 300 ms all-device drift target, or deployment load
capacity. Those checks require appropriate devices and a complete browser game. See the
[architecture](docs/05_ARCHITECTURE.md), [rules](docs/03_GAME_RULES.md),
[data model](docs/06_DATA_MODEL.md), and [API contract](docs/07_API_AND_RUNTIME.md).

The four audio fixtures are temporary original synthesized compositions; see
[catalog provenance](catalog/README.md). Real-song population is a separate
catalog milestone.

The optional local capacity probe uses isolated temporary data and 20 active games:

```bash
python -m tools.load_demo
```

It measures the actual ASGI state endpoint for 20 rooms × 10 players, with
400 requests and 20 workers. It excludes real network and browser delivery,
so its measurements describe server capacity rather than deployment acceptance.

The optimized catalog keeps public metadata and expiring preview references in
`DATA_DIR/catalog.sqlite3`, separate from private room listening history. A small
CC0 starter catalog works immediately; the streaming import tool can expand it
without per-search provider requests. See [catalog optimization](docs/14_CATALOG_OPTIMIZATION.md)
for the bulk import command and the additive local search/selection API.

To populate the local public search catalog from the pinned official metadata dump:

```bash
python tools/setup_catalog.py --info
python tools/setup_catalog.py --all
```

Setup requires `zstd` on `PATH`. It downloads the roughly 2.38 GB metadata archive
once, verifies the published SHA-256, and streams the needed CSV fields into
`DATA_DIR/catalog.sqlite3` without extracting the roughly 7.70 GB CSV. Downloads
are resumable and live under `DATA_DIR/catalog-downloads/`; both downloads and
the generated database are ignored by Git. Without `--all`, import is limited to
100,000 input rows, but the archive download is still the same size. No audio,
provider verification, or private listening history is downloaded by this setup.

For the combined device test checkout, run `bash tools/run_playtest.sh` to load
the existing local provider configuration, enable two-player testing and print
the shared device URL. See [the device playtest guide](docs/16_DEVICE_PLAYTEST.md).
