# 08 — Demo Backend Implementation Status

Evidence recorded 2026-10-01. The combined Demo checkpoint is committed and
pushed on `feature/demo-core` at `bcdcd3d`. This backend-only candidate was
prepared separately from that clean checkout; its branch, commit and PR are
pending explicit Git/GitHub approval. No integration branch or frontend branch
has been created for this split yet.

## Implemented in this candidate

The single-process FastAPI app exposes the Rooms/Game API and stores both
domains in `DATA_DIR/whos_on_repeat.sqlite3`. Migration 1 matches the ten-table
documented DDL. Startup initializes and seeds storage, aborts interrupted games
with partial rankings, and cleans expired rooms. HTTP routes, application
coordination, domain rules and persistence retain separate ownership.

Demo supports 3–10 player identities, room-specific HttpOnly credentials,
nicknames/characters, hidden seeded assignments, host settings, frozen rosters
and song plans, final submissions, artist partial credit, submitted Nobody
versus missing answers, readiness and timed phases, host audio leases, checked
reserves, void attempts, strict skip limits, and durable rankings/history.
The API retains the private host manifest and automatic check-in contracts
needed by the future frontend. Actual browser scheduling and sound playback
require a frontend and are not implemented in this candidate.

The runtime catalog has exactly four fictional personal-pool songs, four
original 30-second MP3s and one SVG cover. Metadata lives in
`catalog/demo_catalog.json`; bundled files live in `catalog/assets/`. The API
serves them at the unchanged `/static/demo/` URLs. Nullable artwork is retained
in songs and frozen snapshots; displaying a placeholder belongs to the future
frontend. No music account or network music API is used.

The four-song seed supports startup and lobby/API checks. It fails the unchanged
ten-songs-per-player start requirement with `insufficient_songs`; it cannot
supply a complete match. Larger metadata fixtures are generated only in
temporary test/load data. Startup refreshes shared catalog entries while keeping
existing room songs and frozen snapshots; use a new room or fresh `DATA_DIR`
when checking the current seed, because old rooms may reference retired assets.

There is no custom player UI or frontend test suite in this candidate. `/`
returns 404, `/docs` exposes FastAPI's API explorer, and `/openapi.json` exposes
the schema. These endpoints are developer tools, not the game's player screens.
The temporary UI remains preserved on the pushed Demo checkpoint.

## Current automated evidence

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
```

The isolated backend-only candidate passed **93 Python tests**, with **93%
combined Rooms/Game coverage** (Python 3.12.2). After independent review tightened
the encoded traversal assertion, all **six bundled-catalog tests** passed again.
The review found no blocking backend dependency or routing regression.

A separate CLI smoke run started `python -m backend` from outside the candidate
with temporary storage. Liveness, readiness, API docs and OpenAPI returned 200;
root and removed UI routes returned 404. All four clips and the cover returned
200, a 128-byte audio range returned 206, encoded traversal was rejected, and
room admission assigned four songs. The process was stopped after the check;
existing checkout data and its running server were left untouched.

Tests use real temporary SQLite databases and injected clocks. They cover
concurrent final submissions, exact deadlines, durable retries, setup and later
readiness recovery, replacement budgets and strict 30% boundaries, immutable
snapshots, void-score exclusion, ten-round completion with larger temporary
fixtures, restart recovery, retention, room cookie isolation and host authority.
Actual bundled-catalog tests exercise fresh FastAPI startup, three-player
admission, rejected Start, reseeding and invalid-input rollback. Resource tests
check migrations, API availability and actual media delivery outside the shell's
checkout directory without a frontend dependency.

## Preserved combined checkpoint

`feature/demo-core` retains the temporary browser UI and its 12 module behavior
checks. Its reported 93-test Python run and 93% Rooms/Game coverage preceded
this split; current candidate evidence above is separate. Its latest browser
checks covered host/guest admission, refresh identity restoration, three-player
rosters, four-song assignments and the insufficient-catalog notice. The full
match and capacity observations below are older runs and do not establish
playability of the current four-song catalog or this API-only candidate.

## Historical frontend evidence

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

## Historical capacity evidence and limits

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
  replacements for supported match lengths. Build the frontend on the integrated backend, using the draft only as a reference.
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
