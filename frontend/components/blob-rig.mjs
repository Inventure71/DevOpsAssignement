// Pure animation clips and a deformable control-point cage; no DOM or clock reads.
// Feet stay at GROUND unless a clip deliberately jumps. Width compensates height.
const GROUND = 212;
const CENTER = 120;
const OUTLINE = Object.freeze(
  [
    [118, 57],
    [145, 58],
    [163, 72],
    [174, 95],
    [171, 119],
    [182, 138],
    [189, 148],
    [184, 161],
    [173, 167],
    [185, 184],
    [178, 201],
    [151, 210],
    [120, 212],
    [91, 209],
    [67, 211],
    [50, 201],
    [51, 187],
    [62, 176],
    [62, 154],
    [57, 136],
    [60, 110],
    [72, 83],
    [92, 64],
  ].map(Object.freeze),
);
const NEUTRAL = Object.freeze({
  squash: 0,
  lean: 0,
  headDrop: 0,
  jump: 0,
  reach: 0,
});
const LISTENING = [
  [0, { squash: 0.27, lean: -0.95, headDrop: 3 }],
  [0.13, { squash: -0.12, lean: -0.55, headDrop: -2 }],
  [0.29, { squash: 0.03, lean: 0.2, headDrop: 0 }],
  [0.5, { squash: 0.27, lean: 0.95, headDrop: 3 }],
  [0.63, { squash: -0.12, lean: 0.55, headDrop: -2 }],
  [0.79, { squash: 0.03, lean: -0.2, headDrop: 0 }],
  [1, { squash: 0.27, lean: -0.95, headDrop: 3 }],
];
const IDLE = [
  [0, { squash: 0, lean: -0.12 }],
  [0.28, { squash: -0.025, lean: 0.1 }],
  [0.4, { squash: 0.045, lean: 0.17, headDrop: 1 }],
  [0.72, { squash: -0.015, lean: -0.05 }],
  [1, { squash: 0, lean: -0.12 }],
];
const CELEBRATING = [
  [0, {}],
  [0.15, { squash: 0.5, lean: -0.2, headDrop: 4 }],
  [0.28, { squash: -0.18, jump: 28, reach: 0.8 }],
  [0.4, { squash: -0.08, jump: 35, reach: 1 }],
  [0.59, { squash: 0.56, headDrop: 5, reach: 0.15 }],
  [0.7, { squash: -0.09, jump: 7, lean: 0.15 }],
  [0.85, { squash: 0.035 }],
  [1, {}],
];
const SETTLE = [
  [0, { squash: 0.12, lean: 0.15 }],
  [0.15, { squash: 0.29, headDrop: 2, reach: 0.3 }],
  [0.36, { squash: -0.12, lean: 0.3, reach: 0.45 }],
  [0.65, { squash: 0.08, lean: -0.1 }],
  [1, {}],
];
const SAD = [
  [0, { squash: 0.18, lean: -0.18, headDrop: 5, reach: -0.15 }],
  [0.24, { squash: 0.25, lean: -0.22, headDrop: 7, reach: -0.2 }],
  [0.38, { squash: 0.14, lean: -0.13, headDrop: 4, reach: -0.1 }],
  [0.7, { squash: 0.2, lean: -0.17, headDrop: 6, reach: -0.15 }],
  [1, { squash: 0.18, lean: -0.18, headDrop: 5, reach: -0.15 }],
];
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const smooth = (t) => t * t * (3 - 2 * t);
// Rest-space normals keep the travelling ripple attached to the material rather
// than shifting a rigid silhouette. Contact points taper to zero displacement.
const FLOW_CAGE = OUTLINE.map(([x, y], index) => {
  const before = OUTLINE[(index + OUTLINE.length - 1) % OUTLINE.length];
  const after = OUTLINE[(index + 1) % OUTLINE.length];
  const dx = after[0] - before[0],
    dy = after[1] - before[1];
  const length = Math.hypot(dx, dy);
  const contact = smooth(clamp((GROUND - y) / 26, 0, 1));
  const lobe = Math.exp(-(((y - 158) / 32) ** 2));
  return {
    x,
    y,
    normalX: dy / length,
    normalY: -dx / length,
    phase: (index / OUTLINE.length) * Math.PI * 2,
    weight: contact * (1 + lobe * 0.7),
  };
});
function clip(frames, position) {
  const t = clamp(position, 0, 1);
  let index = 0;
  while (index < frames.length - 2 && t > frames[index + 1][0]) index++;
  const [start, a] = frames[index];
  const [end, b] = frames[index + 1];
  const mix = smooth((t - start) / (end - start));
  return Object.fromEntries(
    Object.entries(NEUTRAL).map(([key, neutral]) => [
      key,
      (a[key] ?? neutral) * (1 - mix) + (b[key] ?? neutral) * mix,
    ]),
  );
}
function loop(seconds, period) {
  return (((seconds % period) + period) % period) / period;
}
export function sampleBlobMotion(
  mood,
  seconds,
  {
    moodAge = Infinity,
    reactionAge = Infinity,
    reaction = "poke",
    reduced = false,
  } = {},
) {
  if (reduced)
    return {
      ...NEUTRAL,
      ...(mood === "sad" ? SAD[0][1] : {}),
      blink: 0,
      energy: 0,
      gaze: 0,
    };
  let pose =
    mood === "listening"
      ? clip(LISTENING, loop(seconds, 1.4))
      : mood === "celebrating"
        ? clip(
            CELEBRATING,
            loop(Number.isFinite(moodAge) ? moodAge : seconds, 2.4),
          )
        : mood === "sad"
          ? clip(SAD, loop(seconds, 6))
          : clip(IDLE, loop(seconds, 7.2));
  if (mood === "submitted" && moodAge < 1.15) {
    const settle = clip(SETTLE, moodAge / 1.15);
    for (const key of Object.keys(NEUTRAL)) pose[key] += settle[key];
  }
  if (reactionAge >= 0 && reactionAge < 1.4) {
    const decay = Math.exp(-reactionAge * 4.5);
    pose.squash += Math.sin(reactionAge * 13 + 0.7) * 0.38 * decay;
    if (reaction === "greet") {
      pose.reach += Math.sin(Math.min(1, reactionAge / 0.9) * Math.PI) * 0.65;
      pose.lean += Math.sin(reactionAge * 8) * 0.2 * decay;
    }
  }
  const blinkPhase = loop(seconds + 0.83, 5.7);
  const blink =
    blinkPhase < 0.035 ? Math.sin((blinkPhase / 0.035) * Math.PI) ** 2 : 0;
  return {
    ...pose,
    squash: clamp(pose.squash, -0.3, 0.7),
    energy: mood === "listening" || mood === "celebrating" ? 1 : 0.15,
    blink,
    gaze: mood === "sad" ? -0.25 : Math.sin(seconds * 0.67) * 0.45,
  };
}
const number = (value) => Number(value.toFixed(2));
function outlinePath(points, floor) {
  const count = points.length;
  let path = `M${number(points[0][0])} ${number(points[0][1])}`;
  for (let i = 0; i < count; i++) {
    const before = points[(i + count - 1) % count];
    const from = points[i];
    const to = points[(i + 1) % count];
    const after = points[(i + 2) % count];
    const c1 = [
      from[0] + (to[0] - before[0]) / 6,
      Math.min(floor, from[1] + (to[1] - before[1]) / 6),
    ];
    const c2 = [
      to[0] - (after[0] - from[0]) / 6,
      Math.min(floor, to[1] - (after[1] - from[1]) / 6),
    ];
    path += `C${number(c1[0])} ${number(c1[1])} ${number(c2[0])} ${number(c2[1])} ${number(to[0])} ${number(to[1])}`;
  }
  return path + "Z";
}
export function deformBlob(pose, seconds = 0) {
  const height = 1 - pose.squash * 0.32;
  const width = 1 / height;
  const floor = GROUND - pose.jump;
  const energy = pose.energy ?? 0;
  const softness = energy > 0 ? 0.75 + 0.6 * energy : 0;
  const points = FLOW_CAGE.map(({ x, y, normalX, normalY, phase, weight }) => {
    const upper = (GROUND - y) / (GROUND - 57);
    const shoulder =
      Math.exp(-(((y - 137) / 32) ** 2)) * Math.min(1, upper * 4);
    const side = Math.sign(x - CENTER);
    const flow =
      softness *
      weight *
      (1.8 * Math.sin(phase * 3 - seconds * 2.4) +
        Math.sin(phase * 5 + seconds * 1.45));
    return [
      CENTER +
        (x - CENTER) * width +
        pose.lean * 13 * upper +
        side * pose.reach * shoulder * 10 +
        normalX * flow,
      Math.min(
        floor,
        floor -
          (GROUND - y) * height +
          pose.headDrop * upper -
          pose.reach * shoulder * 5 +
          normalY * flow,
      ),
    ];
  });
  return {
    path: outlinePath(points, floor),
    points,
    floor,
    headX: pose.lean * 9,
    headY: (1 - height) * 87 + pose.headDrop * 0.72 - pose.jump,
    headAngle: pose.lean * 3,
    headphoneWidth: width,
    shadowWidth: 62 * width * (1 - Math.min(0.24, pose.jump / 145)),
    shadowOpacity: 0.1 + pose.squash * 0.055 - pose.jump * 0.0014,
  };
}
/** Damped follow-through for the face/gear, with bounded semi-implicit substeps. */
export function springStep(
  state,
  target,
  elapsed,
  stiffness = 180,
  damping = 23,
) {
  let remaining = clamp(elapsed, 0, 0.064);
  while (remaining > 0) {
    const dt = Math.min(remaining, 1 / 120);
    state.velocity +=
      ((target - state.value) * stiffness - state.velocity * damping) * dt;
    state.value += state.velocity * dt;
    remaining -= dt;
  }
  return state.value;
}
