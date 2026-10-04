# Testing strategy

The assignment asks for unit coverage of the two domains' core business logic, separately from framework glue. Its minimum is 70%; this project enforces 90% in Rooms and Game. The teacher's testing exercises guide the suite: explicit happy, edge and error cases; reusable fixtures with teardown; deterministic inputs; offline external collaborators; and spec-constrained mocks. Coverage is supporting evidence, alongside meaningful assertions.

## Ownership

| Layer | Responsibility | Representative tests |
| --- | --- | --- |
| Unit | Membership, authority, exact deadlines, scoring, selection, readiness and preparation policy | `test_rooms_rules.py`, `test_game_rules.py`, `test_scoring.py`, `test_selection.py`, `test_round_preparation.py` |
| SQLite integration | Frozen snapshots, ownership, transaction rollback, concurrency, schema migration and restart persistence | `test_game.py`, `test_round_preparation.py`, `test_blob_colors.py`, `test_song_migration.py` |
| HTTP integration | Authentication, private views, selection tokens, command validation, startup capabilities and complete games | `test_api.py`, `test_upcoming_api.py`, `test_demo_playthrough.py`, `test_music_admission.py`, `test_startup_contract.py` |
| Frontend | Controller decisions, stale asynchronous work, audio lifecycle, preload reuse, readiness and reconnect recovery | `client.test.mjs`, `recovery.test.mjs`, `round-audio.test.mjs`, `upcoming-readiness.test.mjs` |

Unit repository doubles implement storage operations, not game policy. `tests/support/game_policy.py` constrains its double to the real repository interface. Integration tests retain actual SQLite transactions and HTTP requests. Explicit clocks replace sleeps; fixtures isolate all data and media. Provider tests use offline transport collaborators.

## Consolidation on 2026-10-04

| Repetition removed | Protection retained |
| --- | --- |
| SQLite tests repeating preparation rules | Unit cases for freshness boundaries, disconnected guests, expired/replaced host leases, acknowledgement renewal, stale IDs/generations and replacement candidates; SQLite promotion, rollback and cascade tests remain |
| Repeated complete Demo/Normal matches | One maximum-length Demo HTTP match with independent database reopening; two Normal matches covering standard admission and shared-account playtest/rematch; supported round counts still have planner unit cases |
| Eight identical color migration runs | One populated database checks every legacy color in live and frozen rosters, preserves other records and repeats migration safely |
| Repeated provider/cache checks | Actual provider-to-resolver paths, caller identity preservation, bounded imports, negative-cache expiry and retry |
| Duplicate frontend waveform/preload/fixture assertions | Behavioral boundary tables, controller isolation, audio-context failure recovery, decoded-buffer reuse and stale-response protection |

Delete a test only when its unique behavior has a surviving owner. Testing the same rule through another layer is justified when it adds a transport, storage or integration failure mode. Named parameter cases remain separate reported executions because each represents a distinct input boundary. A smaller case count is not itself a quality target.

## Verification

Run `bash tools/verify.sh` from the repository root. It runs unit tests, checks core coverage, checks each domain separately, checks preparation separately, then runs SQLite/HTTP integration and frontend tests. The preparation gate prevents stronger Game coverage from hiding a regression in this small module. No coverage exclusions were added for this cleanup.

The [README](../README.md#verify) contains the unit coverage command. The measured unit line coverage is **94.05% combined**: Rooms **92.13%**, Game **94.79%**. Individual modules: Rooms service **92.13%**, Game service **93.86%**, preparation **96%**, selection **94.52%**, scoring **100%**.

Current verification: **301 unit**, **218 SQLite/HTTP integration** and **178 frontend** cases pass. The original checkout had 541 Python and 174 frontend cases; the current totals include concurrently added startup-contract cases. Core unit line coverage increased from **88.11%** to **94.05%**, with preparation increasing from **62%** to **96%**. Cases were removed, moved or added according to their behavior, rather than to meet a case-count target.

A separate full-backend run passes all **519 Python** cases with **94.39% line coverage** and **85.27% branch coverage**. Node reports **80.07% line coverage across loaded frontend modules**, including presentation components; all loaded `frontend/game` modules and upcoming readiness have 100% line coverage. The frontend aggregate is not a whole-application coverage claim: Node only measures modules loaded by these tests.

To measure the entire backend separately, including adapters and HTTP:

```bash
.venv/bin/python -m pytest -q --cov=backend --cov-branch --cov-report=term-missing
```

For frontend measurements:

```bash
node --test --experimental-test-coverage tests/frontend/*.test.mjs
```

The 90% gate measures core unit line coverage. Whole-backend branch coverage and frontend coverage are separate metrics; those broader scopes are not implied by the core percentage. Automated tests also do not establish physical audio quality, phone compatibility or live provider access, which retain manual acceptance checks.
