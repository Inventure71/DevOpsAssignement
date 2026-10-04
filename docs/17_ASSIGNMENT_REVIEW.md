# Assignment 1 review - 2026-10-04

Source: the local `notes/assignment_instructions.md` supplied for this project.
The source is ignored by Git; this checklist records its requirements without
claiming that newer course announcements were checked. Its stated deadline is
2026-10-04 23:59. The professor approved the app idea with “go for it”, according
to the user; no approval date was supplied.

| Requirement | Evidence / remaining action |
|---|---|
| Single process; no deployed service split | `python -m backend`, one Uvicorn worker; in-process phase/import tasks |
| Two distinct SQLite-backed domains | Rooms owns admission/membership/listening; Game owns frozen games/attempts/answers/ranks |
| One documented SQLite path | `DATA_DIR/whos_on_repeat.sqlite3`; schema 6 / catalog component 3; no separate catalog path |
| One root dependency manifest | `requirements.txt`, six direct packages including local testing; no frontend manifest/build |
| Startup contract | 0.0.0.0, PORT env, automatic migration, no required .env, no bulk download at startup |
| No student-authored Docker/CI/IaC or managed services | No such files required or introduced; local verification is `tools/verify.sh` |
| >=70% unit core business logic coverage | Run the unit-only coverage command in README; 70% gate enforced by tools/verify.sh; integration measured separately |
| Exactly five ADRs, >=3 commit dates | ADR.md keeps its five historical entries/dates and explicit dated refinements; Git history contains multiple ADR changes; remote evidence still needs checking |
| Meaningful AI interaction log | Actual known interactions documented; assistant explanation drafts require author's own review; missing earlier sessions are marked, not invented |
| >=12 meaningful commits across >=6 days, <=40% one day, pushed | Local history has 15 commits across seven days, five on busiest day. Initial setup is generic and merge meaning is reviewer-dependent. Local counts do not prove remote push cadence. No new push was authorized |
| 4-5 page report | Local five-page draft at output/pdf/assignment-report.pdf, excluded from the code checkpoint; personal SDLC/AI statements marked for author review |
| Written comprehension check | Author must explain actual code cold; prompts below are study aids, not evidence of comprehension |

The assignment's 15-50 file guideline is soft. This implementation exceeds it:
multiplayer timing, providers, browser components and behavioral tests create
more modules. Demo media is installed separately and excluded from source control.
The module count is a cost of the chosen scope, not a hidden requirement exemption. No extra framework, message broker,
ORM, npm build, service deployment or CI was added. Further cosmetic abstractions
would make the submission harder to explain without improving either domain.

## Author review before submission

- Confirm the report's description of iterative/incremental development against
  what you actually did. It is inferred from the documented checkpoints, not a
  claim that you followed a formal process perfectly.
- Rewrite/check AI_USAGE.md explanation drafts in your own words using the actual
  function/variable names. Fill missing earlier interactions from real records.
- Review the five-page report, especially SDLC practice and AI disclosure.
- Verify remote commit/push evidence and submit the correct branch/report. Git
  actions require separate exact approval; no fabricated/backdated evidence.
- Complete the classroom comprehension check and physical device acceptance.

## Six code flows to explain without notes

1. **Join:** `RoomCommands.join` serializes admission; `RoomsService.check_admission`
   applies lobby/capacity/nickname policy, and the repository persists a room-scoped
   credential digest. Normal admission verifies/imports music before committing.
2. **Start/snapshot:** `Coordinator.start` validates host, lease and revision;
   `RoomsService.snapshot` exports values; `GameService.start` freezes roster,
   songs, settings and distinct candidates/reserves in SQLite.
3. **Timing:** `Coordinator.execute` captures acceptance time after acquiring the
   room turn and persists elapsed transitions before an invalid command;
   `GameService.advance` owns phase changes. A late guess cannot move the deadline.
4. **Scoring/privacy:** `GameService.answer` accepts one final signed selection;
   `score_answer` uses frozen identities, exact arithmetic and observed listeners.
   Nobody is a submitted empty list; missing is a zero-point absent answer. Views
   expose only the authenticated player's answer feedback.
5. **Catalog:** `SongSearch` searches FTS and scoped provider query caches;
   `CatalogSelections` verifies a bulk result once. `VerifiedLinks` saves both
   directions per scope/purpose/fingerprint. URL expiry does not erase identity.
6. **Audio/recovery:** application readiness includes guests; host controller owns
   lease/unlock/preload/scheduling. A session generation invalidates old asynchronous
   work; `RoomLocks` counts holders and waiters before removing idle locks. Explain
   why dropping a queued lock or trusting a late old lease would be incorrect.

## Current Demo packaging and verification

The sole default Demo is the pinned 100-song Drive pack: 80 personal recordings
and 20 Nobody songs. Public source contains its canonical metadata, source pin
and installer; media, archives, private acquisition tools and build artifacts
stay ignored. The launcher installs missing music before server startup, or
`tools/setup_demo_pack.py --archive` installs a previously downloaded ZIP. Later
launches and gameplay work offline without API credentials or ffmpeg.

The precommit cleanup removed the old synthetic/festival packs and obsolete local
room/game history while retaining public provider metadata, verified links and
caches. There is no alternate fallback catalog or separate catalog import module.
Read-only `--check` requires dependencies and the selected pack already installed.

Current automated totals and coverage belong in
[implementation status](08_IMPLEMENTATION_STATUS.md) after final verification.
They do not establish physical speaker audibility, phone compatibility or remote
Git submission evidence. Earlier browser and pack checkpoints remain historical;
the report draft needs author review against this current architecture and setup.
