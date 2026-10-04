# Assignment 1 review - 2026-10-04

Source: the local `notes/assignment_instructions.md` supplied for this project. The source is ignored by Git; this checklist records its requirements without claiming that newer course announcements were checked. Its stated deadline is 2026-10-04 23:59. The professor approved the app idea with “go for it”, according to the user; no approval date was supplied.

| Requirement | Evidence / remaining action |
|---|---|
| Single process; no deployed service split | `python -m backend`, one Uvicorn worker; in-process phase/import tasks |
| Two distinct SQLite-backed domains | Rooms owns admission/membership/listening; Game owns frozen games/attempts/answers/ranks |
| One documented SQLite path | `DATA_DIR/whos_on_repeat.sqlite3`; schema 6 / catalog component 3; no separate catalog path |
| One root dependency manifest | `requirements.txt`, six direct packages including local testing; no frontend manifest/build |
| Startup contract | Verified clean public source starts with `python -m backend` in 0.459 s: `/`, `/health/live` and `/health/ready` return HTTP 200; SQLite schema 6 initializes automatically. No `.env`, media, private tools, prior data or download is needed for server readiness. Without music, Demo is explicitly disabled; playable Demo requires the pinned pack. See the startup evidence below. |
| No student-authored Docker/CI/IaC or managed services | No such files required or introduced; local verification is `tools/verify.sh` |
| >=70% unit core business logic coverage | Final isolated public-source measurement: 94.05% over five core modules, including round preparation; Rooms 92.13%, Game 94.79%. The README gives command and result. `tools/verify.sh` enforces 90% overall and separately for each domain, above the brief's 70% minimum. Public suite: 286 unit + 218 integration = 504 Python tests, plus 178 frontend tests, all passing. |
| Exactly five ADRs, >=3 commit dates | Five entries first appeared in `7fd5e42` (Sep 27), `e5b091b` (Sep 29), `acc5000` (Sep 30) and `a55de5a` (Oct 1). Their original versions remain in the remotely reachable history at `528952a`. |
| Meaningful AI interaction log | September 28–29 requirements/rules/PoC interactions were recovered from actual transcripts with source references. This targeted recovery is not an exhaustive-history claim; explanation drafts still require the author's review. |
| >=12 meaningful commits across >=6 days, <=40% one day, pushed | At `528952a`: 12 substantive non-merge commits on eight local dates; busiest date has 3/12 (25%). Live GitHub ref matches the local head, and available remote evidence identifies six push dates. Local date distribution does not prove distribution by remote publication date; see the evidence section below. Final local edits are not included in that published head. |
| 4-5 page report | [Regenerated five-page PDF](../output/pdf/assignment-report.pdf) now reflects schema 6, `game_round_preparations`, the sole 100-song pack and final startup/test evidence. All five rendered pages were visually inspected; diagrams include all 17 schema entities and their columns. The author's review of the SDLC account and AI disclosure remains required. |
| Written comprehension check | Author must explain actual code cold; prompts below are study aids, not evidence of comprehension |

The assignment's 15-50 file guideline is soft. This implementation exceeds it: multiplayer timing, providers, browser components and behavioral tests create more modules. Demo media is installed separately and excluded from source control. The module count is a cost of the chosen scope, not a hidden requirement exemption. No extra framework, message broker, ORM, npm build, service deployment or CI was added. Further cosmetic abstractions would make the submission harder to explain without improving either domain.

## Author review before submission

- Confirm the report's description of iterative/incremental development against what you actually did. It is inferred from the documented checkpoints, not a claim that you followed a formal process perfectly.
- Check AI_USAGE.md explanation drafts in your own words using the actual function/variable names. September 28–29 gaps have been recovered; add any other known omissions from real records rather than inventing interactions.
- Review the five-page report, especially SDLC practice and AI disclosure.
- Review the remaining commit-by-push distribution evidence and submit the correct branch/report. The remote contains `528952a`, not later local edits; publishing those requires separate exact Git approval. No fabricated/backdated evidence.
- Complete the classroom comprehension check and physical device acceptance.

## Six code flows to explain without notes

1. **Join:** `RoomCommands.join` serializes admission; `RoomsService.check_admission` applies lobby/capacity/nickname policy, and the repository persists a room-scoped credential digest. Normal admission verifies/imports music before committing.
2. **Start/snapshot:** `Coordinator.start` validates host, lease and revision; `RoomsService.snapshot` exports values; `GameService.start` freezes roster, songs, settings and distinct candidates/reserves in SQLite.
3. **Timing:** `Coordinator.execute` captures acceptance time after acquiring the room turn and persists elapsed transitions before an invalid command; `GameService.advance` owns phase changes. A late guess cannot move the deadline.
4. **Scoring/privacy:** `GameService.answer` accepts one final signed selection; `score_answer` uses frozen identities, exact arithmetic and observed listeners. Nobody is a submitted empty list; missing is a zero-point absent answer. Views expose only the authenticated player's answer feedback.
5. **Catalog:** `SongSearch` searches FTS and scoped provider query caches; `CatalogSelections` verifies a bulk result once. `VerifiedLinks` saves both directions per scope/purpose/fingerprint. URL expiry does not erase identity.
6. **Audio/recovery:** application readiness includes guests; host controller owns lease/unlock/preload/scheduling. A session generation invalidates old asynchronous work; `RoomLocks` counts holders and waiters before removing idle locks. Explain why dropping a queued lock or trusting a late old lease would be incorrect.

## Current Demo packaging and verification

The sole default Demo is the pinned 100-song Drive pack: 80 personal recordings and 20 Nobody songs. Public source contains its canonical metadata, source pin and installer; media, archives, private acquisition tools and build artifacts stay ignored. At the published `528952a` checkpoint, the launcher installs missing music before server startup, or `tools/setup_demo_pack.py --archive` installs a previously downloaded ZIP. Later launches and gameplay work offline without API credentials or ffmpeg.

The cleanup published in `528952a` removed the old synthetic/festival packs and obsolete local room/game history while retaining public provider metadata, verified links and caches. There is no alternate fallback catalog or separate catalog import module. Read-only `--check` requires dependencies and the selected pack already installed.

Final isolated public-source verification passed 286 unit and 218 integration tests (504 Python total), plus 178 frontend tests, with zero failures. Core unit coverage is 94.05% (639 statements, 38 missed) across Rooms service, Game service, scoring, selection and round preparation. The verified source/test fingerprints match the live implementation; lower totals than earlier checkpoints reflect the parallel test cleanup, not failing checks. Commands/results are in README and dated evidence is in [implementation status](08_IMPLEMENTATION_STATUS.md). They do not establish physical speaker audibility, phone compatibility or remote Git submission evidence. Earlier browser and pack checkpoints remain historical. Final startup evidence follows; the regenerated report must still receive the author's review. Comprehension cannot be certified by AI.

## Fresh-source startup evidence — 2026-10-04

A clean public-source copy with the existing Python dependencies supplied and
without `.env`, private tools, media or previous data reached readiness in
**0.459 seconds** under `python -m backend`. The root page and both health
endpoints returned HTTP 200; the single SQLite database initialized to schema 6.
Startup neither created `catalog/local` nor downloaded music.

Server readiness means that HTTP and persistence work. It does not mean a
key-free Demo can play without its audio: `/api/config` disables Demo when the
pack is absent, and admission/preview requests fail clearly before creating
room/player data. Configured Normal admission is independent of Demo media.
The assessment launcher installs the sole pinned 100-song pack automatically
before launching; installation plus restart enables local Demo playback.
Existing malformed packs still fail before database initialization.

Six passing [startup integration cases](../tests/integration/test_startup_contract.py)
cover both configured game modes, missing-pack admission, configured Normal, a restored
Demo with missing music, corrupt-pack failure and installation/restart recovery.
Those use isolated generated transport fixtures. A separate fresh public-source
checkout verified the installed pack inventory and passed complete ten- and
fifteen-round HTTP/SQLite games with separate cookie jars and actual audio files.
Demo launcher `--check` also passed when invoked outside the checkout and created
no application data. Verified installed media was reused; this check did not make
a new Drive download. Physical speakers and phones remain manual acceptance checks.

## Read-only version-control evidence — 2026-10-04

The current head contains 16 reachable commits. Excluding generic `initial setup`
and three merge commits leaves 12 substantive non-merge commits. Their local
calendar distribution is Sep 27: 1, Sep 28: 1, Sep 29: 2, Sep 30: 1, Oct 1: 2,
Oct 2: 1, Oct 3: 3 and Oct 4: 1. The busiest local date is therefore 25%.

Read-only GitHub API checks confirm
`refs/heads/test/optimized-game = 528952a0b37faf3537df2f17908d06e145199ad8`.
The available [repository events](https://api.github.com/repos/Inventure71/DevOpsAssignement/events)
include PushEvents dated Sep 27, Sep 28, Sep 29, Oct 1 and Oct 2 (UTC).
The [repository metadata](https://api.github.com/repos/Inventure71/DevOpsAssignement)
reports `pushed_at = 2026-10-04T18:22:37Z`, matching the local remote-ref reflog's
`update by push` at 20:22:37 +02:00. Together these identify six remote push dates;
none cross a UTC/Madrid calendar boundary.

These are real publication observations, rather than author/committer timestamps.
The exposed events are not a complete per-commit first-publication audit: in
particular, the Sep 30 and Oct 3 local dates must not be presented as verified
push dates. The <=40% rule should be assessed against the professor's remote
history, not certified from the 25% local statistic. No fetching, staging,
committing, pushing or other Git/GitHub mutation was performed for this check.
