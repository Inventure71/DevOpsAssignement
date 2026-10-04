import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizedAppearance,
  normalizeLevels,
  waveformGeometry,
} from "../../frontend/components/waveform-drawing.mjs";

function verticalBars(path) {
  return [...path.matchAll(/M([\d.]+) ([\d.]+)V([\d.]+)/g)].map((match) => ({
    x: Number(match[1]),
    top: Number(match[2]),
    bottom: Number(match[3]),
  }));
}

test("waveforms render measured amplitude and preserve transients when fitting the viewport", () => {
  const geometry = waveformGeometry([0, 0.2, 0.1, 0.9, 0.3], 100, {
    barCount: 2,
  });
  assert.deepEqual(geometry.levels, [0, 0.2, 0.1, 0.9, 0.3]);
  assert.deepEqual(geometry.samples, [0.2, 0.9]);
  assert.equal(geometry.barCount, 2);
  const bars = verticalBars(geometry.paths[0].d);
  assert.equal(bars.length, 2);
  assert.ok(bars[1].bottom - bars[1].top > bars[0].bottom - bars[0].top);
  assert.deepEqual(
    bars.map(({ x }) => x),
    [25, 75],
  );
  assert.ok(
    bars.every(({ top, bottom }) => top >= 0 && bottom <= geometry.height),
  );
  assert.equal(geometry.paths[0].fill, false);
});

test("silence stays flat, and absent measurements produce no invented waveform", () => {
  const silence = waveformGeometry([0, 0, 0, 0], 300);
  assert.ok(
    verticalBars(silence.paths[0].d).every(({ top, bottom }) => top === bottom),
  );
  assert.deepEqual(silence.samples, [0, 0, 0, 0]);
  for (const value of [undefined, null, [], "not audio"]) {
    const absent = waveformGeometry(value, 300);
    assert.equal(absent.empty, true);
    assert.deepEqual(absent.paths, []);
  }
  const silentLine = waveformGeometry([0, 0, 0], 300, { mode: "line" });
  const coordinates = silentLine.paths[0].d
    .match(/[+-]?(?:\d+(?:\.\d+)?)/g)
    .map(Number);
  assert.ok(
    coordinates
      .filter((_, index) => index % 2)
      .every((y) => y === silentLine.height / 2),
  );
});

test("line mode draws a smooth, closed measured envelope", () => {
  const geometry = waveformGeometry([0, 0.25, 1, 0.5, 0], 500, {
    mode: "line",
    height: 60,
  });
  const path = geometry.paths[0];
  assert.equal(path.fill, true);
  assert.ok(path.d.includes("Q"));
  assert.ok(path.d.endsWith("Z"));
  assert.ok(!path.d.includes("NaN") && !path.d.includes("Infinity"));
  assert.equal(geometry.strokeWidth, 2.5);
  assert.equal(geometry.height, 60);
});

test("untrusted or malformed measurements and layout inputs yield finite, bounded geometry", () => {
  assert.deepEqual(normalizeLevels(new Float32Array([0, 0.5, 1])), [0, 0.5, 1]);
  assert.deepEqual(
    normalizeLevels([-1, 0.3, 4, NaN, Infinity, "0.7"]),
    [0, 0.3, 1, 0, 0, 0],
  );
  const config = normalizedAppearance({
    mode: "unknown",
    barCount: -30,
    height: Infinity,
    gap: 200,
    barWidth: 0,
    lineWidth: 99,
  });
  assert.deepEqual(
    {
      mode: config.mode,
      barCount: config.barCount,
      height: config.height,
      gap: config.gap,
      barWidth: config.barWidth,
      lineWidth: config.lineWidth,
    },
    {
      mode: "bars",
      barCount: 1,
      height: 46,
      gap: 24,
      barWidth: 1,
      lineWidth: 12,
    },
  );
  for (const width of [0, -8, NaN, Infinity, Number.MAX_VALUE, 0.1, 1, 300]) {
    for (const mode of ["bars", "line"]) {
      const geometry = waveformGeometry([NaN, -1, 1, Infinity, 0.3], width, {
        mode,
      });
      assert.ok(geometry.width >= 1 && geometry.barCount >= 1);
      assert.ok(geometry.strokeWidth <= geometry.width);
      assert.ok(!/NaN|Infinity/.test(geometry.paths[0].d));
    }
  }
});

test("custom drawings receive immutable original measurements and layout without truncated audio", () => {
  let received;
  const geometry = waveformGeometry(
    [0.1, 0.4, 0.9, 0.2],
    120,
    { barCount: 2, height: 48 },
    (context) => {
      received = context;
      assert.ok(
        Object.isFrozen(context) &&
          Object.isFrozen(context.levels) &&
          Object.isFrozen(context.samples),
      );
      return [
        { d: `M0 24L${context.width} 24`, fill: false },
        { d: "M20 20Q40 0 60 20", fill: true },
      ];
    },
  );
  assert.deepEqual(received.levels, [0.1, 0.4, 0.9, 0.2]);
  assert.deepEqual(received.samples, [0.4, 0.9]);
  assert.equal(received.barCount, 2);
  assert.equal(received.strokeWidth, 5);
  assert.equal(geometry.paths.length, 2);
  assert.deepEqual(geometry.paths[0], { d: "M0 24L120 24", fill: false });
  let called = false;
  waveformGeometry([], 100, {}, () => {
    called = true;
    return [];
  });
  assert.equal(
    called,
    false,
    "the absence of audio never invokes a decorative drawing callback",
  );
});

test("custom paths cannot inject markup or nonfinite coordinates into the SVG", () => {
  for (const result of [
    null,
    "<path/>",
    Array.from({ length: 9 }, () => ({ d: "M0 0" })),
    [{ d: "MNaN 0" }],
    [{ d: "M0 Infinity" }],
    [{ d: "M1e999 0" }],
    [{ d: '<svg onload="alert(1)">' }],
    [{ d: "M0 0", fill: false }, {}],
  ])
    assert.throws(
      () => waveformGeometry([0.5], 100, {}, () => result),
      TypeError,
    );
  assert.deepEqual(
    waveformGeometry([0.5], 100, {}, () => [{ d: "M1e-3 2L3 4" }]).paths,
    [{ d: "M1e-3 2L3 4", fill: false }],
  );
});
