# Who's On Repeat

A music party game where players guess the song and who listens to it. Each player answers on their own screen; the **host device plays the sound**. All-device audio is a future feature.

Demo works without credentials and uses simulated listening histories. On a fresh checkout, the launcher installs the pinned [100-song Drive pack](catalog/README.md#install-the-drive-pack) once; subsequent games work offline. The sole default Demo contains 80 personal songs and 20 Nobody songs. Normal mode imports each player's Spotify top/recent tracks and resolves playable previews through Apple. Normal supports 3-5 approved Spotify accounts; Demo supports 3-10 players. The launcher's explicit `--playtest` option relaxes admission to two players and permits a shared Spotify account for testing.

## Run

The teacher should use **Demo**. Install Python 3.12+ and use a modern browser;
there is no frontend install or build. On macOS/Linux:

```bash
bash tools/run_demo.sh
# For a two-player test:
bash tools/run_demo.sh --playtest
```

On Windows, use `py -3 tools/launch_game.py demo`; the Python launcher also
works on macOS/Linux. First launch creates `.venv` and installs the single root
`requirements.txt`, which needs internet or a prepared package cache. It also
downloads the 98.02 MiB Drive music pack if the pinned installation is missing,
verifies the ZIP and every extracted file, then selects the complete pack.
Subsequent Demo launches and games work offline. A failed download or invalid
pack stops launch with setup guidance. For installation without contacting Drive,
run `python3 tools/setup_demo_pack.py --archive /path/to/whos-on-repeat-demo-100.zip`.
Demo ignores private `.env` settings and inherited provider/tunnel configuration;
it needs the installed pack, but no API keys, account, FFmpeg or Cloudflare. Its SQLite path is
`data/demo/whos_on_repeat.sqlite3` by default. Both launchers use the same documented
`DATA_DIR/whos_on_repeat.sqlite3` storage contract.

Open the **Open on this computer** URL printed by the launcher (normally
**http://127.0.0.1:8000/**), create a Demo room, and invite two friends. It also
prints a LAN address for devices on the same network. The host taps **Start game**,
which activates the host speaker before starting. **Resume audio** appears only
when an active game needs audio recovery. Guests submit guesses on their own screens. Search
runs when you click Search or press Enter. Demo assigns each player 36 hidden
songs from the 80 personal recordings; 20 independent decoys supply Nobody rounds.
Search covers the complete 100-song pack without revealing player assignments. Both creation options remain visible: the unavailable mode is disabled,
and the backend also rejects it.

To run the real game, configure the private provider settings described below,
keep the HTTPS tunnel forwarding to the app's port, then use:

```bash
bash tools/run_real_game.sh
# Windows: py -3 tools/launch_game.py real
```

This launcher loads `.env`, verifies the keys and exact Spotify callback, prints
the configured HTTPS game URL, and enables Spotify and Demo rooms. Use `--check` on
either launcher for read-only preflight after dependencies and the pack are
installed. It installs nothing and starts no server. Use `--port 8001` if another
server occupies 8000, `--data-dir /path/to/data` for another data location, or
`--demo-pack /path/to/complete/pack` for an explicit local pack. A launch from an
arbitrary working directory still resolves project files correctly. See the
[device launch guide](docs/16_DEVICE_PLAYTEST.md).

For other devices on the same Wi-Fi, open the host computer's LAN address (for example `http://192.168.1.80:8000/`). Invite friends uses a reachable origin, detects LAN IPv4 when opened through loopback, or uses `APP_PUBLIC_URL`. Local firewall and guest-network isolation can affect connectivity. Demo works over LAN HTTP with `COOKIE_SECURE=false`. With `COOKIE_SECURE=true`, both modes use HTTPS: the local entry page redirects to the configured HTTPS `APP_PUBLIC_URL`, preserving invitation codes. Direct HTTP session requests are rejected before admission. Spotify on other devices also requires the registered callback in the [device playtest guide](docs/16_DEVICE_PLAYTEST.md).

`/health/live` and `/health/ready` check startup; `/docs` is the interactive API reference. `/ui-lab` contains isolated visual fixtures. Native browser modules and media are served by the same process.

## Configuration

Configuration uses environment variables. `tools/run_demo.sh` deliberately
isolates Demo from `.env`; `tools/run_real_game.sh` loads literal `.env` values.
Direct `python -m backend` does not load `.env` and defaults to Demo; install the
pinned pack with `tools/setup_demo_pack.py` first. It prints
Uvicorn's bind address; use `127.0.0.1`, a LAN address, or the configured HTTPS URL
in the browser. `0.0.0.0` is a bind address, not an invitation address.

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Binds to `0.0.0.0`; one Uvicorn worker |
| `DATA_DIR` | `./data` | Directory containing the single application SQLite file |
| `APP_PUBLIC_URL` | empty | Reachable HTTP(S) origin for invitations |
| `COOKIE_SECURE` | `false` | Set true for HTTPS |
| `GAME_MODE` | `demo` | Launch profile: `demo` allows Demo; `normal` also allows configured Spotify |
| `DEMO_PACK_DIR` | pinned versioned installation | Explicit local Demo catalog/assets override; launcher verifies it |
| `PLAYTEST_MODE` | `false` | Explicit two-player/shared-account test mode |
| `SETUP_TIMEOUT_MS` | `60000` | Full-game preload timeout, 10000-120000 ms |
| `ROOM_CREATE_LIMIT` / `ROOM_JOIN_LIMIT` | `10` / `30` | Attempts per client address per minute |
| `SPOTIFY_CLIENT_ID` | empty | Spotify PKCE application ID |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8000/api/music/spotify/callback` | Exact registered callback; default follows PORT |
| `APPLE_TEAM_ID` / `APPLE_KEY_ID` | empty | Apple developer token identity |
| `APPLE_PRIVATE_KEY_PATH` | empty | Private MusicKit signing key outside source control |
| `APPLE_STOREFRONT` | `es` | Apple catalog region |

Normal needs a configured Spotify app, allowed accounts and Apple signing key. Import failure stays visible and never silently changes a room to Demo. OAuth tokens and import receipts are transient; only room-scoped account digests and normalized ownership facts persist. See [provider setup](docs/13_SPOTIFY_IMPLEMENTATION.md).

## Storage and catalog

**`DATA_DIR/whos_on_repeat.sqlite3`** stores all application tables in SQLite WAL mode. Rooms owns membership/listening facts, Game owns frozen games/attempts/answers, and Catalog owns public metadata, verified links and expiring media references. Separate repositories enforce ownership inside this one file.

Startup applies application migrations 001–006 automatically (`PRAGMA user_version=6`); Catalog version 3 is recorded separately in `component_schema_versions`. There is no separate catalog database or legacy-file import path. Public catalog tables contain no live game or listening-history data. The precommit cleanup removed obsolete local rooms/game histories while retaining public provider metadata, verified links and caches.

Verified recording/guess mappings are permanent for each provider/storefront/purpose and metadata fingerprint. They change when identity metadata or matching rules change, or a known incorrect edge is rejected. Query caches and preview URLs expire independently. Decoy songs come from Demo's independent 20-song pool or Apple chart candidates in Normal, with known room listeners excluded. Listener ownership is preserved even if preview resolution fails.

The 64-recording CC0 MusicBrainz starter supports local search immediately. Optional bulk metadata import uses the same database and does not download music:

```bash
python tools/setup_catalog.py --info
python tools/setup_catalog.py --all
# Or import an already downloaded CSV:
python tools/import_catalog.py /path/to/canonical.csv.gz \
  --database /path/to/data/whos_on_repeat.sqlite3 --limit 100000
```

Bulk setup needs `zstd` on PATH, downloads the pinned roughly 2.38 GB archive, verifies SHA-256, and streams selected columns without extracting the roughly 7.70 GB CSV. Without `--all`, it imports up to 100,000 input rows; download size stays the same. Downloads and generated data are ignored by Git. Bulk setup is optional and does not run at startup. See [catalog design](docs/14_CATALOG_OPTIMIZATION.md) and [Demo provenance](catalog/README.md).

## Architecture

A layered monolith, as Assignment 1 requires:

```text
Browser screens -> browser application -> HTTP transport
HTTP validation -> RoomCommands / GameCommands -> Coordinator
                                             -> Rooms / Game services
                                             -> owned repositories -> SQLite
Public search / personal import -> provider adapters
```

`backend/app.py` is the composition root. Named application operations own authorization, command ordering and transaction scope. Rooms exports value snapshots; Game freezes them and never reads live Rooms tables or calls providers while scoring. GameService owns time-driven and command-driven transitions. Scoped room locks remain shared while requests are queued and disappear when idle. Provider I/O runs outside room locks and SQLite transactions.

Browser application readiness belongs to every participant; the audio controller owns host leases, decoding and scheduling. Session generations and cancellation prevent responses from an old room restoring playback state. Signed room-specific song selections keep answer submission offline. Other players' guesses remain private, including from the host. Rankings count revealed attempts; void attempts retain diagnostic answers.

Details: [architecture](docs/05_ARCHITECTURE.md), [schema](docs/06_DATA_MODEL.md), [API](docs/07_API_AND_RUNTIME.md), [code map](docs/09_CODEBASE_MAP.md).

## Verify

Use Node 24+ for native frontend tests. The single root `requirements.txt` includes application and test dependencies. One local command runs isolated unit tests, real SQLite/HTTP integration tests and frontend tests:

```bash
bash tools/verify.sh
```

The assignment core-logic coverage command runs **unit tests only** over the Rooms service, Game service, scoring and planning:

```bash
python -m pytest -q tests/unit \
  --cov=backend.rooms.service --cov=backend.game.service \
  --cov=backend.game.scoring --cov=backend.game.selection \
  --cov-report=term-missing --cov-fail-under=70
```

Run the commands against the current checkout for test totals and coverage;
results from earlier packs are historical evidence. Unit coverage measures core
Rooms/Game service policy, scoring and planning separately from SQLite integration.
Full backend coverage can be measured with
`python -m pytest -q --cov=backend --cov-report=term-missing`.

Integration tests cover offline Demo ten-/fifteen-round games, pinned Drive
installation, Normal imports, exact deadlines, retries, concurrent answers,
privacy, room expiry and startup recovery. Frontend tests exercise actual
controllers with deferred transport/decoding, stale leases, readiness,
scheduling and UI-lab metadata/error handling. Tests use isolated application
data and avoid live provider credentials. Optional formatting check:
`uvx ruff format --check backend tests tools`.

See [current verification](docs/08_IMPLEMENTATION_STATUS.md) and the [assignment checklist](docs/17_ASSIGNMENT_REVIEW.md). The generated PDF at `output/pdf/assignment-report.pdf` is a local draft pending author review and is not included in the code checkpoint. Real account onboarding, physical phone playback and timing need device checks; automated results do not establish those outcomes. The optional `python -m tools.load_demo` probe measures ASGI state reads with isolated data and does not establish network capacity.

The pinned Demo pack contains 100 actual, unmodified previews (80 personal songs and 20 Nobody songs), totaling 98.41 MiB. Offline setup checks verified every SHA-256 checksum and full audio decode; all excerpts measure approximately 30 seconds. The original local pack and a fresh anonymous Drive download both completed ten- and fifteen-round HTTP/SQLite games in temporary data without provider keys or network calls during games. Drive installation verifies the pinned ZIP and every extracted file; repeated installation and later launches reuse verified local files offline. This verifies media delivery and game flow, not physical device audio.

## Assignment evidence

[ADR.md](ADR.md) has exactly five decisions with their historical dates and explicit later refinements. [AI_USAGE.md](AI_USAGE.md) records assistant use; explanations labelled drafts need the author's review in their own words. The professor approved the idea with “go for it” (user account; no approval date recorded). The [submission checklist](docs/17_ASSIGNMENT_REVIEW.md) distinguishes verified implementation from remaining author/process evidence. No student-authored Docker, CI, IaC or managed services are required or included.
