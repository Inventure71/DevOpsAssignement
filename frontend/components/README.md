# Reusable UI components

Import `character.mjs` or `player-card.mjs` as ES modules. Both components retain their SVG and shadow DOM across state updates; they need no framework dependency.

```html
<repeat-character
  color="coral"
  mood="listening"
  style="width: 280px"
></repeat-character>
```

Colors: `coral`, `periwinkle`, `lavender`, `lemon`, `lilac`, `sage`, `sky`, `rose`. Moods: `idle`, `listening`, `submitted`, `celebrating`, `sad`. Only `listening` wears headphones; a visible listening-to-submitted transition loosens, lifts, tilts and fades them over 850ms. Restored submissions and reduced-motion users see the final state immediately. `blob-headphones.mjs` owns that independent clip. All colors use one rounded, asymmetric deformable body. `blob-rig.mjs` owns pure motion clips, contour deformation and damped joint springs. `character.mjs` renders the persistent SVG and blends mood changes. `blob-motion.mjs` shares one 30 fps frame loop across visible instances. Reduced motion, hidden documents, offscreen sprites and thumbnails at or below 56px stop continuous animation. Sadness retains a quiet slumped posture under reduced motion. Idle and submitted use the same larger oval eyes and small glint, retaining blink/gaze motion. Idle also has a soft curved smile. Surface waves move the contour and lobes along precomputed normals even when the main pose stays still; contact points stay planted and reduced motion suppresses the waves. Headphone joints and the face stay mounted across transitions.

Call `sprite.react('poke')` or `sprite.react('greet')` for brief body reactions. The sprite is decorative; the control or screen containing it supplies its name.

`<blob-color-picker preview value="coral">` optionally displays a larger preview. Set `.value` and `.disabled`; its bubbling/composed `color-select` event carries `{color}`. Swatches use native buttons, selected checkmarks, arrow/Home/End navigation and palette labels. Entry and lobby reuse this control. The server's existing `character_id` field stores the color ID; migration 003 translates previous character IDs in live players and frozen rosters.

```js
const card = document.createElement("player-card");
card.data = {
  id: "player-1",
  nickname: "Jules",
  character_id: "coral",
  is_host: false,
  connected: true,
  status: "listening",
  selected: false,
  selectable: true,
  disabled: false,
  variant: "round",
};
card.addEventListener("player-select", (event) =>
  toggleListener(event.detail.id),
);
```

Status values: `listening`, `submitted`, `ready`, `not-ready`, `joining`. Variants: `round`, `lobby`. Assign `.data` after each state change; selection is controlled by the caller. The bubbling, composed `player-select` event reports the player ID without changing selection itself. A native button supplies keyboard activation, disabled behavior, focus feedback, and `aria-pressed`. Nonselectable cards are display-only. Names use text nodes, including long names. The small selection dot and portrait ring show the caller's selected state.

`SongSearch` owns debounced/cancellable queries and keyboard navigation. Set its `.search(query, {signal})` function, `.selection`, `.disabled` and `.submitted`. The composed `song-select` event carries `{song}` or null. Before submitting, check `.hasUnselectedQuery` and call `.reportSelectionRequired()` when true; typed text alone is never an answer. Clearing permits an explicit listener-only answer.

`RoundCountdown.data` accepts `{startsAt, deadline, phase, submitted, now}`; call `.tick(now)` from the screen clock. Its upper 200-degree arc leaves the bottom open and represents the remaining answer time, with accessible progress values. Both countdown and waveform use `../game/timing.mjs`, including exact start/deadline boundaries. Components own no timers, persistence or scoring.

`MusicWaveform.data` accepts `{startsAt, deadline, levels, now}`; call `.tick(now)` from the same screen clock. `levels` are measured normalized RMS values for the played window, including all audio channels. Missing data shows plain progress and measured silence stays flat. Played/unplayed SVG layers retain their paths across ticks; resizing or changed measurements rebuild geometry.

```js
const waveform = document.querySelector("music-waveform");
waveform.appearance = {
  mode: "bars", // 'line' draws a smooth amplitude envelope
  barCount: 64,
  height: 46,
  gap: 4,
  barWidth: 5,
  lineWidth: 2.5,
  playedColor: "#151515",
  unplayedColor: "#d7d4d9",
};
waveform.data = { levels, startsAt, deadline, now };
```

For a custom drawing, assign `.draw(context)` returning up to eight `{d, fill}` SVG paths. The immutable context supplies the original normalized `levels`, peak-preserving display `samples`, `width`, `height`, `mode`, `gap`, `barCount` and `strokeWidth`. Colors and elapsed clipping stay independent of the drawing. Set `.draw = null` to restore the built-in renderer. For example:

```js
waveform.draw = ({ samples, width, height }) => [
  {
    d: samples
      .map((level, index) => {
        const x = (width * (index + 0.5)) / samples.length;
        const radius = ((height - 6) * level) / 2;
        return `M${x} ${height / 2 - radius}V${height / 2 + radius}`;
      })
      .join(""),
    fill: false,
  },
];
```

The drawing never fetches or schedules audio and has no playback controls or icon column. Submission does not stop, dim or freeze the drawing. Production rounds retain shared host audio until closure. `../audio/lab.mjs` owns the isolated lab clip; the Listening/Submitted scene controller schedules it after a three-second countdown. Selecting Listening or Submitted unlocks browser audio permission when necessary; there is no Play button. Add `&waveform=line` to preview the alternative drawing. Other scene navigation/hidden pages stop preview playback. Switching from an active Listening fixture to Submitted keeps its current source and timeline. The lab obtains its song metadata and audio URL once from `/api/demo/preview`, using the installed Demo pack. Alternate guesses are metadata-only display samples. Preview playback starts from a scene click; startup never starts audio. If the pack is unavailable, Characters and Lobby remain usable and music scenes explain how to install it and reload.

`ListenerResult.data` receives one display projection from `roundResult(state)`: the frozen identity/color, local selected status, actual collection membership, listener verdict and mood. It retains its character and labels across updates. Wrong listener selections use sadness; correct selections use celebration; missing submissions stay neutral. Explicit submitted Nobody differs from No answer.

`createStandingsView()` returns `{element, update(standings, myPlayerId), destroy}`. It retains keyed characters, displays a 2–1–3 podium and remaining rows, preserves server ranks/ties and never recalculates scores. `createRevealView()` composes the cover/fallback, personal outcome summary and the viewer's listener verdicts. Other players' answers are never sent to this view, including for the host. `../screens/results.mjs` supplies the authoritative five-second phase clock and final/history actions. Layout belongs to `styles/results.css`.

Inspect fixtures through `/ui-lab?scene=reveal` or `?scene=leaderboard`; optional `&missing-answer`, `&artist-only`, `&nobody`, `&broken-artwork`, `&wrong-answer` and `&tied-ranks` exercise display cases without game persistence.
