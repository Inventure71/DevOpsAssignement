# 10 — Frontend Design

## Direction and implemented scope

Warm backgrounds, Nunito typography, pastel blobs and pill controls connect entry, lobby, rounds and results. Listening, submitted and selected states have distinct visuals. Reveal centers the album cover and personal feedback; standings use a 2–1–3 podium.

The frontend uses native ES modules and Web Components on the API origin. Components retain their DOM across polling updates; keyed players retain focus and animation. Local fonts include their license. A shared animation loop respects reduced motion, visibility and sprite size.

## Boundaries

| Module | Responsibility |
| --- | --- |
| `app.mjs` | Compose dependencies and start the application |
| `application/` | Local state, commands, polling, readiness and screen lifecycle |
| `transport/client.mjs` | Requests, cancellation and server-clock estimates |
| `audio/host.mjs` | Speaker leases, preload/decode and scheduled playback |
| `audio/levels.mjs` | Measured waveform levels |
| `game/` | Pure timing, result and readiness projections |
| `screens/` | Entry, lobby, round, results, help and history layouts |
| `components/` | Reusable controls, characters and views |
| `dom.mjs` | Keyed DOM reconciliation |
| `styles/` | Tokens and responsive layouts |
| `lab/`, `audio/lab.mjs` | Isolated fixtures, character studio and preview playback |

The server owns identity, roster, phases, deadlines and points. The browser derives presentation from those facts. Only the active host receives playback references. All imports use `.mjs`; Node 24 or newer runs the frontend tests directly.

## Results privacy

Reveal publishes the correct song and listeners, plus only the requesting player's `my_answer`. Listener cards compare that player's selections with the actual listeners. Correct selections celebrate, wrong selections look sad and missing submissions stay neutral. Standings show public scores and ranks. The backend enforces answer privacy for hosts and guests.

## Song field

Search or Enter requests catalog results; arrow keys and Enter select a title/artist. Editing clears the selection and cancels pending work. Polling preserves unfinished queries. Room-scoped signed tokens identify accepted guesses, which the server freezes on submission.

Some metadata results require resolution before selection. Errors and ambiguity offer retry or an explicit choice. See [search and selection](15_GAME_UI_POLISH.md#search-and-selection) and [scoring rules](03_GAME_RULES.md).

## Real controls and motion

Lobby settings support 5/10/15 rounds, 10/20/30 seconds, difficulty and optional decoys. Start game activates the host speaker and obtains its lease before starting. Check-in reflects actual readiness. Visible clients acknowledge upcoming preparation during results; the host also requires decoded audio and an active lease.

An empty submitted listener selection means Nobody; a missing submission means No answer. Submission locks answer controls and removes local headphones. Host audio continues until the server closes the attempt. Countdown and waveform share estimated server time; the waveform displays measured audio levels or plain progress when measurements are unavailable.

## Verification and outstanding acceptance

Run `node --test tests/frontend/*.test.mjs`. Tests cover immutable submissions, private results, stale requests, clock boundaries, host leases/recovery and measured audio geometry. Check focus, keyboard selection, reduced motion and narrow layouts in a browser, then follow the [device playtest](16_DEVICE_PLAYTEST.md).

## Implementation checklist

The following sections summarize completed design revisions. Component interfaces and examples are in [the component guide](../frontend/components/README.md).

### Privacy and module cleanup

Personal answer feedback and public standings have separate projections. Application, transport, audio, presentation and lab modules own their respective lifecycles.

### Reveal and standings refinement

`game/results.mjs` projects frozen results. `screens/reveal.mjs` and `components/listener-result.mjs` render the personal outcome; `components/standings.mjs` retains ranked players and ties. `screens/results.mjs` supplies the server phase clock and final/history actions. Layout lives in `styles/results.css`.

### Round layout and sound drawing refinement

`round-countdown` draws an upper 200-degree arc. `music-waveform` retains measured SVG geometry and moves its elapsed clip with the screen clock. Waveform styles support bars, an envelope and custom paths. Production and lab audio controllers own their sources.

### Fluid character revision

`blob-rig.mjs` supplies grounded squash/stretch, contour waves and damped joints. `character.mjs` retains the SVG and blends moods. `blob-motion.mjs` shares frame scheduling; hidden, offscreen, reduced-motion and small sprites stop continuous animation. `blob-headphones.mjs` supplies the 850 ms listening-to-submitted departure; restored submissions show its final state.

The `character_id` field stores one of eight color IDs. `/ui-lab?scene=characters` provides color, mood and reaction controls.

### Initial frontend implementation

Entry, lobby, rounds, results, help and history share reusable components. Demo uses the installed local music pack; Real uses music admission. See [architecture](05_ARCHITECTURE.md) for the backend boundaries and [launch instructions](16_DEVICE_PLAYTEST.md) for setup.
