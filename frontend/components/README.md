# Reusable UI components

Import components as native ES modules. They retain their DOM across state updates.

```html
<repeat-character color="coral" mood="listening" style="width: 280px"></repeat-character>
```

Colors: `coral`, `periwinkle`, `lavender`, `lemon`, `lilac`, `sage`, `sky`, `rose`. Moods: `idle`, `listening`, `submitted`, `celebrating`, `sad`. Call `.react("poke")` or `.react("greet")` for a brief reaction. The containing control supplies the accessible name.

`blob-rig.mjs` owns body motion and joint springs; `character.mjs` renders and blends moods. `blob-motion.mjs` shares a 30 fps loop across visible sprites. Reduced motion, hidden documents, offscreen sprites and thumbnails at or below 56 px stop continuous animation. Ground contact remains planted except during jumps.

Listening wears headphones. A listening-to-submitted transition removes them over 850 ms through `blob-headphones.mjs`; restored submissions and reduced motion show the final state immediately.

`<blob-color-picker preview value="coral">` optionally displays a larger preview. Set `.value` and `.disabled`; its bubbling/composed `color-select` event carries `{color}`. Native swatches support arrow/Home/End navigation. Entry and lobby share the picker; the server's `character_id` stores the color ID.

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

Statuses: `listening`, `submitted`, `ready`, `not-ready`, `joining`. Variants: `round`, `lobby`. Assign `.data` after state changes; the caller owns selection. The bubbling/composed `player-select` event carries `{id}`. A native button supplies keyboard, focus, disabled and `aria-pressed` behavior. Nonselectable cards display the player; names use text nodes.

`SongSearch` requests results on Search or Enter and supports arrow-key selection. Set `.search(query, {signal})`, `.resolve(song, {signal})`, `.selection`, `.disabled` and `.submitted`. The composed `song-select` event carries `{song}`, with null on clearing. Before submission, check `.hasUnselectedQuery` and call `.reportSelectionRequired()` if true. Editing and unmount cancel requests; generation checks discard late responses. See [resolution and ambiguity](../../docs/15_GAME_UI_POLISH.md#search-and-selection).

`RoundCountdown.data` accepts `{startsAt, deadline, phase, submitted, now}`. Call `.tick(now)` from the screen clock. Its upper 200-degree arc shows remaining time with accessible progress values.

`MusicWaveform.data` accepts `{startsAt, deadline, levels, now}`; use the same `.tick(now)` clock. Both components use `../game/timing.mjs`. Levels are normalized RMS measurements across all channels in the played window. Silence stays flat; missing measurements show plain progress. Resize/data changes rebuild SVG geometry; clock ticks move the elapsed clip.

```js
const waveform = document.querySelector("music-waveform");
waveform.appearance = {
  mode: "bars", // "line" draws an amplitude envelope
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

Assign `.draw(context)` to return up to eight `{d, fill}` SVG paths. The immutable context supplies original normalized `levels`, peak-preserving display `samples`, `width`, `height`, `mode`, `gap`, `barCount` and `strokeWidth`. Colors and elapsed clipping remain controlled by the component. Set `.draw = null` to restore the built-in drawing.

```js
waveform.draw = ({ samples, width, height }) => [{
  d: samples.map((level, index) => {
    const x = (width * (index + 0.5)) / samples.length;
    const radius = ((height - 6) * level) / 2;
    return `M${x} ${height / 2 - radius}V${height / 2 + radius}`;
  }).join(""),
  fill: false,
}];
```

Audio controllers own fetching, decoding and playback. Submission keeps production host audio playing until closure. The lab reads installed song metadata from `/api/demo/preview`. Clicking Listening or Submitted unlocks preview audio and schedules a three-second countdown. Switching an active Listening fixture to Submitted preserves its source/timeline; other scenes and hidden pages stop preview playback. If music setup fails, Characters and Lobby remain available.

`ListenerResult.data` receives a `roundResult(state)` player projection: frozen identity/color, selected status, actual membership, verdict and mood. Correct selections celebrate, wrong selections look sad and missing submissions remain neutral. Submitted Nobody differs from No answer.

`createStandingsView()` returns `{element, update(standings, myPlayerId), destroy}` and retains keyed players, server ranks and ties. `createRevealView()` composes the cover/fallback, personal outcome and listener verdicts. The server supplies only the viewer's answer, including for hosts. `../screens/results.mjs` supplies the phase clock and final/history actions; `styles/results.css` owns layout.

Inspect `/ui-lab?scene=characters`, `?scene=reveal` or `?scene=leaderboard`. Optional flags: `missing-answer`, `artist-only`, `nobody`, `broken-artwork`, `wrong-answer`, `tied-ranks`; `&waveform=line` previews the envelope.
