# 08 — Demo Implementation Status

Evidence recorded 2026-10-01. Work began Sep 30 and remains uncommitted on the local
`feature/demo-core` branch. This records current evidence rather than treating
the earlier design or PoC as proof of the application.

## Implemented

The single-process FastAPI app serves vanilla HTML/CSS/JavaScript and stores
both Rooms and Game in `DATA_DIR/whos_on_repeat.sqlite3`. Migration 1 matches
the ten-table documented DDL exactly. Startup initializes/seeds storage,
aborts interrupted games with partial rankings, and cleans expired rooms.

Demo supports 3–10 real player identities, room-specific HttpOnly credentials,
nicknames/characters, hidden seeded assignments, host settings, frozen rosters
and song plans, one final submission, artist partial credit, submitted Nobody
versus missing answers, automatic readiness and timed phases, host audio leases,
checked reserves, void attempts, strict skip limits, and durable rankings/history.
The browser decodes the complete host manifest once and schedules the active
clip at the shared server start time. A later readiness timeout exposes Retry or
Continue without every named unready non-host player from the barrier only.

The runtime catalog now contains exactly four temporary fictional personal-pool
songs, with four original 30-second MP3s and one temporary SVG cover. Null
artwork references exercise the missing-cover path. The earlier 120-song bulk
fixture catalog and its generator have been removed. No music account or network
music API is used. These four songs support lobby/data-flow checks but cannot
supply a complete match under the existing distinct-song, decoy and replacement
rules. Start rejects an insufficient pool; the rules have not been weakened.
The current seed fails the unchanged ten-songs-per-player start requirement
with `insufficient_songs`, so it does not support playing a round through the
normal browser flow. Startup refreshes the shared catalog without altering
existing room songs or frozen snapshots; use new rooms or a fresh `DATA_DIR`
for current-seed checks, since old rooms can still reference retired assets.
Tests and the load probe use larger metadata fixtures only in temporary data.

## Codebase organization

Backend code is grouped into transport, application coordination, shared core,
storage and the existing Rooms/Game domains. Browser code and media live in
`temporary_frontend/`; runtime song metadata lives in `catalog/`. Tests are separated into
Python unit/integration tests, frontend checks and support helpers. Runtime and developer dependencies are
separate, and package entry points remove working-directory import hacks.
See [the codebase map](09_CODEBASE_MAP.md). The reorganized tree passed **93
Python tests**, with **93% Rooms/Game coverage**, and **12 frontend behavior
checks** against the production modules. Both pytest entry points work from the
root. A new real-resource integration test verifies schema, catalog, HTML and
static assets while the process runs outside the checkout. Compilation, all
ES-module syntax checks, and Git whitespace checks passed.

The packaged CLI was started with `python -m backend` and returned healthy.
The native browser loaded all nine modules, created a host room through the
normal form, joined a guest from a separate origin, and restored the host on
refresh. A third player joined through an independent HTTP cookie jar; both
browser sessions showed the three-player roster, with four songs per player.
Host audio activation succeeded, while Start remained disabled with the explicit
insufficient-catalog message. This is startup/lobby/module integration evidence,
not a new complete-game or physical-audio acceptance run.

The relocated module load probe completed **40/40 state reads** across 20 rooms
with ten identities each, leaving game versions unchanged. This repeat check
used temporary metadata and measures local ASGI reads rather than network load.

## Automated evidence

The following commands target the reorganized layout. Install developer
dependencies before running tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
for module in temporary_frontend/static/js/*.js; do
  node --input-type=module --check < "$module"
done
node tests/frontend/client.test.mjs
```

Before codebase reorganization, the four-song cleanup was checked in a Python
3.12.2 environment with SQLite 3.46.0: **92 tests passed; combined Rooms/Game coverage
93%.** Game service coverage is 94%, phase transitions 94%, repository 100%,
and public projections 95%. Rooms service coverage is 91%. Full-match tests
explicitly seed larger temporary metadata pools. Separate checkpoint tests use
the actual bundled four-song catalog through FastAPI startup, three-player
admission, asset delivery and rejected Start without bypassing the ten-song rule.
Reseeding tests verify removal of retired global entries, preservation of existing
room copies and snapshot values, and no catalog changes after invalid input.
The combined result measures actual domain modules, including persistence,
rather than routing alone. JavaScript syntax and Git whitespace checks passed.

Tests use real temporary SQLite databases and injected clocks. Coverage includes
concurrent final submissions; closure committed before rejecting a late answer;
exact deadline and host-grace boundaries; durable command/answer retries;
readiness generations and excluded-player eligibility; setup and later timeout
recovery; shared four-candidate replacement budgets; strict 30% boundaries for
5/10/15 rounds; frozen metadata; void-score exclusion; ten-round completion;
restart recovery; retention deletion; room cookie isolation; and host authority.
The final leaderboard completes during host absence when no next round remains.

All four retained clips have distinct hashes, are 30-second MP3s, and passed
ffprobe inspection and complete ffmpeg decoding. The referenced cover exists;
no retired clips or covers remain. File checks do not prove physical audibility.
The earlier 120-track asset inspection predates this cleanup.

Before runtime and developer dependencies were separated, a fresh temporary
virtual environment installed the then-combined `requirements.txt`; all
six API integration tests passed there, including startup/seeding.

The browser submission handler was also exercised with deferred responses:
a late receipt cannot mark a different round submitted, accepted receipts survive
older polls, and new-game state clears the local receipt cache. A script boot
check without `crypto.randomUUID` or Clipboard access verifies the LAN-HTTP
fallbacks. Neither check substitutes for testing actual phone browsers.

## Browser evidence

The following run used the earlier large fixture catalog, before the four-song
cleanup. It validates the implemented game loop under that test data and is not
a claim that the current four-song seed supports a ten-round match.

The T3 collaborative browser ran three separate player sessions using
`localhost`, `127.0.0.1`, and `localhost.` origins, each with its own room cookie.
Host, Ada and Grace joined through the browser UI. Host audio activation produced
a running AudioContext, and 40 planned/reserve clips decoded before play.
The ten-round game advanced through automatic check-ins, countdowns, answering,
reveals and leaderboards, then completed with identical final rankings on the
sessions inspected. SQLite confirms ten revealed attempts, 27 submitted answers
and three missing answers, retained separately with zero missing-answer points.
Automated DOM clicks supplied test guesses; background-tab scheduling affected
some submissions. No JavaScript errors were captured in the session traces.

Both a null cover reference and a deliberately broken image URL displayed the
bundled placeholder. A 375 × 667 viewport showed no horizontal overflow in the
inspected game screen. This is a desktop engine at a phone-sized viewport,
not physical iOS/Android acceptance. The preview screenshot tool failed;
verification used page inspection and interaction tools, and no screenshot or
visual-polish acceptance is claimed.

The native preview was intermittent after viewport changes. Final completion is
also verified independently through persisted game/round/answer data. Browser
refresh after completion restored the host identity and the final ranking, and
Back to the listening room restored the lobby. The latest submission/HTTP-LAN
fixes have separate handler checks; the complete ten-round run preceded them.

## Capacity evidence and limits

```bash
python -m tools.load_demo
```

The probe now runs as a module. The measurements below predate structural
reorganization. This repeatable probe prepares 20 active answering-phase games with ten players
each in temporary SQLite storage, then calls the actual ASGI state endpoint
400 times with 20 workers. Injected time holds the answer windows steady.
All **400 requests succeeded**, game versions stayed unchanged during reads,
and the measured throughput was **463.7 requests/second**, median **40.6 ms**,
p95 **75.5 ms** on the development Mac. Removing redundant per-poll database
connections improved the earlier 289.9 requests/second result.

This measures server state reads through the real application, including its
identity checks and projections. It excludes HTTP network transport, concurrent
answer/closure workloads and browser delivery. It is preliminary capacity evidence,
not Azure/storage/load acceptance. The complete two-second readiness/start trace
and supported-device synchronization target still need dedicated measurement.

## Remaining gates

- Populate the runtime Demo catalog with recognizable real songs, including
  the requested Kanye selections, enough personal/decoy candidates and checked
  replacements for supported match lengths. Redesign the current draft UI.
- Select and validate a real provider, authorization protocol, import source/count
  policy, familiarity mapping and complete artist credits. Normal admission
  explicitly returns `provider_unavailable`; no fake authorization is accepted.
- Verify audible shared playback, autoplay/refresh/background behavior and timing
  on actual supported phones/browsers, with three people through a full game.
- Measure readiness delivery under the defined network/device/load conditions.
  Optional all-device playback stays disabled until its separate drift/audio gate.
- Validate persistent SQLite WAL storage and backups for the eventual Azure setup.
- Complete the course report, user-owned comprehension explanations, and genuine
  commit/push cadence. No commit dates or remote publication are invented here.

No Dockerfile, CI workflow, infrastructure definition or public deployment was
added. Lobby settings are process-local before Start; restarting restores the
last frozen game settings, or defaults. Only completed games renew retention.
See [README](../README.md) for setup, configuration and module boundaries.
