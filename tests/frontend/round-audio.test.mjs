import test from "node:test";
import assert from "node:assert/strict";
import { roundTiming } from "../../frontend/game/timing.mjs";
import { waveformProgress } from "../../frontend/components/waveform-drawing.mjs";
import { waveformLevels } from "../../frontend/audio/levels.mjs";
import { createLabAudio } from "../../frontend/audio/lab.mjs";

const invalidTiming = {
  duration: 0, elapsed: 0, progress: 0, remaining: 0,
  remainingFraction: 0, started: false, expired: false,
};
for (const [name, data, expected] of [
  ["before start", { startsAt: 0, deadline: 20000, now: -100 },
    { duration: 20000, elapsed: 0, progress: 0, remaining: 20000, remainingFraction: 1, started: false, expired: false }],
  ["exact start at zero", { startsAt: 0, deadline: 20000, now: 0 },
    { duration: 20000, elapsed: 0, progress: 0, remaining: 20000, remainingFraction: 1, started: true, expired: false }],
  ["during the round", { startsAt: 1000, deadline: 21000, now: 9000 },
    { duration: 20000, elapsed: 8000, progress: 0.4, remaining: 12000, remainingFraction: 0.6, started: true, expired: false }],
  ["short round midpoint", { startsAt: 0, deadline: 1000, now: 500 },
    { duration: 1000, elapsed: 500, progress: 0.5, remaining: 500, remainingFraction: 0.5, started: true, expired: false }],
  ["exact deadline", { startsAt: 0, deadline: 20000, now: 20000 },
    { duration: 20000, elapsed: 20000, progress: 1, remaining: 0, remainingFraction: 0, started: true, expired: true }],
  ["after deadline", { startsAt: 0, deadline: 20000, now: 25000 },
    { duration: 20000, elapsed: 20000, progress: 1, remaining: 0, remainingFraction: 0, started: true, expired: true }],
  ["missing timestamps", {}, invalidTiming],
  ["empty window", { startsAt: 5, deadline: 5, now: 10 }, invalidTiming],
  ["reversed window", { startsAt: 20, deadline: 10, now: 30 }, invalidTiming],
  ["invalid clock", { startsAt: 0, deadline: 20, now: NaN }, invalidTiming],
  ["invalid start", { startsAt: NaN, deadline: 200, now: 100 }, invalidTiming],
]) {
  test(`countdown and waveform clocks agree: ${name}`, () => {
    assert.deepEqual(roundTiming(data), expected);
    const { duration, elapsed, progress } = expected;
    assert.deepEqual(waveformProgress(data, data.now), { duration, elapsed, progress });
  });
}

test("measured audio draws only the played window and hears either stereo channel", () => {
  const left = new Float32Array(3000);
  const right = new Float32Array(3000);
  right.fill(0.25, 1000, 2000);
  left.fill(1, 2000); // Loud material beyond the 20-second answer window.
  const buffer = {
    duration: 30,
    numberOfChannels: 2,
    getChannelData: (channel) => (channel ? right : left),
  };
  const levels = waveformLevels(buffer, 48, 20);
  assert.deepEqual(levels.slice(0, 24), Array(24).fill(0));
  assert.deepEqual(levels.slice(24), Array(24).fill(1));
  assert.deepEqual(waveformLevels(buffer, 48, 10), Array(48).fill(0));
  assert.deepEqual(waveformLevels(buffer, 48, 0), Array(48).fill(0));
  const silence = { duration: 30, numberOfChannels: 1, getChannelData: () => new Float32Array(3000) };
  assert.deepEqual(waveformLevels(silence), Array(48).fill(0));
});

test("short clips leave silence on the remainder of the round's audio axis", () => {
  const buffer = {
    duration: 10,
    getChannelData: () => new Float32Array(1000).fill(0.5),
  };
  assert.deepEqual(waveformLevels(buffer, 48, 20), [
    ...Array(24).fill(1),
    ...Array(24).fill(0),
  ]);
});

function session({
  deferDecode = false,
  fetchFails = false,
  resumeFails = false,
} = {}) {
  const sources = [],
    changes = [];
  let fetches = 0,
    resumes = 0,
    closed = 0,
    release;
  const decoded = {
    duration: 30,
    numberOfChannels: 1,
    getChannelData: () => new Float32Array(3000).fill(0.3),
  };
  const deferred = deferDecode
    ? new Promise((resolve) => {
        release = () => resolve(decoded);
      })
    : decoded;
  class Context {
    currentTime = 4;
    destination = {};
    resume() {
      resumes++;
      return resumeFails
        ? Promise.reject(new Error("Permission denied"))
        : Promise.resolve();
    }
    decodeAudioData() {
      return Promise.resolve(deferred);
    }
    close() {
      closed++;
      return Promise.resolve();
    }
    createBufferSource() {
      const source = {
        starts: [],
        stops: [],
        disconnected: false,
        connect() {},
        start(time) {
          this.starts.push(time);
        },
        stop(time) {
          this.stops.push(time);
        },
        disconnect() {
          this.disconnected = true;
        },
      };
      sources.push(source);
      return source;
    }
  }
  const audio = createLabAudio({
    url: "/test.mp3",
    onChange: (change) => changes.push(change),
    environment: {
      AudioContext: Context,
      AbortController,
      setTimeout,
      clearTimeout,
      Date: { now: () => 1000 },
      fetch: async () => {
        fetches++;
        return { ok: !fetchFails, arrayBuffer: async () => new ArrayBuffer(1) };
      },
    },
  });
  return {
    audio,
    sources,
    changes,
    release: () => release(),
    counts: () => ({ fetches, resumes, closed }),
  };
}

test("lab clip is decoded once, drawn from measured samples and scheduled to the common countdown", async (t) => {
  const s = session();
  t.after(() => s.audio.close());
  await s.audio.load();
  assert.deepEqual(s.changes.at(-1).levels, Array(64).fill(1));
  const timing = await s.audio.play();
  assert.deepEqual(timing, { startsAt: 4000, deadline: 24000 });
  assert.deepEqual(s.sources[0].starts, [7]);
  assert.deepEqual(s.sources[0].stops, [27]);
  assert.equal(s.changes.at(-1).playbackState, "playing");
  s.sources[0].onended();
  assert.equal(s.changes.at(-1).playbackState, "ended");
  await s.audio.play();
  assert.equal(s.counts().fetches, 1);
  assert.equal(s.counts().resumes, 2);
  s.audio.stop();
  assert.equal(s.sources[1].disconnected, true);
  assert.equal(s.sources[1].onended, null);
});

test("leaving during decode cannot start late audio and close is idempotent", async () => {
  const s = session({ deferDecode: true });
  const pending = s.audio.play();
  s.audio.stop();
  s.release();
  assert.equal(await pending, null);
  assert.deepEqual(s.sources, []);
  s.audio.close();
  s.audio.close();
  assert.equal(s.counts().closed, 1);
  await assert.rejects(s.audio.load(), /closed/);
});

test("unavailable audio and denied playback expose recoverable errors without starting sound", async () => {
  for (const options of [{ fetchFails: true }, { resumeFails: true }]) {
    const s = session(options);
    assert.equal(await s.audio.play(), null);
    assert.equal(s.changes.at(-1).playbackState, "error");
    assert.ok(s.changes.at(-1).error);
    assert.deepEqual(s.sources, []);
    s.audio.close();
  }
});
