import test from "node:test";
import assert from "node:assert/strict";
import { sampleHeadphones } from "../../frontend/components/blob-headphones.mjs";

test("submission removes worn headphones with anticipation, lift, earcup spread and a final fade", () => {
  const worn = sampleHeadphones("listening", 100);
  const initial = sampleHeadphones("submitted", 0, { departing: true });
  assert.deepEqual(
    initial,
    worn,
    "the first submitted frame does not instantly hide the gear",
  );
  const loosen = sampleHeadphones("submitted", 0.12, { departing: true });
  const lift = sampleHeadphones("submitted", 0.36, { departing: true });
  const fade = sampleHeadphones("submitted", 0.7, { departing: true });
  assert.ok(
    loosen.spread > 0 && loosen.lift > 0,
    "earcups loosen before the lift",
  );
  assert.ok(lift.lift < -10 && lift.spread > loosen.spread);
  assert.equal(
    lift.opacity,
    1,
    "the lifted headphones remain visible before fading",
  );
  assert.ok(lift.angle < 0 && lift.scale > 1);
  assert.ok(fade.lift < lift.lift && fade.opacity > 0 && fade.opacity < 1);
  assert.equal(
    sampleHeadphones("submitted", 1, { departing: true }).opacity,
    0,
  );
  assert.equal(
    sampleHeadphones("submitted", 10, { departing: true }).opacity,
    0,
    "completed submissions never replay the departure",
  );
});
test("restored submissions and reduced motion show the final state without inventing a departure", () => {
  for (const age of [0, 0.2, 0.5, 10]) {
    assert.equal(sampleHeadphones("submitted", age).opacity, 0);
    assert.equal(
      sampleHeadphones("submitted", age, { departing: true, reduced: true })
        .opacity,
      0,
    );
    for (const mood of ["idle", "sad", "celebrating"])
      assert.equal(sampleHeadphones(mood, age, { departing: true }).opacity, 0);
    assert.equal(
      sampleHeadphones("listening", age, { reduced: true }).opacity,
      1,
    );
  }
});
test("the departure is continuous and bounded across its key poses", () => {
  let previous = sampleHeadphones("submitted", 0, { departing: true });
  for (let step = 1; step <= 85; step++) {
    const pose = sampleHeadphones("submitted", step / 100, { departing: true });
    assert.ok(Object.values(pose).every(Number.isFinite));
    assert.ok(pose.opacity >= 0 && pose.opacity <= 1);
    assert.ok(pose.spread >= 0 && pose.spread <= 12);
    assert.ok(
      Math.abs(pose.lift - previous.lift) < 2,
      "the departure has no frame-sized teleports",
    );
    assert.ok(Math.abs(pose.opacity - previous.opacity) < 0.06);
    previous = pose;
  }
});
