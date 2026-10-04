# Assignment 1 checklist

Based on the supplied `notes/assignment_instructions.md`. Deadline: Oct 4, 2026, 23:59.

| Requirement | Evidence |
|---|---|
| Single process and two SQLite-backed domains | `python -m backend`; Rooms owns membership/listening, Game owns frozen games/answers/rankings |
| One database and root dependency manifest | `DATA_DIR/whos_on_repeat.sqlite3`; `requirements.txt` |
| Startup contract | Binds `0.0.0.0`, reads `PORT`/`DATA_DIR`, initializes schema automatically and exposes health endpoints; [README](../README.md#run) |
| 70% core unit coverage | Project gate is 90% per domain; command/result in [README](../README.md#verify) |
| Exactly five ADRs introduced on three or more dates | [ADR.md](../ADR.md); introductions on Sep 27, Sep 29, Sep 30 and Oct 1 |
| Meaningful AI log with implementation explanations | [AI_USAGE.md](../AI_USAGE.md) |
| Twelve meaningful commits over six days, at most 40% on one day, published | Local history and dated publication observations below; verify the final submitted ref |
| Four- or five-page report with diagrams and AI disclosure | [Report PDF](../output/pdf/assignment-report.pdf) |
| Written code comprehension | Author review and classroom check |

## Before submission

- [ ] Review the report's SDLC account against your own experience.
- [ ] Review AI log explanations in your own words and add known missing interactions.
- [ ] Check the final report and submitted branch, including publication cadence.
- [ ] Complete physical-device checks in [the playtest checklist](16_DEVICE_PLAYTEST.md).
- [ ] Prepare for the written comprehension check.

## Code flows to explain

1. Join: `MusicSource` → `MusicImporter` → `MusicAdmissionHandler` → Rooms; cancellation, session acceptance and admission-specific acknowledgement.
2. Start: `Coordinator.start` → `RoomsService.snapshot` → `GameService.start`; frozen roster, settings and songs.
3. Timing: room lock → acceptance timestamp → `GameService.advance`; deadlines and stale commands.
4. Scoring: signed selection → `GameService.answer` → `score_answer`; Nobody versus missing, release editions and private projections.
5. Catalog: `SongSearch`, `CatalogSelections` and `VerifiedLinks`; scoped caching, identity and preview availability.
6. Audio: host lease, gesture activation, preparation during results and session generations that invalidate old work.

[Architecture](05_ARCHITECTURE.md#pattern-rationale-and-course-connection) explains the pattern choices; [API/runtime](07_API_AND_RUNTIME.md) follows the command flow.

## Dated publication evidence — Oct 4

At `1a8c1ce`, local history contained 13 substantive non-merge commits across eight dates; the busiest date held 3/13 (23.08%). The earlier published `528952a` checkpoint contained 12, with a busiest date of 3/12 (25%).

The recorded remote observation matched `test/optimized-game` to `528952a0b37faf3537df2f17908d06e145199ad8`. GitHub events showed pushes on Sep 27, Sep 28, Sep 29, Oct 1 and Oct 2; repository `pushed_at` was `2026-10-04T18:22:37Z`. These establish six push dates. Per-commit first-publication distribution still needs verification for the final submission.

Runtime and test evidence is kept in [implementation status](08_IMPLEMENTATION_STATUS.md).
