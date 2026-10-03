import test from "node:test";
import assert from "node:assert/strict";
import { createAudioController } from "../../frontend/audio/host.mjs";
import { createModel } from "../../frontend/application/state.mjs";

async function settleUntil(predicate, description) {
  for (let attempt = 0; attempt < 40; attempt++) {
    if (predicate()) {
      // Finish the enclosing preload worker and its allSettled continuation.
      await new Promise(setImmediate);
      return;
    }
    await new Promise(setImmediate);
  }
  assert.fail(`Did not reach ${description}`);
}

function audioSession({ failFirstManifest = false } = {}) {
  const clock = { now: 0 };
  const state = {
    me: { id: "host", is_host: true },
    settings: { answer_seconds: 20 },
    game: {
      id: "game",
      status: "preparing",
      phase: "setup",
      round: {
        id: "round",
        readiness_generation: 3,
        audio_candidate_id: "one",
        starts_at_ms: 1000,
        deadline_at_ms: 21000,
      },
    },
  };
  const requests = [],
    sources = [],
    notices = [];
  let fetches = 0,
    decodes = 0;
  const samples = new Float32Array(4800);
  samples.fill(0.25, 2400);
  class Context {
    state = "running";
    sampleRate = 48000;
    destination = {};
    currentTime = 10;
    async resume() {}
    createBuffer() {
      return {};
    }
    createBufferSource() {
      const source = {
        starts: [],
        stops: [],
        connect() {},
        start(...args) {
          this.starts.push(args);
        },
        stop(...args) {
          this.stops.push(args);
        },
      };
      sources.push(source);
      return source;
    }
    async decodeAudioData() {
      decodes++;
      return { duration: 30, getChannelData: () => samples };
    }
  }
  const api = async (url, options = {}) => {
    requests.push({ url, ...options });
    if (url.endsWith("/audio-controller")) return { lease_id: "lease" };
    if (url.endsWith("/audio")) {
      const count = requests.filter((request) =>
        request.url.endsWith("/audio"),
      ).length;
      if (failFirstManifest && count === 1)
        throw new Error("Temporary network failure");
      return {
        candidates: [
          { candidate_id: "one", preview_url: "/shared-clip" },
          { candidate_id: "two", preview_url: "/shared-clip" },
        ],
      };
    }
    return { accepted: true };
  };
  const environment = {
    AudioContext: Context,
    AbortController,
    setTimeout,
    clearTimeout,
    async fetch(url, options) {
      assert.equal(url, "/shared-clip");
      assert.equal(options.credentials, "same-origin");
      fetches++;
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) };
    },
  };
  const readySent = new Set();
  const audio = createAudioController(
    {
      api,
      path: (suffix) => suffix,
      roundPath: (suffix) => `/rounds/round${suffix}`,
    },
    () => state,
    () => clock.now,
    "tab",
    readySent,
    () => {},
    (message) => notices.push(message),
    environment,
  );
  return {
    audio,
    state,
    clock,
    sources,
    notices,
    readySent,
    requestsFor: (suffix) =>
      requests.filter((request) => request.url.endsWith(suffix)),
    counts: () => ({ fetches, decodes }),
  };
}

test("host retries a failed manifest after backoff, checks clips, then acknowledges readiness once", async (t) => {
  const session = audioSession({ failFirstManifest: true });
  t.after(() => session.audio.reset());
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.notices.length === 1,
    "failed preparation notice",
  );
  assert.match(session.notices[0], /try again automatically/);
  assert.doesNotMatch(session.notices[0], /Temporary network failure/);
  assert.equal(session.requestsFor("/audio").length, 1);

  session.clock.now = 1999;
  await session.audio.synchronize();
  assert.equal(
    session.requestsFor("/audio").length,
    1,
    "polling respects the retry backoff",
  );
  session.clock.now = 2000;
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "recovered clip checks",
  );

  assert.equal(session.requestsFor("/audio").length, 2);
  assert.equal(
    session.requestsFor("/audio")[1].headers["X-Audio-Lease"],
    "lease",
  );
  assert.deepEqual(
    session.counts(),
    { fetches: 1, decodes: 1 },
    "shared clip URLs decode once",
  );
  for (const { body } of session.requestsFor("/preload-check")) {
    assert.equal(body.ok, true);
    assert.equal(body.lease_id, "lease");
    assert.equal(body.waveform.length, 48);
    assert.equal(
      body.waveform[0],
      0,
      "waveform preserves the silent beginning",
    );
    assert.equal(body.waveform[47], 1, "waveform reflects decoded samples");
    assert.ok(body.request_id);
  }
  assert.deepEqual(
    session
      .requestsFor("/preload-check")
      .map((request) => request.body.candidate_id)
      .sort(),
    ["one", "two"],
  );

  session.state.game.phase = "ready";
  await session.audio.synchronize();
  await session.audio.synchronize();
  assert.equal(session.requestsFor("/ready").length, 1);
  assert.deepEqual(session.requestsFor("/ready")[0].body, {
    readiness_generation: 3,
    lease_id: "lease",
  });
  assert.ok(session.readySent.has("round:3"));
});

test("suspending scheduled host audio reports one interrupted attempt without replaying it", async (t) => {
  const session = audioSession();
  t.after(() => session.audio.reset());
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "initial preparation",
  );
  session.state.game.status = "playing";
  session.state.game.phase = "countdown";
  await session.audio.synchronize();
  assert.equal(
    session.sources.length,
    2,
    "one unlock source and one song source",
  );
  const song = session.sources[1];
  assert.deepEqual(
    song.starts,
    [[11]],
    "the song starts at the common countdown deadline",
  );
  assert.deepEqual(
    song.stops,
    [[31]],
    "the song stops after the configured twenty seconds",
  );

  session.clock.now = 1500;
  session.state.game.phase = "answering";
  session.audio.suspend();
  assert.deepEqual(
    song.stops,
    [[31], []],
    "page suspension stops shared audio immediately",
  );
  await session.audio.synchronize();
  await session.audio.synchronize();
  const failures = session.requestsFor("/audio-failure");
  assert.equal(failures.length, 1);
  assert.equal(failures[0].body.lease_id, "lease");
  assert.equal(failures[0].body.readiness_generation, 3);
  assert.match(failures[0].body.reason, /Host left the page.*interrupted/);
  assert.equal(
    session.sources.length,
    2,
    "returning to the page does not create a replacement playback source",
  );
  assert.deepEqual(song.starts, [[11]]);
  assert.deepEqual(session.notices, []);
});

test("explicit URL room references restore separate tabs despite shared last-room storage", () => {
  const values = new Map();
  const shared = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const firstTab = createModel(shared, "room-a");
  firstTab.rememberRoom({ room_id: "room-a" });
  const secondTab = createModel(shared, "room-b");
  secondTab.rememberRoom({ room_id: "room-b" });
  assert.equal(shared.getItem("repeat_room_id"), "room-b");
  assert.equal(firstTab.ui.roomId, "room-a");

  const restoredFirst = createModel(shared, "room-a");
  const restoredSecond = createModel(shared, "room-b");
  const snapshot = (room, player) => ({
    room: { id: room, revision: 1 },
    me: { id: player, character_id: "coral" },
    players: [],
    game: null,
  });
  assert.equal(
    restoredFirst.applySnapshot(snapshot("room-a", "ada"), "room-a"),
    true,
  );
  assert.equal(
    restoredSecond.applySnapshot(snapshot("room-b", "grace"), "room-b"),
    true,
  );
  assert.equal(restoredFirst.ui.state.me.id, "ada");
  assert.equal(restoredSecond.ui.state.me.id, "grace");
  assert.equal(
    restoredFirst.applySnapshot(snapshot("room-b", "grace"), "room-b"),
    false,
  );
  assert.equal(restoredFirst.ui.roomId, "room-a");
  assert.equal(
    createModel(shared, null).ui.roomId,
    null,
    "an explicit entry/join route does not restore last-room storage",
  );
});

test("submitting an answer keeps shared audio playing until the reveal phase", async (t) => {
  const session = audioSession();
  t.after(() => session.audio.reset());
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "initial preparation",
  );

  session.state.game.status = "playing";
  session.state.game.phase = "countdown";
  await session.audio.synchronize();
  assert.equal(
    session.sources.length,
    2,
    "one unlock source and one scheduled song",
  );
  const song = session.sources[1];
  assert.deepEqual(song.starts, [[11]]);
  assert.deepEqual(song.stops, [[31]], "the configured stop is scheduled once");

  session.clock.now = 1500;
  session.state.game.phase = "answering";
  await session.audio.synchronize();
  session.state.game.round.my_answer = {
    status: "submitted",
    song_guess: { title: "Submitted guess" },
    who_player_ids: [],
  };
  session.state.game.round.submitted_player_ids = ["host"];
  for (const now of [2000, 5000, 18000]) {
    session.clock.now = now;
    await session.audio.synchronize();
  }
  assert.equal(session.sources.length, 2, "submission never restarts the song");
  assert.deepEqual(
    song.starts,
    [[11]],
    "the original playback source is retained",
  );
  assert.deepEqual(
    song.stops,
    [[31]],
    "submission never stops shared audio early",
  );
  assert.equal(session.requestsFor("/audio-failure").length, 0);

  session.state.game.phase = "reveal";
  await session.audio.synchronize();
  await session.audio.synchronize();
  assert.deepEqual(
    song.stops,
    [[31], []],
    "reveal closes the shared song source once",
  );
  assert.equal(session.sources.length, 2);
  assert.deepEqual(session.notices, []);
});
