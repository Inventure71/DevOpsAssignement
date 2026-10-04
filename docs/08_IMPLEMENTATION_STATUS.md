# Submission readiness checkpoint - 2026-10-04

This section describes the current local source after the published `528952a`
checkpoint. The sections below preserve earlier evidence and are historical.

## Startup and assessed gameplay

A clean public-source copy with Python dependencies supplied, but no `.env`,
private tooling, media or application data, reached `/health/ready` in **0.459 s**
under `python -m backend`. SQLite initialized at the documented path; no media
was created or downloaded. An absent pack now disables Demo consistently through
capabilities, create/join/restore and preview/media routes. Configured Normal
admission works independently. Existing corrupt packs are rejected before data
initialization. Installing media requires a server restart to enable Demo.

A copied, independently verified pinned pack reached ready with Demo enabled in
**0.445 s**. Full **10- and 15-round HTTP/SQLite games** passed with separate
cookie jars and the actual audio files. Installed-pack launcher `--check` passed
from outside the checkout and created no application data. This reused verified
installed media; no new Drive download was performed in this run. The assessment
launcher still installs the sole 100-song pack before starting playable Demo;
that installation needs internet or the verified archive. Server readiness alone
does not establish playable music or physical speaker acceptance.

## Current automated verification

The frozen public-source snapshot passed **286 unit + 218 integration = 504
Python tests** and **178 frontend tests**, with no failures. Unit-only coverage
across Rooms service, Game service, scoring, selection and round preparation is
**94.05% (601/639 statements)**: **Rooms 92.13%**, **Game 94.79%**. The local
verification script enforces 90% both overall and per domain, above the brief's
70% minimum. Refactored tests move duplicate policy scenarios into meaningful
unit tests; test counts are not directly comparable to earlier checkpoints.
Source fingerprints were checked against the live source after verification.
Private acquisition-tool tests are excluded. Dependencies were supplied from the
existing Python environment; this was not a fresh package installation or a
Windows hardware test.

## Report and remaining author checks

The actual [five-page report](../output/pdf/assignment-report.pdf) was regenerated
with schema 6, catalog component 3, `game_round_preparations`, all actual schema
columns, the sole 100-song pack, dated SMART outcomes, business tradeoffs and
Claude/Codex disclosure. All five rendered pages were inspected. The PDF and its
reviewable source remain ignored artifacts for separate report submission.

README now contains the exact coverage command and measured result; planning,
ADRs and the assignment checklist distinguish current scope from dated history.
The author must still review the personal process account and AI explanations,
complete the written check and perform remaining physical device acceptance.
Remote evidence establishes at least six push dates, but complete per-commit
remote date distribution remains unverified. This task performed no Git/GitHub
mutation; local changes are not represented by the published checkpoint.

## Historical checkpoints

## Historical: Single-pack cleanup checkpoint - 2026-10-04

Demo now requires the pinned 100-song Drive pack: 80 personal tracks and 20 Nobody tracks, with 36 assigned songs per player. The canonical public metadata matches the installed pack. The only runtime mount is `/static/demo/local/`; retired synthetic/festival recordings, generators and pack-selection fallback paths have been removed. The UI lab requests its sample from `/api/demo/preview`.

Both launch profiles install missing default music before starting the server. A failed download or invalid pack stops launch with setup instructions. `--check` remains read-only and requires an installed valid pack; `--demo-pack` selects an explicit prepared directory. `--bundled-demo` no longer exists. Teacher setup needs internet once or the pinned ZIP supplied with `--archive`; gameplay then uses local music without API keys, a Google account or ffmpeg.

At the user's request, local pre-release room/game history was cleared and old media moved outside the checkout. Verified provider links and public catalog cache remain intact. Separate catalog imports and pre-release catalog upgrade paths are retired; ordinary current-game recovery and versioned application schema creation remain. Automated tests generate explicit temporary transport audio, so source tests require neither private acquisition tools nor Drive.

An isolated copy of public source, without private acquisition tools, local media or application data, passed **267 unit + 259 integration = 526 Python tests** and **174 frontend tests**. Unit core line coverage is **90.32%** against the 70% requirement. Its dependencies were supplied from the existing `.venv`; this was not a new package download or Windows hardware check. Runtime/tool/test Ruff lint, formatting and whitespace checks passed.

The same source copy installed the actual pinned ZIP with `--archive`, verified all 104 inventory entries offline and passed Demo launcher preflight with usable loopback/LAN URLs. Preflight created no application data. Real-pack ten- and fifteen-round HTTP/SQLite games passed with separate client cookie jars and isolated game data. This verifies transport and game flow, not physical speakers. The checkout has exactly 100 audio files, all inside the ignored managed pack; no existing audio or ignored artifact is tracked or eligible for source addition. No staging, commit, branch or remote mutation is included in this cleanup.

The following sections are historical checkpoint evidence. Their earlier packs, compatibility paths and test counts describe those dates, not current behavior.

## Historical: Drive installer checkpoint - 2026-10-04

The user's uploaded 98.02 MiB ZIP is anonymously downloadable. The public source pins the Drive file ID, exact byte count, ZIP SHA-256 and manifest SHA-256 in `catalog/demo_pack_source.json`. The portable launcher installs it once before starting the server when no playable local pack exists; `--bundled-demo` skips Drive and `--check` stays read-only. A failed optional download prints a note and falls back to bundled music. The standalone `tools/setup_demo_pack.py` command also supports an already downloaded ZIP and a full offline integrity check.

Download, shared catalog validation and immutable installation have separate modules. Bounded transfers, allowed redirects, unsafe ZIP paths/links, inventory hashes, partial files, corrupt installs and concurrent locks are checked. Install publishes an entirely verified version directory atomically, preserving the existing author pack and older media. Malformed HTTP responses use the same recoverable fallback as other transport failures. No provider credentials, Google account or media encoder is needed by the installer.

Live validation downloaded the actual Drive ZIP anonymously into a temporary project, verified all 104 entries and ran ten- and fifteen-round HTTP/SQLite matches with its original audio. Offline reruns made no download requests. A clean public source copy, with dependencies supplied and private acquisition scripts/keys/music absent, passed **297 unit + 257 integration = 554 Python tests**, **153 frontend tests**, and **90.32% core unit line coverage**. These checks do not establish Windows hardware or physical speaker acceptance. Existing application databases, server processes, Drive permissions and Git state were not mutated. Changes remain unstaged on `test/optimized-game`.

Earlier checkpoint evidence follows.

## Historical: Private acquisition and upload package - 2026-10-04

The Apple acquisition script, media helper and fifteen dedicated unit tests are Git-ignored at the user's request. The public application and tests do not import these private tools. Verification from a clean source copy with dependencies supplied and private tools absent passed **262 unit + 220 integration = 482 Python tests**, **127 frontend tests**, with **91% unit core coverage**. The local author's 497-test Python count includes the fifteen private preparation tests.

`catalog/local/drive-upload/whos-on-repeat-demo-100.zip` is an ignored, self-contained package with exactly 100 previews and the catalog, provenance, credits and checksum manifest. It excludes the old clips, private credentials, acquisition code, setup receipts and history. Every archive entry was checked against its SHA-256 hash. At this earlier checkpoint, the Drive installer was pending the uploaded file link. No upload or Git mutation occurred; the completed installer is described above.

Earlier preparation evidence follows.

## Historical: Local Apple-preview checkpoint - 2026-10-04

Optional `tools/setup_apple_demo.py` resolves the explicit 100-song request list, prepares original previews under ignored `catalog/local`, and publishes only a complete pack. Eighty songs populate simulated libraries (36 per player); twenty separate songs supply Nobody rounds. Per-song receipts permit resumed/offline reuse. SHA-256 filenames preserve older frozen-game URLs, and previous metadata and attribution are retained. Startup never invokes the preparation tool. The standard Apple terms restrict saving/rehosting; this checkpoint makes no claim of an educational exemption or redistribution permission. No cloud upload or Git mutation occurred.

All 100 actual previews passed full ffmpeg decode, duration and checksum checks; lengths are 29.977-30.023 seconds and current media totals 98.41 MiB. Ten- and fifteen-round HTTP/SQLite games passed using the downloaded pack and temporary application data. The current suite passes **277 unit + 220 integration = 497 Python tests**, **127 frontend tests**, with **91% unit core coverage**. Native browser/device speaker acceptance for this new pack was not performed; the main server was left stopped. Existing application data was untouched.

Earlier launch and refinement evidence follows.

## Historical: Current refinement checkpoint - 2026-10-04

Latest launch refinement: `run_demo.sh` is the teacher's key-free setup/run path; `run_real_game.sh` additionally enables configured Spotify, while retaining Demo. Both use the portable Python setup entry, verify requirements/assets and print usable browser URLs. Demo ignores private provider and tunnel configuration, uses local catalog searches even for misses, and defaults to `data/demo`. `GET /api/config` controls available options; server commands enforce the same Spotify restriction independently of the UI. Insecure real-game entries redirect to the configured HTTPS origin and preserve invitations.

Current verification: **277 unit + 218 integration = 495 Python tests**, **127 frontend tests**, **91% unit-only core coverage**. All 109 Python source/test/tool files pass formatting checks. A fresh copied project without `.env`, `.venv` or downloaded clips installed the root manifest and ran bundled Demo; 11 additional checks under that fresh environment covered complete ten-/fifteen-round matches, invitations and session boundaries. Native browser checks verified disabled Spotify under Demo and both enabled choices under the real launch. An independent LAN cookie jar reached and joined the printed invite. Physical teacher hardware, Windows execution and device speaker acceptance remain separate manual checks. The existing server/game was preserved; all new runtime checks used other ports and temporary data. Changes remain uncommitted on `test/optimized-game`.

Unused-code cleanup removed Spotify public search/app-token credentials, its implicit decoy fallback, the Apple resolve wrapper, unused importer counters and media identity field, obsolete frontend selectors/model fields and inspection hooks. Five tests for the retired Spotify search feature were removed; personal PKCE import, failure details, verified links, signed-selection expiry, standings and the room-revision snapshot remain intact. Seven unreferenced local clips were pruned after checking catalog JSON and all local databases, with recovery copies outside the repository. Both the prepared 21-clip pack and bundled 120-clip pack validate. Current counts include the Apple Demo setup tests already in the workspace. Backend/tool/unit lint, JavaScript/shell syntax and whitespace checks pass; this cleanup did not start or stop servers or perform Git mutations.

Earlier refinement evidence follows:

The entries below preserve earlier evidence and limitations at those dates. Current implementation uses one process, one root manifest and one SQLite file. The complete offline Demo has 120 original bundled recordings (96 personal, 24 independent Nobody decoys); default 10-round and maximum 15-round games pass real HTTP/SQLite tests with three player sessions and signed local search. Each player gets 36 hidden songs. All 120 MP3s were decoded with ffmpeg and last 30.000-30.096 seconds, totaling 10,960,608 audio bytes.

Named application operations own HTTP workflows. GameService owns transitions and its repository owns score writes. Per-room locks release idle entries while retaining queued callers. Catalog transport is injected, and public search accepts authorized public Demo metadata without direct Rooms SQL. Browser readiness is independent of host playback. Session cancellation/generation fences stop old leases, decoding and errors from reaching a replacement room.

Unit-only core policy verification: 183 tests passed, 91% line coverage across Rooms service (93%), Game service (88%), scoring (96%) and planning (95%). Clean-environment full Python suite: **387 passed in 55.64 s**, **94% backend line coverage**. The latest frontend suite contains **115 passing tests**. Browser: three independent cookie origins joined the real bundled Demo and completed two ten-round games. The host decoded/reported all 40 planned clips/reserves; the second run used the latest frontend and advanced inter-round server time, then submitted signed local-search guesses through the actual UI. Nobody rounds awarded listener points and all three sessions showed identical final ranks/scores. This is software/browser behavior, not phone audibility. Native snapshot automation failed, so DOM/state inspection and focused native interactions were used; no rendered gameplay screenshot claim is made.

All 96 Python files pass the Ruff format check; formatting changed no ASTs. Backend/tool undefined-name and unused-import checks pass. New migration tests reject unknown component versions and roll back invalid rows rather than silently marking a lossy import complete. Six direct dependencies installed successfully. The standard local verification command ran unit, integration and Node checks. The five-page PDF report was rendered and inspected, with no clipping or overlap. Existing private application data was inspected read-only, not migrated or reconciled during verification. All browser/testing storage was temporary. A fresh temporary Python environment installed the single requirements.txt successfully. No source changes were committed or pushed in this refinement.

The professor approved the app idea with “go for it”, according to the user. No approval date was supplied. Personal SDLC explanation and the author's AI log explanations require review; physical phone audio remains pending.

---

## Historical: 08 — Implementation Status

Updated 2026-10-02. Backend [PR #1](https://github.com/Inventure71/DevOpsAssignement/pull/1) is merged into `integration`. The redesigned UI checkpoint is committed on `feature/frontend` at `a05e19e`; this checkpoint adds the Spotify/Apple provider integration. The original combined Demo checkpoint remains preserved on `feature/demo-core` (`bcdcd3d`).

## Current implementation

The FastAPI/SQLite Rooms and Game domains retain the integrated backend’s identity, fixed-roster, phase, scoring, void-attempt, recovery and history behavior. A native ES module frontend is served at `/`; browser assets are at `/ui/` and catalog media at `/static/demo/`. No frontend bundler or npm dependencies are needed.

The new UI implements create/join, lobby settings and character selection, setup/check-in/countdown, listening and submitted rounds, direct player-icon selection, reveal with artwork fallback, leaderboard and room-history navigation. One deformable blob rig has eight selectable colors, friendly open eyes and listening/submitted/celebrating/sad moods. It retains its SVG nodes across updates. Pure contour clips and damped face/headphone joints share one visible 30 fps loop; offscreen and small thumbnail instances do not animate. Mounted screens and keyed player cards preserve focus and drafts. Reduced motion and document visibility govern continuous motion. `/ui-lab` uses isolated fixtures for visual/component checks; it is not a playable game.

Song-name typeahead searches shared Demo fixtures and the configured Apple developer catalog, with public iTunes metadata fallback for no-credentials Demo, not four round options. Server-signed room selections freeze title, artist, structured identity and optional artwork into answers. Provider calls occur outside room command locks; submission performs no provider lookup. Search is bounded by cache, timeout, single-flight calls and a process-wide request budget. Apple developer searches request structured artist relationships. Preview matching preserves Spotify credits and adds verified Apple aliases; missing featured credits remain unavailable. Search stays independent of personal authorization and playback import.

Migration 3 translates live/frozen character IDs to color IDs without changing credentials, membership, guesses or scores. Revealed answers now include `song_match`, sharing the frozen-song classifier with scoring. Song verdicts do not depend on total points; artist partial credit and unanswered guesses have separate feedback. The field stays hidden before reveal.

Migration 2 replaces choice-index answers with nullable selected-song JSON and converts historical answers without changing stored scores. Host preload reports can include normalized waveform levels measured from decoded audio; public round state exposes levels without its private playback URL.

The runtime catalog still contains exactly **four fictional personal songs**, four original 30-second MP3s and one SVG cover. It supports admission/lobby/media checks and correctly rejects Start with `insufficient_songs`. A complete match requires at least ten songs per player plus sufficient distinct candidates and reserves. Larger test metadata remains isolated. Real-song Demo population remains pending. Normal Spotify import is now implemented; real five-account acceptance remains pending rather than inferred from fixture tests.

Normal admission verifies each player's own Spotify account through cookie-bound PKCE, imports at most 60 balanced top/recent candidates, resolves Apple previews and requires at least ten playable personal songs. Host import obtains independent Apple chart candidates. The host counts toward the five-player/app-account limit. Receipt, queue and worker bounds keep provider work outside transactions; atomic admission rechecks room state, nickname, capacity and account uniqueness.

Migration 4 adds room-scoped account digests and explicit song pool kinds. Unavailable observed songs preserve ownership when another import later supplies playable media; their absence from a snapshot does not fabricate decoys. Frozen recording keys and verified artist aliases support Spotify-import/Apple-search scoring. Incompatible versions that share a mislabeled ISRC stay separate, and ISRC equality alone never awards full credit. No OAuth access/refresh token enters SQLite, public state or answer snapshots. The browser has explicit Spotify/Demo selection, import progress, finite connection retry and verification-error recovery. See [the checkpoint](13_SPOTIFY_IMPLEMENTATION.md).

The results contract is now owner-only: `reveal.my_answer` contains the requesting player's answer; the API never includes other players' song/listener guesses, including for the host. All answer records remain in SQLite for internal diagnosis. Correct song/listener facts, submission status and score/rank totals remain public. The shared guesses table and its unused styles were removed.

Frontend `.mjs` modules now separate application state/commands/runtime, transport, audio, pure display logic, screen lifecycle, header controls and isolated lab fixtures. Room SQL lives in its repository; room services retain rules. Runtime generations stop old in-flight poll/heartbeat work from restarting duplicate loops or applying stale state after stop/start. See [cleanup record](11_CODE_CLEANUP.md).

## Current verification

The provider checkpoint passes **228 Python tests**, **94% Rooms/Game coverage**, and **76 frontend Node tests**. All 40 frontend modules pass syntax checks. Five separate HTTP cookie sessions complete games of 5, 10 and 15 rounds through OAuth receipts, imported shared ownership, host preload reports, automatic readiness/countdowns, signed catalog answers, private reveals, rankings, history and rematch. Provider boundaries are faked; HTTP, SQLite, signing and game services are real. Additional tests prove concurrent five-player capacity, cancellation, expiry rollback, unavailable-song ownership, conflicting ISRC versions, migration preservation and identity restoration through a fresh application startup. The frontend admission revision includes ten new checks for OAuth navigation, configuration/origin errors, cookie restore, callback failure, bounded polling retry and cancellation of stale browser work. Native T3 preview verified desktop/mobile entry behavior, no horizontal overflow at 390 px, and a visible keyboard focus ring; the isolated UI test server stopped cleanly after these checks.

Recovered Apple developer configuration was exercised live: catalog search returned 20 songs, charts returned 30 candidates, and a Stronger ISRC lookup resolved an Apple preview whose Range probe returned HTTP 206 with CORS support. A native browser separately decoded the real Apple Stronger AAC preview: 29.975 seconds, two channels at 48 kHz. These checks verify sampled catalog, delivery and browser decode paths, not five Spotify accounts, complete import coverage or physical speaker audibility. Exact application callback registration, Spotify allowlisting and real five-account QA are deferred until the user returns. Live browser HTTP search returned 20 signed Apple catalog selections without listening evidence. The user explicitly authorized this checkpoint's commit and push; Git history records its publication.

Reproduce the automated checks with:

```bash
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
node --test tests/frontend/*.test.mjs
```

### Previous redesigned-UI checkpoint evidence

Before the provider changes, the tree passed **132 Python tests** with **94% Rooms/Game coverage** and **66 frontend Node tests**. All 38 frontend modules passed syntax, relative-import and live HTTP/MIME checks. Native preview open timed out in that revision; this historical limitation does not describe the new admission entry checks above.

The backend tests exercise real temporary SQLite/HTTP search-to-answer paths, signatures, room scope, expiry, historical migration, scoring, provider failure, concurrency and unchanged game lifecycle constraints. Frontend tests exercise accepted receipts, stale polls, round changes, submission races, request cancellation, clock estimates, audio scheduling/deduplication and measured waveform levels. The new tests also sample grounded contour geometry, squash/stretch area, anticipation/landing, sad posture, reduced-motion poses, spring stability and frame loop cleanup; populated schema-v2 upgrades preserve every non-color field. Reveal classification checks include wrong-song answers that earned listener points. The round refinement removes the lab caption, uses an open 200-degree timer arc and shares remaining/elapsed arithmetic with the waveform. Drawing supports bars, a smooth envelope or a custom path callback. Measured levels cover all channels and only the actual playback window. Thirteen additional Node tests cover timing boundaries, geometry/customization, silence, stereo/window extraction, scheduled preview playback, cancellation during decode and denied/unavailable playback. The lab clock advances and its scene controller schedules the bundled fake-song clip after a three-second countdown; it never changes persistent game state. Modules and served assets pass checks. A static render of the actual arc and waveform extracted from the bundled MP3 was inspected. Native preview open still times out, so rendered layout and audible playback of this revision remain unverified.

The newer reveal/standings revision removes all waveform playback controls and the icon column; audio and measured progress continue after submission until closure. Decorative notes are nonselectable SVGs. Reveal has a central cover, personal song/artist/listener feedback and authoritative points, with listener characters on either side. The podium displays 2–1–3, then compact rank rows; server ranks, ties and final/partial states are preserved. New projection tests cover all four listener-selection cases, Nobody versus missing submissions, artist partial credit, frozen/departed identities, ties and phase deadlines. A controller regression confirms submission does not stop/restart audio and reveal stops it once. This layout/audio revision still needs live native-preview inspection because preview open times out.

Before the fluid-blob revision, the native T3 browser verified real create/join across three origins, host-only settings and character changes, shared audio activation/preload, automatic readiness, countdowns, catalog selection and listener-only submission, reveal, rankings and history. An isolated server used larger temporary metadata fixtures with the existing four clips; its ten-round game completed. All three sessions returned identical final rankings. SQLite confirms ten revealed attempts, 26 submitted answers and four missing answers, with missing answers worth zero. A real Apple song selection was stored; no JavaScript errors were captured on the three sessions. Some background-browser timers missed submissions, correctly recorded as No answer. Refresh restored the host identity and final ranking, and history/back-to-lobby navigation worked. That full-match run predates the fluid-blob revision and is integration evidence with test data, not a claim that the runtime four-song seed can start a full match.

Earlier standalone/browser checks verified retained SVG nodes, running character animations, headphone removal, direct player selection, ArrowUp/Enter song selection, blocked unselected title submission and keyboard handling during a pending search reload. Real public metadata search returned 20 suggestions beyond the game pool. Null and broken artwork references displayed the placeholder. Inspected 320- and 375-pixel layouts had no horizontal overflow; phone layout keeps Submit within reach while player cards scroll. Desktop screenshots/recording were captured through T3 preview. The latest contour revision shares idle/submitted eye size and glints and adds travelling surface waves along precomputed normals, with extra lobe movement and anchored ground contact. Two additional tests hold the body pose fixed to verify local deformation, then sample repeated cycles for continuity, bounds and limited area drift. All 37 frontend tests pass. Native preview still times out; live visual inspection of these changes remains pending.

The later silhouette revision adds 23 asymmetric contour anchors, larger idle eye ovals/glints and a separate 850ms headphone departure clip. Four additional frontend tests check lobe geometry, continuity, timing and reduced/restored final gear state. A static render of the actual SVG contour/face was inspected; native preview open/snapshot repeatedly timed out, so live inspection of this latest revision remains pending. Earlier browser evidence below predates these changes.

The fluid-blob revision was separately inspected in native preview recordings: body contours change, SVG nodes survive color updates, offscreen instances unsubscribe and return when visible. A real lobby color edit persisted to the API, player portrait and profile, then survived refresh; native ArrowRight changed and persisted the selected color while retaining focus. The standalone scene previews all colors/moods and squish/greeting reactions. The wrong-answer reveal shows sad feedback with positive listener points. Integrated submission removes headphones without rebuilding SVG. A controlled media-query fixture stopped/restarted the real component loop when reduced motion changed (0 frames → 13 frames → stopped); this is separate from changing an actual OS preference. Desktop views remain within their viewport. A 375px standalone check found gallery minimum-width overflow; the gallery now uses shrinking grid columns. Native preview disconnected before that layout could be rechecked, so the small-screen blob lab needs a repeat inspection. Earlier product-screen phone-layout evidence is recorded above.

Physical speaker audibility, iOS/Android behavior, reduced-motion preference changes, and network start-drift/performance acceptance still need separate validation.

## Integrated backend evidence

Before the redesign, the backend-only candidate passed 93 Python tests with 93% Rooms/Game coverage. Its separate CLI smoke run verified API health/docs, all four clips and the cover, byte ranges, traversal rejection and four-song admission. The root and removed UI routes returned 404 in that backend-only tree; the current frontend intentionally replaces root with the game entry. This evidence describes the merged backend checkpoint, not verification of the current UI.

## Preserved combined checkpoint

`feature/demo-core` retains the temporary browser UI and its 12 module behavior checks. Its reported 93-test Python run and 93% Rooms/Game coverage preceded this split; current candidate evidence above is separate. Its latest browser checks covered host/guest admission, refresh identity restoration, three-player rosters, four-song assignments and the insufficient-catalog notice. The full match and capacity observations below are older runs and do not establish playability of the current four-song catalog or the current frontend.

## Historical frontend evidence

The following run used the earlier large fixture catalog, before the four-song cleanup. It validates the implemented game loop under that test data and is not a claim that the current four-song seed supports a ten-round match.

The T3 collaborative browser ran three separate player sessions using `localhost`, `127.0.0.1`, and `localhost.` origins, each with its own room cookie. Host, Ada and Grace joined through the browser UI. Host audio activation produced a running AudioContext, and 40 planned/reserve clips decoded before play. The ten-round game advanced through automatic check-ins, countdowns, answering, reveals and leaderboards, then completed with identical final rankings on the sessions inspected. SQLite confirms ten revealed attempts, 27 submitted answers and three missing answers, retained separately with zero missing-answer points. Automated DOM clicks supplied test guesses; background-tab scheduling affected some submissions. No JavaScript errors were captured in the session traces.

Both a null cover reference and a deliberately broken image URL displayed the bundled placeholder. A 375 × 667 viewport showed no horizontal overflow in the inspected game screen. This is a desktop engine at a phone-sized viewport, not physical iOS/Android acceptance. The preview screenshot tool failed; verification used page inspection and interaction tools, and no screenshot or visual-polish acceptance is claimed.

The native preview was intermittent after viewport changes. Final completion is also verified independently through persisted game/round/answer data. Browser refresh after completion restored the host identity and the final ranking, and Back to the listening room restored the lobby. The latest submission/HTTP-LAN fixes have separate handler checks; the complete ten-round run preceded them.

## Historical capacity evidence and limits

```bash
python -m tools.load_demo
```

The probe now runs as a module. The measurements below predate structural reorganization. This repeatable probe prepares 20 active answering-phase games with ten players each in temporary SQLite storage, then calls the actual ASGI state endpoint 400 times with 20 workers. Injected time holds the answer windows steady. All **400 requests succeeded**, game versions stayed unchanged during reads, and the measured throughput was **463.7 requests/second**, median **40.6 ms**, p95 **75.5 ms** on the development Mac. Removing redundant per-poll database connections improved the earlier 289.9 requests/second result.

This measures server state reads through the real application, including its identity checks and projections. It excludes HTTP network transport, concurrent answer/closure workloads and browser delivery. It is preliminary capacity evidence, not Azure/storage/load acceptance. The complete two-second readiness/start trace and supported-device synchronization target still need dedicated measurement.

## Remaining gates

- Populate the runtime catalog with recognizable songs, including requested Kanye selections, enough personal/decoy candidates and checked replacements.
- Test audible playback, autoplay, refresh and background behavior on real phones; the current three-session browser game used isolated fixtures.
- Measure the defined readiness/start-delivery target and deployment load; optional all-device audio remains disabled until separate drift/audibility evidence.
- Validate personal-provider authorization/import, familiarity, candidate quantity and complete artist credits before enabling Normal mode.
- Validate persistent SQLite WAL storage and consistent backup/restore for deployment.
- Finish course reporting, user-owned comprehension explanations and genuine Git publication cadence. No current frontend commit, push or deployment is claimed.

No Dockerfile, CI workflow or public deployment has been added. Lobby settings stay process-local until Start; only completed games renew room retention.
