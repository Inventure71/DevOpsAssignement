> Historical checkpoint/research document. Current architecture, complete
> offline Demo and storage/setup are described in [README](../README.md),
> [architecture](05_ARCHITECTURE.md) and [implementation status](08_IMPLEMENTATION_STATUS.md).
> Four-song references below describe the earlier development seed.

# 10 — Frontend Design

## Direction and implemented scope

The supplied lobby and round references guide warm white backgrounds, rounded
Nunito typography, pastel characters, soft pill controls and a central timer.
Listening, submitted and selected are distinct states. One deformable SVG blob rig
uses eight selectable colors and removes headphones after submission. Direct player-icon
selection uses a muted dot when unselected and a colored dot/ring when selected.
Entry, setup/check-in/countdown and history follow the same visual language.
The supplied results and leaderboard references now guide the cover-centered
reveal and 2–1–3 podium; our shared blob rig remains the character component.

The frontend uses native ES modules and Web Components, served on the API origin.
There is no build step or framework dependency. Local font files include their
license. Components retain their DOM; keyed player updates preserve focus and
animation rather than replacing the entire screen every poll. A shared animation
loop respects reduced motion, offscreen sprites and hidden documents.

## Boundaries

- `app.mjs` composes dependencies and starts the browser application.
- `application/` owns local state, commands, polling and screen lifecycle.
  `screen-host.mjs` selects, mounts and destroys screens and distributes the clock.
- `transport/client.mjs` owns requests, cancellation and server-clock estimates.
- `audio/host.mjs` owns host leases, preload/decode and scheduled playback;
  `audio/levels.mjs` extracts measured waveform data.
- `game/` owns pure timing, result and lobby-readiness projections. These modules
  derive display values from frozen server facts without recalculating points.
- `screens/` composes stable entry, lobby, round, results, help and history layouts.
- `components/` owns reusable characters, controls, standings and the site header,
  with narrow properties and bubbling intent events.
- `dom.mjs` reconciles keyed children without replacing live components.
- `styles/` owns tokens, responsive composition and shared controls.
- `lab.mjs` starts the isolated controller in `lab/`; fixtures and the character
  studio are separate modules. `audio/lab.mjs` owns its preview source.

These boundaries separate transport, orchestration, pure logic and presentation.
They keep changes local and allow behavior tests without introducing a framework
or parallel compatibility paths. All browser modules use explicit `.mjs` imports;
Node 24 or newer runs `node --test tests/frontend/*.test.mjs` directly. There is no
npm manifest, install or build step.

Server state owns identity, roster, phase, deadlines and points. Playing responses
expose nicknames/characters, named submission status, timing and measured waveform
levels. Correct-song and listener facts become public at reveal. Submitted guesses
remain private: reveal responses contain only the requesting player's
`my_answer`, including for the host. Only the active host receives playback
references.

## Results privacy

The reveal shows the album cover, correct title/artist and personal song/artist
feedback. Listener cards compare your selected players with the revealed actual
listeners; their Selected/Not selected and Correct/Wrong states describe your
answer. Their character moods express that local verdict. They do not display
another player's song or listener guesses. The “Everyone’s guesses” section and
its answer table are removed. Shared podiums and ranking rows retain public scores
and ranks. Stored answers remain available to server-side scoring and diagnosis;
privacy is enforced when the backend constructs the response.

## Song field

Typing searches a broad metadata catalog with debounced loading results; players
select a title/artist result, rather than choose among four issued options or send
unmatched raw text. Shared fixture matches are local; other queries use Apple’s
public Search API. The backend signs normalized selected facts for the room and
freezes them on accepted submission. Scoring and structured artist partial credit
follow [the game rules](03_GAME_RULES.md). Provider outage, empty results and rate
limits are visible. Public search returns a primary artist; complete featured-artist
coverage remains a limitation, not inferred from display strings.

Search does not load playable songs into the pool or authenticate music accounts.
The current runtime catalog remains four fake tracks and cannot start a complete
match. Larger metadata fixtures belong only to isolated verification storage.

## Real controls and motion

Lobby settings use supported 5/10/15 rounds, 10/20/30 seconds, difficulty and
optional decoys. The mockup’s privacy selector and manual Ready control have no
backend contract and are omitted. Readiness reflects actual connection/catalog
status. Room invitations and copy/share controls use real room codes.

An empty submitted listener selection means Nobody; no submission means No answer.
Submitting locks the song/player controls and removes the local headphones. Shared
host audio continues for everyone, including the submitting player, until the
server closes the attempt. The waveform uses actual host-decoded levels; absent data shows plain progress. It is
not an unsupported pause or replay control. Timer changes use estimated server
time; client clocks never decide answer acceptance.

## Verification and outstanding acceptance

Module and backend checks cover receipts, draft/round reset, stale polls, clocks,
submission races, signed selections, provider bounds, migrations and measured audio
levels. Current automated and three-session browser evidence is recorded
in [implementation status](08_IMPLEMENTATION_STATUS.md).

Verify standalone characters before integrated screens, then keyboard selection,
input focus, reduced motion, narrow layouts, real admission, host preload/readiness,
submission/reveal, reconnect and automatic phases. A fixture lab does not prove a
playable game; a phone-sized desktop viewport does not prove physical phone audio.
The runtime catalog needs separate population before normal full-match acceptance.

## Implementation checklist

### Privacy and module cleanup

- [x] Remove other-player answer displays and fixtures.
- [x] Keep personal listener verdicts separate from other players' guesses.
- [x] Group application, transport, audio and pure game display responsibilities.
- [x] Extract screen lifecycle, site header and lobby readiness from composition.
- [x] Split the lab bootstrap, fixtures, character studio and controller.
- [x] Use explicit native `.mjs` modules without a frontend dependency manifest.
- [x] Run integrated regression checks and reconcile the evidence record; native
  preview attach timed out, so live visual/audio acceptance remains pending.

### Reveal and standings refinement

Visual thesis: warm, spacious game results, anchored by the album cover and our
fluid pastel blobs. Reveal has one central outcome panel with personal listener
feedback on either side; standings has a 2–1–3 podium followed by compact rows.
Motion keeps existing character moods and adds brief panel entrances and a timed
phase bar, with reduced-motion support.

- [x] Remove waveform playback controls and prevent decorative-note selection.
- [x] Verify audio continues after the local answer until the round closes.
- [x] Project local listener correctness and frozen points without rescoring answers.
- [x] Compose reusable reveal and standings views with retained keyed characters.
- [x] Implement reference hierarchy across desktop/mobile and handle missing answers,
  artwork failure, tied rankings and partial/final standings.
- [x] Run tests and module/asset checks.
- [ ] Inspect the integrated rendered layout/audio when native preview responds.

`game/results.mjs` owns pure display projections from revealed server facts.
`screens/reveal.mjs` owns the cover and personal outcome layout;
`components/listener-result.mjs` owns one player's personal listener feedback.
`components/standings.mjs` owns podium/list rows. `screens/results.mjs` composes
these views with the phase clock and existing final/history actions. Dedicated
`styles/results.css` owns their responsive layout. The audio controller keeps sole
playback ownership; submission changes only answer controls and the character mood.

### Round layout and sound drawing refinement

- [x] Remove the lab caption and reclaim its vertical space.
- [x] Replace the circle with a standalone upper arc; share deadline math with the waveform.
- [x] Keep audio decoding/playback separate from a configurable retained-SVG drawing component.
- [x] Drive the lab with a live clock and a real bundled clip, including playback cleanup.
- [x] Verify timing boundaries, measured waveform windows, drawing customization and module checks.
- [ ] Inspect the integrated layout and playback when native preview responds.

The round screen owns layout and distributes the existing clock. `round-countdown`
and `music-waveform` render that clock without independent timers. Pure timing and
drawing modules own arithmetic and geometry. The production audio controller owns
the host source; `audio/lab.mjs` owns only the isolated preview source. Neither drawing
component fetches audio, grants playback authority or changes scoring.
The upper 200-degree arc has no bottom segment and controls have positive spacing
below the stage. Waveforms draw actual RMS measurements from all channels in the
played window, with bars, a smooth envelope, configurable sizing/colors and custom
path callbacks. Geometry changes only with layout/data; clock ticks move the clip.
The lab has a live clock and automatic scene-controlled playback for the current
bundled fake-song audio. The normal first interaction unlocks browser permission;
the waveform has no playback controls. Native preview remains unresponsive; live layout/audio acceptance
is still pending.

### Fluid character revision

Current silhouette/expression revision:

- [x] Share idle eye size/glint with submitted sprites.
- [x] Add travelling contour deformation along each anchor's outward normal;
  soften side lobes independently while keeping contact points grounded.
- [x] Check stationary-pose deformation, bounds, continuity and reduced motion.

Contour motion belongs in the pure body rig and uses its existing shared clock.
Normals and weights are precomputed once; frame updates only sample two smooth
waves. The renderer retains the same eyes/SVG and the shared frame lifecycle.

- [x] Replace the cone outline with a rounded asymmetric contour and soft lobes.
- [x] Add expressive idle eyes while preserving blink/gaze and sad/listening moods.
- [x] Separate headphone removal motion from the body rig; lift, spread and fade
  only after a listening-to-submitted transition, with a still reduced-motion state.
- [x] Verify geometry and departure timing; inspect a static render of the actual contour/face.
- [ ] Recheck live standalone/integrated animation when native preview responds.

The body contour remains owned by `blob-rig.mjs`; the renderer owns mood transitions
and keeps its joints. A pure headphone clip owns removal timing independently of
body movement, so playback/scoring and persistent color identities are unchanged.

- [x] Separate color presets, pure pose/geometry, frame scheduling and SVG rendering.
- [x] Author grounded squash/stretch, weight shifts, jumping and spring follow-through.
- [x] Reuse a color picker in entry and lobby; migrate live and frozen color IDs.
- [x] Inspect standalone and integrated motion, picker persistence and lifecycle cleanup.
- [x] Verify geometry/scheduler tests and reconcile documentation.

The rig deforms a twenty-three-point asymmetric closed contour, with a rounded
head, soft side lobes and a puddle base. Height compression widens the
body; the base stays grounded except during deliberate jumps. Face and headphone
joints use damped springs. Listening grooves, submitted settling, anticipation,
landing and touch reactions change the body itself. Idle and submitted share
larger soft oval eyes with one small glint; other moods keep their own expression.
Idle also has a curved smile. Two travelling waves deform the contour along
precomputed outward normals, independently of the whole-body pose. Side lobes
have extra softness; surface displacement tapers to zero at ground contact.
Reduced-motion and thumbnail poses disable the surface flow as well as the clips.
Sadness adds drooping brows, a small frown and a slumped body. Mood changes
blend over 250ms without resetting joint momentum. Celebration starts with
anticipation on entry. A single loop paints visible
sprites at approximately 30 fps; small thumbnails, reduced-motion preferences,
offscreen sprites and hidden documents do not consume animation frames.

`blob-headphones.mjs` samples an 850ms departure: loosen the earcups, lift and
tilt the band, then fade. The renderer applies it to a separate outer joint,
preserving the body's animation and headphone follow-through springs. Only an
active listening-to-submitted transition starts it; initial/restored submitted
sprites and reduced-motion views show the final state immediately. The headphone
SVG stays mounted and can be worn again when the next listening phase begins.

The existing API field `character_id` now stores a color ID. Migration 003 maps
the previous identities to matching colors in players and frozen game rosters.
Provider metadata, gameplay, scoring and submitted guesses are unaffected.
The reveal uses the server-derived `song_match` for central song/artist verdicts;
listener points cannot substitute for that classification. In the current results
composition, flanking character moods follow the local listener verdict: correct
selections celebrate, wrong selections look sad and missing submissions stay idle.
`/ui-lab?scene=characters` provides color, mood and reaction controls;
`?scene=reveal&wrong-answer` exercises wrong-song feedback independently of points.

### Initial frontend implementation

- [x] Define module boundaries and server/client authority.
- [x] Build and inspect reusable animated characters independently.
- [x] Integrate real lobby, listening and submitted controls.
- [x] Replace four-choice answers with signed catalog selections and migration.
- [x] Approximate supporting pages and provide isolated visual scenes.
- [x] Verify keyboard, retained DOM, artwork fallback and narrow layouts.
- [x] Complete the three-session browser game with isolated fixtures.
- [x] Run Python/Node checks and reconcile documentation.
- [ ] Populate the playback catalog and validate physical-device audio/synchronization.
