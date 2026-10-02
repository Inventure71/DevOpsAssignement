# 08 — Implementation Status

Updated 2026-10-02. Backend [PR #1](https://github.com/Inventure71/DevOpsAssignement/pull/1)
is merged into `integration`. The redesigned UI checkpoint is committed on
`feature/frontend` at `a05e19e`; this checkpoint adds the Spotify/Apple provider
integration. The original combined Demo checkpoint remains preserved on
`feature/demo-core` (`bcdcd3d`).

## Current implementation

The FastAPI/SQLite Rooms and Game domains retain the integrated backend’s identity,
fixed-roster, phase, scoring, void-attempt, recovery and history behavior. A native
ES module frontend is served at `/`; browser assets are at `/ui/` and catalog
media at `/static/demo/`. No frontend bundler or npm dependencies are needed.

The new UI implements create/join, lobby settings and character selection,
setup/check-in/countdown, listening and submitted rounds, direct player-icon
selection, reveal with artwork fallback, leaderboard and room-history navigation.
One deformable blob rig has eight selectable colors, friendly open eyes and
listening/submitted/celebrating/sad moods. It retains its SVG nodes across updates.
Pure contour clips and damped face/headphone joints share one visible 30 fps loop;
offscreen and small thumbnail instances do not animate. Mounted screens and keyed player cards preserve focus and drafts.
Reduced motion and document visibility govern continuous motion. `/ui-lab` uses
isolated fixtures for visual/component checks; it is not a playable game.

Song-name typeahead searches shared Demo fixtures and the configured Apple
developer catalog, with public iTunes metadata fallback for no-credentials Demo,
not four round options. Server-signed room selections freeze title, artist,
structured identity and optional artwork into answers. Provider calls occur outside
room command locks; submission performs no provider lookup. Search is bounded by
cache, timeout, single-flight calls and a process-wide request budget. Apple
developer searches request structured artist relationships. Preview matching
preserves Spotify credits and adds verified Apple aliases; missing featured
credits remain unavailable. Search stays independent of personal authorization
and playback import.

Migration 3 translates live/frozen character IDs to color IDs without changing
credentials, membership, guesses or scores. Revealed answers now include
`song_match`, sharing the frozen-song classifier with scoring. Song verdicts
do not depend on total points; artist partial credit and unanswered guesses have
separate feedback. The field stays hidden before reveal.

Migration 2 replaces choice-index answers with nullable selected-song JSON and
converts historical answers without changing stored scores. Host preload reports
can include normalized waveform levels measured from decoded audio; public round
state exposes levels without its private playback URL.

The runtime catalog still contains exactly **four fictional personal songs**, four
original 30-second MP3s and one SVG cover. It supports admission/lobby/media checks
and correctly rejects Start with `insufficient_songs`. A complete match requires
at least ten songs per player plus sufficient distinct candidates and reserves.
Larger test metadata remains isolated. Real-song Demo population remains pending.
Normal Spotify import is now implemented; real five-account acceptance remains
pending rather than inferred from fixture tests.

Normal admission verifies each player's own Spotify account through cookie-bound
PKCE, imports at most 60 balanced top/recent candidates, resolves Apple previews
and requires at least ten playable personal songs. Host import obtains independent
Apple chart candidates. The host counts toward the five-player/app-account limit.
Receipt, queue and worker bounds keep provider work outside transactions; atomic
admission rechecks room state, nickname, capacity and account uniqueness.

Migration 4 adds room-scoped account digests and explicit song pool kinds.
Unavailable observed songs preserve ownership when another import later supplies
playable media; their absence from a snapshot does not fabricate decoys. Frozen
recording keys and verified artist aliases support Spotify-import/Apple-search
scoring. Incompatible versions that share a mislabeled ISRC stay separate, and
ISRC equality alone never awards full credit.
No OAuth access/refresh token enters SQLite, public state or answer snapshots.
The browser has explicit Spotify/Demo selection, import progress, finite connection
retry and verification-error recovery. See [the checkpoint](13_SPOTIFY_IMPLEMENTATION.md).

The results contract is now owner-only: `reveal.my_answer` contains the requesting
player's answer; the API never includes other players' song/listener guesses,
including for the host. All answer records remain in SQLite for internal
diagnosis. Correct song/listener facts, submission status and score/rank totals
remain public. The shared guesses table and its unused styles were removed.

Frontend `.mjs` modules now separate application state/commands/runtime, transport,
audio, pure display logic, screen lifecycle, header controls and isolated lab
fixtures. Room SQL lives in its repository; room services retain rules. Runtime
generations stop old in-flight poll/heartbeat work from restarting duplicate loops
or applying stale state after stop/start. See [cleanup record](11_CODE_CLEANUP.md).

## Current verification

The provider checkpoint passes **228 Python tests**, **94% Rooms/Game coverage**,
and **76 frontend Node tests**. All 40 frontend modules pass syntax checks.
Five separate HTTP cookie sessions complete games of 5, 10 and 15 rounds through
OAuth receipts, imported shared ownership, host preload reports, automatic
readiness/countdowns, signed catalog answers, private reveals, rankings, history
and rematch. Provider boundaries are faked; HTTP, SQLite, signing and game services
are real. Additional tests prove concurrent five-player capacity, cancellation,
expiry rollback, unavailable-song ownership, conflicting ISRC versions, migration
preservation and identity restoration through a fresh application startup.
The frontend admission revision includes
ten new checks for OAuth navigation, configuration/origin errors, cookie restore,
callback failure, bounded polling retry and cancellation of stale browser work.
Native T3 preview verified desktop/mobile entry behavior, no horizontal overflow
at 390 px, and a visible keyboard focus ring; the isolated UI test server stopped
cleanly after these checks.

Recovered Apple developer configuration was exercised live: catalog search
returned 20 songs, charts returned 30 candidates, and a Stronger ISRC lookup
resolved an Apple preview whose Range probe returned HTTP 206 with CORS support.
A native browser separately decoded the real Apple Stronger AAC preview:
29.975 seconds, two channels at 48 kHz. These checks verify sampled catalog,
delivery and browser decode paths, not five Spotify accounts, complete import
coverage or physical speaker audibility. Exact application
callback registration, Spotify allowlisting and real five-account QA are deferred
until the user returns. Live browser HTTP search returned 20 signed Apple catalog
selections without listening evidence. The user explicitly authorized this
checkpoint's commit and push; Git history records its publication.

Reproduce the automated checks with:

```bash
python -m pytest -q --cov=backend.rooms --cov=backend.game --cov-report=term-missing
node --test tests/frontend/*.test.mjs
```

### Previous redesigned-UI checkpoint evidence

Before the provider changes, the tree passed **132 Python tests** with **94%
Rooms/Game coverage** and **66 frontend Node tests**. All 38 frontend modules
passed syntax, relative-import and live HTTP/MIME checks. Native preview open
timed out in that revision; this historical limitation does not describe the
new admission entry checks above.

The backend tests exercise real temporary SQLite/HTTP search-to-answer paths,
signatures, room scope, expiry, historical migration, scoring, provider failure,
concurrency and unchanged game lifecycle constraints. Frontend tests exercise
accepted receipts, stale polls, round changes, submission races, request cancellation,
clock estimates, audio scheduling/deduplication and measured waveform levels.
The new tests also sample grounded contour geometry, squash/stretch area,
anticipation/landing, sad posture, reduced-motion poses, spring stability and frame
loop cleanup; populated schema-v2 upgrades preserve every non-color field. Reveal
classification checks include wrong-song answers that earned listener points.
The round refinement removes the lab caption, uses an open 200-degree timer arc
and shares remaining/elapsed arithmetic with the waveform. Drawing supports bars,
a smooth envelope or a custom path callback. Measured levels cover all channels
and only the actual playback window. Thirteen additional Node tests cover timing
boundaries, geometry/customization, silence, stereo/window extraction, scheduled
preview playback, cancellation during decode and denied/unavailable playback.
The lab clock advances and its scene controller schedules the bundled fake-song
clip after a three-second countdown; it never changes persistent game state. Modules and
served assets pass checks. A static render of the actual arc and waveform extracted
from the bundled MP3 was inspected. Native preview open still times out, so rendered layout
and audible playback of this revision remain unverified.

The newer reveal/standings revision removes all waveform playback controls and
the icon column; audio and measured progress continue after submission until
closure. Decorative notes are nonselectable SVGs. Reveal has a central cover,
personal song/artist/listener feedback and authoritative points, with listener
characters on either side. The podium displays 2–1–3, then compact rank rows;
server ranks, ties and final/partial states are preserved. New projection tests
cover all four listener-selection cases, Nobody versus missing submissions,
artist partial credit, frozen/departed identities, ties and phase deadlines.
A controller regression confirms submission does not stop/restart audio and
reveal stops it once. This layout/audio revision still needs live native-preview
inspection because preview open times out.

Before the fluid-blob revision, the native T3 browser verified real create/join across three origins, host-only
settings and character changes, shared audio activation/preload, automatic readiness,
countdowns, catalog selection and listener-only submission, reveal, rankings and
history. An isolated server used larger temporary metadata fixtures with the existing
four clips; its ten-round game completed. All three sessions returned identical
final rankings. SQLite confirms ten revealed attempts, 26 submitted answers and
four missing answers, with missing answers worth zero. A real Apple song selection
was stored; no JavaScript errors were captured on the three sessions. Some
background-browser timers missed submissions, correctly recorded as No answer.
Refresh restored the host identity and final ranking, and history/back-to-lobby
navigation worked. That full-match run predates the fluid-blob revision and is integration evidence with test data, not a claim
that the runtime four-song seed can start a full match.

Earlier standalone/browser checks verified retained SVG nodes, running character animations,
headphone removal, direct player selection, ArrowUp/Enter song selection, blocked
unselected title submission and keyboard handling during a pending search reload.
Real public metadata search returned 20 suggestions beyond the game pool. Null and
broken artwork references displayed the placeholder. Inspected 320- and 375-pixel
layouts had no horizontal overflow; phone layout keeps Submit within reach while
player cards scroll. Desktop screenshots/recording were captured through T3 preview.
The latest contour revision shares idle/submitted eye size and glints and adds
travelling surface waves along precomputed normals, with extra lobe movement and
anchored ground contact. Two additional tests hold the body pose fixed to verify
local deformation, then sample repeated cycles for continuity, bounds and limited
area drift. All 37 frontend tests pass. Native preview still times out; live
visual inspection of these changes remains pending.

The later silhouette revision adds 23 asymmetric contour anchors, larger idle
eye ovals/glints and a separate 850ms headphone departure clip. Four additional
frontend tests check lobe geometry, continuity, timing and reduced/restored final
gear state. A static render of the actual SVG contour/face was inspected; native
preview open/snapshot repeatedly timed out, so live inspection of this latest
revision remains pending. Earlier browser evidence below predates these changes.

The fluid-blob revision was separately inspected in native preview recordings:
body contours change, SVG nodes survive color updates, offscreen instances
unsubscribe and return when visible. A real lobby color edit persisted to the API,
player portrait and profile, then survived refresh; native ArrowRight changed and
persisted the selected color while retaining focus. The standalone scene previews
all colors/moods and squish/greeting reactions. The wrong-answer reveal shows sad
feedback with positive listener points. Integrated submission removes headphones
without rebuilding SVG. A controlled media-query fixture stopped/restarted the
real component loop when reduced motion changed (0 frames → 13 frames → stopped);
this is separate from changing an actual OS preference. Desktop views remain
within their viewport. A 375px standalone check found gallery minimum-width
overflow; the gallery now uses shrinking grid columns. Native preview disconnected
before that layout could be rechecked, so the small-screen blob lab needs a repeat
inspection. Earlier product-screen phone-layout evidence is recorded above.

Physical speaker audibility, iOS/Android behavior, reduced-motion preference changes,
and network start-drift/performance acceptance still need separate validation.

## Integrated backend evidence

Before the redesign, the backend-only candidate passed 93 Python tests with 93%
Rooms/Game coverage. Its separate CLI smoke run verified API health/docs, all four
clips and the cover, byte ranges, traversal rejection and four-song admission.
The root and removed UI routes returned 404 in that backend-only tree; the current
frontend intentionally replaces root with the game entry. This evidence describes
the merged backend checkpoint, not verification of the current UI.

## Preserved combined checkpoint

`feature/demo-core` retains the temporary browser UI and its 12 module behavior
checks. Its reported 93-test Python run and 93% Rooms/Game coverage preceded
this split; current candidate evidence above is separate. Its latest browser
checks covered host/guest admission, refresh identity restoration, three-player
rosters, four-song assignments and the insufficient-catalog notice. The full
match and capacity observations below are older runs and do not establish
playability of the current four-song catalog or the current frontend.

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

- Populate the runtime catalog with recognizable songs, including requested Kanye
  selections, enough personal/decoy candidates and checked replacements.
- Test audible playback, autoplay, refresh and background behavior on real phones;
  the current three-session browser game used isolated fixtures.
- Measure the defined readiness/start-delivery target and deployment load; optional
  all-device audio remains disabled until separate drift/audibility evidence.
- Validate personal-provider authorization/import, familiarity, candidate quantity
  and complete artist credits before enabling Normal mode.
- Validate persistent SQLite WAL storage and consistent backup/restore for deployment.
- Finish course reporting, user-owned comprehension explanations and genuine Git
  publication cadence. No current frontend commit, push or deployment is claimed.

No Dockerfile, CI workflow or public deployment has been added. Lobby settings stay
process-local until Start; only completed games renew room retention.
