import { roundTiming } from "../game/timing.mjs";

const DEFAULTS = Object.freeze({
  mode: "bars",
  barCount: 64,
  height: 46,
  gap: 4,
  barWidth: 5,
  lineWidth: 2.5,
  playedColor: "#151515",
  unplayedColor: "#d7d4d9",
});
const finite = (value, fallback) => (Number.isFinite(value) ? value : fallback);
const clamp = (value, minimum, maximum) =>
  Math.min(maximum, Math.max(minimum, value));
const number = (value) => Number(value.toFixed(3));

export function normalizedAppearance(value = {}) {
  return {
    mode: value.mode === "line" ? "line" : "bars",
    barCount: Math.round(
      clamp(finite(value.barCount, DEFAULTS.barCount), 1, 512),
    ),
    height: clamp(finite(value.height, DEFAULTS.height), 16, 200),
    gap: clamp(finite(value.gap, DEFAULTS.gap), 0, 24),
    barWidth: clamp(finite(value.barWidth, DEFAULTS.barWidth), 1, 16),
    lineWidth: clamp(finite(value.lineWidth, DEFAULTS.lineWidth), 1, 12),
    playedColor:
      typeof value.playedColor === "string"
        ? value.playedColor
        : DEFAULTS.playedColor,
    unplayedColor:
      typeof value.unplayedColor === "string"
        ? value.unplayedColor
        : DEFAULTS.unplayedColor,
  };
}

// Invalid measurements become silence, never an invented decorative waveform.
export function normalizeLevels(levels) {
  if (!Array.isArray(levels) && !ArrayBuffer.isView(levels)) return [];
  return Array.from(levels, (level) => clamp(finite(level, 0), 0, 1));
}

export function waveformProgress({ startsAt, deadline }, now) {
  const { duration, elapsed, progress } = roundTiming({
    startsAt,
    deadline,
    now,
  });
  return { duration, elapsed, progress };
}

function reduceLevels(levels, count) {
  // Keep measured transients when several samples occupy one screen column.
  return Array.from({ length: count }, (_, index) => {
    const start = Math.floor((index * levels.length) / count);
    const end = Math.max(
      start + 1,
      Math.floor(((index + 1) * levels.length) / count),
    );
    let peak = 0;
    for (let sample = start; sample < end; sample++)
      peak = Math.max(peak, levels[sample]);
    return peak;
  });
}

function smooth(points, move = true) {
  let path = `${move ? "M" : "L"}${points[0].join(" ")}`;
  for (let index = 1; index < points.length; index++) {
    const previous = points[index - 1];
    const next = points[index];
    path += `Q${previous.join(" ")} ${number((previous[0] + next[0]) / 2)} ${number((previous[1] + next[1]) / 2)}`;
  }
  const last = points.at(-1);
  return `${path}L${last.join(" ")}`;
}

function builtInDrawing(context) {
  const { samples: levels, width, height, mode, strokeWidth } = context;
  const center = height / 2;
  const amplitude = (height - strokeWidth) / 2;
  const spacing = width / levels.length;
  const points = levels.map((level, index) => [
    number(spacing * (index + 0.5)),
    number(center - amplitude * level),
  ]);
  if (mode === "bars") {
    return [
      {
        d: points
          .map(([x, top]) => `M${x} ${top}V${number(height - top)}`)
          .join(""),
        fill: false,
      },
    ];
  }
  // The two curves trace the measured amplitude envelope around the centerline.
  const top = [[0, points[0][1]], ...points, [width, points.at(-1)[1]]];
  const bottom = top.map(([x, y]) => [x, number(height - y)]).reverse();
  return [{ d: `${smooth(top)}${smooth(bottom, false)}Z`, fill: true }];
}

// Custom draw(context) returns up to eight { d, fill } paths. It receives all
// normalized `levels`; `samples` are peak-preserving display buckets. Paths are
// applied with SVG attributes, never inserted as markup. Colors and time are
// presentation concerns, so a drawing is independent of playback position.
export function waveformGeometry(levels, width, appearance = {}, draw = null) {
  const config = normalizedAppearance(appearance);
  const measured = normalizeLevels(levels);
  const layoutWidth = clamp(finite(width, 1), 1, 100000);
  const strokeWidth = Math.min(
    layoutWidth,
    config.mode === "bars" ? config.barWidth : config.lineWidth,
  );
  const fit = Math.max(1, Math.floor(layoutWidth / (strokeWidth + config.gap)));
  const count = Math.min(measured.length, config.barCount, fit);
  const reduced = count ? reduceLevels(measured, count) : [];
  const context = Object.freeze({
    levels: Object.freeze(measured),
    samples: Object.freeze(reduced),
    width: layoutWidth,
    height: config.height,
    mode: config.mode,
    gap: config.gap,
    barCount: count,
    strokeWidth,
  });
  let paths = [];
  if (count) {
    const result =
      typeof draw === "function" ? draw(context) : builtInDrawing(context);
    if (!Array.isArray(result) || result.length > 8)
      throw new TypeError(
        "A waveform drawing must return up to eight { d, fill } paths.",
      );
    paths = result.map((path) => {
      if (
        !path ||
        typeof path.d !== "string" ||
        path.d.length > 200000 ||
        !/^[MmZzLlHhVvCcSsQqTtAaEe\d\s,.\-+]*$/.test(path.d) ||
        !(
          path.d.match(/[+-]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][+-]?\d+)?/g) || []
        ).every((coordinate) => Number.isFinite(Number(coordinate)))
      )
        throw new TypeError(
          "Waveform paths must contain finite SVG path coordinates.",
        );
      return { d: path.d, fill: Boolean(path.fill) };
    });
  }
  return { ...context, paths, empty: !count };
}
