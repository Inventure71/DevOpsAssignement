import test from "node:test";
import assert from "node:assert/strict";
import {
  sampleBlobMotion,
  deformBlob,
  springStep,
} from "../../frontend/components/blob-rig.mjs";
import { createBlobMotionHub } from "../../frontend/components/blob-motion.mjs";
import {
  BLOB_COLORS,
  getBlobColor,
} from "../../frontend/components/blob-palette.mjs";

function bounds(points) {
  const xs = points.map(([x]) => x),
    ys = points.map(([, y]) => y);
  return {
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
    bottom: Math.max(...ys),
  };
}
function area(points) {
  return (
    Math.abs(
      points.reduce((sum, [x, y], index) => {
        const next = points[(index + 1) % points.length];
        return sum + x * next[1] - next[0] * y;
      }, 0),
    ) / 2
  );
}
function frameHarness() {
  const pending = new Map();
  let nextId = 0,
    requested = 0,
    cancelled = 0;
  const hub = createBlobMotionHub({
    requestFrame(callback) {
      requested++;
      pending.set(++nextId, callback);
      return nextId;
    },
    cancelFrame(id) {
      cancelled++;
      pending.delete(id);
    },
  });
  return {
    hub,
    pending,
    counts: () => ({ requested, cancelled }),
    advance(time) {
      assert.equal(
        pending.size,
        1,
        "a visible group uses exactly one scheduled frame",
      );
      const [id, callback] = pending.entries().next().value;
      pending.delete(id);
      callback(time);
    },
  };
}

test("motion clips keep the outline and Bezier controls above their current ground plane", () => {
  const neutral = deformBlob(sampleBlobMotion("idle", 0, { reduced: true }));
  for (const mood of ["idle", "listening", "submitted", "celebrating", "sad"]) {
    for (let index = 0; index <= 144; index++) {
      const seconds = index / 20;
      const pose = sampleBlobMotion(mood, seconds, { moodAge: seconds });
      const rig = deformBlob(pose, seconds);
      assert.ok(
        rig.path.startsWith("M") && rig.path.endsWith("Z"),
        "the body remains a closed outline",
      );
      assert.ok(
        rig.points.every((point) => point.every(Number.isFinite)),
        `${mood}: finite cage points`,
      );
      assert.ok(
        rig.points.every(([, y]) => y <= rig.floor + 1e-8),
        `${mood}: cage does not sink below its feet`,
      );
      const coordinates = [...rig.path.matchAll(/-?\d+(?:\.\d+)?/g)].map(
        (match) => Number(match[0]),
      );
      assert.ok(coordinates.every(Number.isFinite));
      const controlYs = coordinates.filter(
        (_, coordinate) => coordinate % 2 === 1,
      );
      // SVG coordinates are rounded to two decimals; control tangents must not
      // pull the cubic silhouette through the ground between cage points.
      assert.ok(
        controlYs.every((y) => y <= rig.floor + 0.011),
        `${mood}: cubic controls stay above the ground`,
      );
      assert.ok(
        Math.abs(bounds(rig.points).bottom - rig.floor) < 0.03,
        `${mood}: feet follow the current ground plane`,
      );
      if (pose.jump === 0)
        assert.equal(
          rig.floor,
          neutral.floor,
          `${mood}: nonjumping clips remain grounded`,
        );
    }
  }
});

test("celebration visibly anticipates, jumps, lands, then settles back on the floor", () => {
  const neutral = deformBlob(sampleBlobMotion("idle", 0, { reduced: true }));
  const anticipation = deformBlob(sampleBlobMotion("celebrating", 0.34), 0.34);
  const airborne = deformBlob(sampleBlobMotion("celebrating", 0.96), 0.96);
  const landing = deformBlob(sampleBlobMotion("celebrating", 1.42), 1.42);
  const resting = deformBlob(sampleBlobMotion("celebrating", 2.4), 2.4);
  assert.equal(anticipation.floor, neutral.floor);
  assert.ok(
    bounds(anticipation.points).height < bounds(neutral.points).height,
    "the body crouches before lift-off",
  );
  assert.ok(
    bounds(anticipation.points).width > bounds(neutral.points).width,
    "anticipation pushes the body outward",
  );
  assert.ok(
    airborne.floor < neutral.floor - 20,
    "the feet lift for a deliberate jump",
  );
  assert.ok(
    airborne.shadowOpacity < neutral.shadowOpacity,
    "the floor shadow softens while airborne",
  );
  assert.ok(
    Math.abs(landing.floor - neutral.floor) < 0.01,
    "the landing reconnects to the floor within a subpixel",
  );
  assert.ok(
    bounds(landing.points).height < bounds(neutral.points).height,
    "landing absorbs the impact",
  );
  assert.equal(resting.floor, neutral.floor);
  assert.ok(
    Math.abs(bounds(resting.points).height - bounds(neutral.points).height) < 1,
    "the loop returns to its resting body",
  );
});

test("squash and stretch compensate width while preserving body area and planted feet", () => {
  const neutral = {
    squash: 0,
    lean: 0,
    headDrop: 0,
    jump: 0,
    reach: 0,
    energy: 0,
  };
  const resting = deformBlob(neutral);
  const compressed = deformBlob({ ...neutral, squash: 0.6 });
  const stretched = deformBlob({ ...neutral, squash: -0.25 });
  assert.ok(bounds(compressed.points).height < bounds(resting.points).height);
  assert.ok(bounds(compressed.points).width > bounds(resting.points).width);
  assert.ok(bounds(stretched.points).height > bounds(resting.points).height);
  assert.ok(bounds(stretched.points).width < bounds(resting.points).width);
  for (const rig of [compressed, stretched]) {
    assert.ok(
      Math.abs(area(rig.points) / area(resting.points) - 1) < 1e-10,
      "affine squash keeps body volume rather than shrinking the sprite",
    );
    assert.equal(bounds(rig.points).bottom, bounds(resting.points).bottom);
    assert.ok(rig.headphoneWidth > 0 && rig.shadowWidth > 0);
  }
});

test("listening bends the upper body while the feet remain planted", () => {
  const left = deformBlob(sampleBlobMotion("listening", 0), 0);
  const right = deformBlob(sampleBlobMotion("listening", 0.7), 0.7);
  const head = left.points.reduce(
    (best, point, index, points) => (point[1] < points[best][1] ? index : best),
    0,
  );
  const foot = left.points.reduce(
    (best, point, index, points) => (point[1] > points[best][1] ? index : best),
    0,
  );
  assert.notEqual(
    left.path,
    right.path,
    "the silhouette itself changes, rather than translating a rigid sprite",
  );
  assert.ok(
    Math.abs(left.points[head][0] - right.points[head][0]) > 10,
    "head and shoulders follow the listening sway",
  );
  assert.deepEqual(
    left.points[foot],
    right.points[foot],
    "the cage pivots from a stationary foot",
  );
  assert.ok(
    left.headAngle * right.headAngle < 0,
    "the face follows both directions of the sway",
  );
  assert.equal(left.floor, right.floor);
});

test("reduced motion returns the same quiet pose regardless of clips or interaction", () => {
  const expected = sampleBlobMotion("idle", 0, { reduced: true });
  for (const mood of ["idle", "listening", "submitted", "celebrating"]) {
    for (const seconds of [0, 0.4, 3, 100]) {
      const pose = sampleBlobMotion(mood, seconds, {
        reduced: true,
        moodAge: 0.2,
        reactionAge: 0.1,
        reaction: "greet",
      });
      assert.deepEqual(pose, expected);
      assert.deepEqual(
        deformBlob(pose, seconds).points,
        deformBlob(expected, 0).points,
        "reduced motion also suppresses the cage ripple",
      );
    }
  }
  assert.equal(expected.blink, 0);
  assert.equal(expected.energy, 0);
  assert.equal(expected.jump, 0);
});

test("follow-through springs converge without exploding after a long frame stall", () => {
  const spring = { value: 0, velocity: 0 };
  for (let frame = 0; frame < 180; frame++) {
    springStep(spring, 10, 1 / 30);
    assert.ok(
      Number.isFinite(spring.value) && Number.isFinite(spring.velocity),
    );
    assert.ok(
      spring.value >= 0 && spring.value < 11,
      "damped following stays near the target",
    );
  }
  assert.ok(Math.abs(spring.value - 10) < 0.001);
  assert.ok(Math.abs(spring.velocity) < 0.001);
  const stalled = { value: 4, velocity: 10 },
    normal = { ...stalled };
  springStep(stalled, 10, 30);
  springStep(normal, 10, 0.064);
  assert.deepEqual(
    stalled,
    normal,
    "a thirty-second background stall advances only a bounded step",
  );
  const before = { ...stalled };
  springStep(stalled, 10, -1);
  assert.deepEqual(
    stalled,
    before,
    "clock reversal cannot integrate backwards",
  );
});

test("moving blobs share one throttled loop and releasing the last member cancels it", () => {
  const frames = frameHarness();
  const a = [],
    b = [];
  const removeA = frames.hub.add((time, elapsed) => a.push({ time, elapsed }));
  const removeB = frames.hub.add((time, elapsed) => b.push({ time, elapsed }));
  assert.equal(frames.pending.size, 1);
  assert.equal(
    frames.counts().requested,
    1,
    "adding a second blob does not spawn another loop",
  );
  frames.advance(100);
  frames.advance(110);
  assert.equal(a.length, 1, "an early frame does not repaint the rig");
  frames.advance(140);
  frames.advance(10000);
  assert.equal(a.length, 3);
  assert.equal(b.length, 3);
  assert.ok(
    a.every(({ elapsed }) => elapsed > 0 && elapsed <= 0.064),
    "members receive bounded simulation deltas",
  );
  removeA();
  frames.advance(10040);
  assert.equal(
    a.length,
    3,
    "removed components receive no further animation calls",
  );
  assert.equal(b.length, 4);
  removeB();
  assert.equal(frames.pending.size, 0);
  assert.deepEqual(frames.hub.stats, { members: 0, running: false, frames: 4 });
  assert.equal(frames.counts().cancelled, 1);
});

test("visibility disables all animation work and resume restarts with a fresh elapsed time", () => {
  const frames = frameHarness();
  const calls = [];
  const remove = frames.hub.add((time, elapsed) =>
    calls.push({ time, elapsed }),
  );
  frames.advance(100);
  const queued = frames.pending.values().next().value;
  frames.hub.setEnabled(false);
  assert.equal(frames.pending.size, 0);
  assert.equal(frames.hub.stats.running, false);
  queued(5000);
  assert.equal(
    calls.length,
    1,
    "a stale callback does no work while visibility is disabled",
  );
  assert.equal(frames.pending.size, 0);
  frames.hub.setEnabled(true);
  frames.hub.setEnabled(true);
  assert.equal(
    frames.pending.size,
    1,
    "repeated resume notifications keep a single loop",
  );
  frames.advance(20000);
  assert.equal(calls.length, 2);
  assert.ok(
    calls[1].elapsed < 0.05,
    "resume does not integrate all time spent hidden",
  );
  frames.hub.setEnabled(false);
  remove();
  assert.equal(frames.hub.stats.members, 0);
  assert.equal(frames.pending.size, 0);
});

test("color presets are shared immutable identities with a usable fallback", () => {
  assert.ok(BLOB_COLORS.length >= 5);
  assert.equal(
    new Set(BLOB_COLORS.map((color) => color.id)).size,
    BLOB_COLORS.length,
  );
  assert.ok(Object.isFrozen(BLOB_COLORS));
  for (const color of BLOB_COLORS) {
    assert.equal(
      getBlobColor(color.id),
      color,
      "persisted color IDs resolve to their shared preset",
    );
    assert.ok(Object.isFrozen(color));
    assert.ok(color.label.trim());
    for (const key of ["main", "light", "dark", "accent"])
      assert.match(color[key], /^#[a-f\d]{6}$/i);
  }
  assert.equal(getBlobColor("unknown-color"), BLOB_COLORS[0]);
  assert.equal(getBlobColor(null), BLOB_COLORS[0]);
});

test("sadness slumps the body gently and keeps a still expression when motion is reduced", () => {
  const resting = deformBlob(sampleBlobMotion("idle", 0, { reduced: true }));
  const poses = [0, 0.4, 2, 8].map((t) => sampleBlobMotion("sad", t));
  for (const pose of poses) {
    const rig = deformBlob(pose);
    assert.equal(rig.floor, resting.floor);
    assert.ok(bounds(rig.points).height < bounds(resting.points).height);
    assert.ok(rig.headY > 4, "the head droops with the body");
    assert.equal(pose.jump, 0, "disappointment never bounces off the floor");
  }
  const quiet = sampleBlobMotion("sad", 0, { reduced: true });
  assert.deepEqual(
    sampleBlobMotion("sad", 20, { reduced: true, reactionAge: 0.2 }),
    quiet,
  );
  assert.ok(
    quiet.headDrop > 0,
    "reduced motion retains the semantic sad posture",
  );
  assert.equal(quiet.energy, 0);
});

test("entering celebration starts its anticipation independently of the shared page clock", () => {
  const entered = sampleBlobMotion("celebrating", 123, { moodAge: 0 });
  const crouched = sampleBlobMotion("celebrating", 124, { moodAge: 0.34 });
  assert.equal(entered.jump, 0);
  assert.equal(crouched.jump, 0);
  assert.ok(crouched.squash > entered.squash);
});

test("even a held idle pose has a fluid contour and independently moving lobes with planted feet", () => {
  const pose = sampleBlobMotion("idle", 0);
  const first = deformBlob(pose, 0),
    later = deformBlob(pose, 0.65);
  assert.notEqual(
    first.path,
    later.path,
    "outline motion continues without changing the body's rig pose",
  );
  const foot = first.points.findIndex(([, y]) => y === first.floor);
  assert.ok(foot >= 0);
  assert.deepEqual(first.points[foot], later.points[foot]);
  assert.equal(first.headX, later.headX);
  assert.equal(
    first.headY,
    later.headY,
    "the face does not drift along with the surface ripples",
  );
  assert.ok(
    first.points.some(
      ([x, y], index) =>
        Math.hypot(x - later.points[index][0], y - later.points[index][1]) >
        1.5,
    ),
  );
  assert.ok(
    first.points.some(
      ([, y], index) => Math.abs(y - later.points[index][1]) > 0.5,
    ),
    "surface deformation changes height as well as width",
  );
  const chord = (points, index) =>
    Math.hypot(
      points[index][0] - points[(index + 1) % points.length][0],
      points[index][1] - points[(index + 1) % points.length][1],
    );
  assert.ok(
    first.points.some(
      (_, index) =>
        Math.abs(chord(first.points, index) - chord(later.points, index)) > 0.5,
    ),
    "local distances change instead of translating a rigid border",
  );
});

test("surface flow stays smooth, bounded and approximately volume preserving over repeated cycles", () => {
  const pose = { ...sampleBlobMotion("idle", 0), energy: 1 };
  const resting = deformBlob({ ...pose, energy: 0 });
  let previous = deformBlob(pose, 0).points;
  for (let frame = 1; frame <= 600; frame++) {
    const rig = deformBlob(pose, frame / 60);
    assert.ok(
      Math.abs(area(rig.points) / area(resting.points) - 1) < 0.08,
      "the blob does not inflate/deflate excessively with each ripple",
    );
    rig.points.forEach(([x, y], index) => {
      assert.ok(x > 0 && x < 240 && y > 0 && y <= rig.floor);
      assert.ok(
        Math.hypot(x - previous[index][0], y - previous[index][1]) < 0.8,
        "the material has no frame-sized jumps",
      );
    });
    previous = rig.points;
  }
});
