import test from "node:test";
import assert from "node:assert/strict";
import { roundTiming } from "../../frontend/game/timing.mjs";
import { waveformLevels } from "../../frontend/audio/levels.mjs";
import { createLabAudio } from "../../frontend/audio/lab.mjs";

test("remaining arc and elapsed sound drawing share exact countdown boundaries", () => {
  for (const [now, remaining, elapsed, expired] of [
    [-100, 20000, 0, false],
    [0, 20000, 0, false],
    [8000, 12000, 8000, false],
    [20000, 0, 20000, true],
    [25000, 0, 20000, true],
  ]) {
    const timing = roundTiming({ startsAt: 0, deadline: 20000, now });
    assert.equal(timing.remaining, remaining);
    assert.equal(timing.elapsed, elapsed);
    assert.equal(timing.expired, expired);
    assert.equal(timing.remainingFraction + timing.progress, 1);
    assert.equal(timing.started, now >= 0);
  }
  for (const data of [
    {},
    { startsAt: 5, deadline: 5, now: 10 },
    { startsAt: 20, deadline: 10, now: 30 },
    { startsAt: 0, deadline: 20, now: NaN },
  ]) {
    const timing = roundTiming(data);
    assert.equal(timing.duration, 0);
    assert.equal(timing.remainingFraction, 0);
    assert.equal(timing.expired, false);
  }
});

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
