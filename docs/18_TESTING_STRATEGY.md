# Testing strategy

The assignment requires 70% unit coverage of Rooms and Game core logic; this project gates each domain at 90%. Tests follow the teacher's exercises: happy, edge and error cases, isolated fixtures, deterministic inputs and controlled external collaborators.

## Ownership

| Layer | Tests |
|---|---|
| Unit | Membership, authority, deadlines, scoring, selection, preparation and song-title equivalence |
| SQLite integration | Frozen snapshots, ownership, rollback, concurrency, migrations and restart persistence |
| HTTP integration | Authentication, private views, signed selections, startup, admission lifecycle and complete games |
| Frontend | Controller decisions, stale requests, audio lifecycle, preload reuse, readiness and reconnect |

Repository doubles implement storage operations and follow the real interface; domain rules stay in production services. Integration tests use real SQLite and HTTP. Clocks replace sleeps, fixtures isolate data/media, and provider collaborators work offline.

## Keeping tests useful

Give each rule a primary test owner. Repeat it through another layer when that adds a storage, transport or lifecycle failure mode. Parameterized cases should represent distinct boundaries.

The Oct 4 cleanup consolidated repeated matches, migration runs and provider/frontend assertions. It retained rollback, restart and end-to-end coverage, and added missing preparation and scoring boundaries.

Current regressions cover:

- Freshness, host leases, readiness generations, disconnected players and preparation promotion.
- Source evidence through the shared importer and real Rooms persistence, including qualified account identities and shared ownership.
- Cancellation versus commit, session delivery, admission-specific acknowledgement and explicit Leave through HTTP.
- Frontend acceptance, lost responses, cancellation, invitation-specific recovery, stale failures after page restoration and preload reuse from reveal.
- Recognized release editions in guesses, with strict recording identity preserved for catalog links and playback.

## Verification

```bash
bash tools/verify.sh
```

This runs unit tests with core coverage gates, checks preparation separately, then runs SQLite/HTTP and frontend tests. [README](../README.md#verify) gives the measured modules and result; [implementation status](08_IMPLEMENTATION_STATUS.md) records the latest run.

Broader measurements can be run separately:

```bash
.venv/bin/python -m pytest -q --cov=backend --cov-branch --cov-report=term-missing
node --test --experimental-test-coverage tests/frontend/*.test.mjs
```

Core unit line coverage, whole-backend branch coverage and frontend coverage measure different scopes. Real accounts, phone behavior and audible playback use the [device checklist](16_DEVICE_PLAYTEST.md).
