import test from "node:test";
import assert from "node:assert/strict";
import { createModel, safeStorage } from "../../frontend/application/state.mjs";
import {
  createTransport,
  requestId,
} from "../../frontend/transport/client.mjs";
import { createRuntime } from "../../frontend/application/runtime.mjs";
import { createActions } from "../../frontend/application/actions.mjs";
import { createAudioController } from "../../frontend/audio/host.mjs";
import { waveformLevels } from "../../frontend/audio/levels.mjs";

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}
function snapshot(game = "game", round = "round", version = 1) {
  return {
    room: { id: "room", revision: 1 },
    me: { id: "me", character_id: "coral", is_host: true },
    players: [],
    settings: { answer_seconds: 20 },
    game: {
      id: game,
      state_version: version,
      status: "playing",
      phase: "answering",
      round: {
        id: round,
        starts_at_ms: 1000,
        deadline_at_ms: 21000,
        submitted_player_ids: [],
        my_answer: null,
      },
    },
  };
}
function model() {
  const value = createModel(storage());
  value.rememberRoom({ room_id: "room" });
  value.applySnapshot(snapshot(), "room");
  return value;
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const selected = {
  title: "Dreams",
  artist: "Fleetwood Mac",
  token: "signed-selection",
  artwork_url: null,
};

test("an accepted answer stays locked when an older poll arrives", () => {
  const m = model();
  m.acceptAnswer("game", "round", {
    song_guess: selected,
    who_player_ids: ["friend"],
  });
  m.applySnapshot(snapshot(), "room");
  assert.equal(m.ui.state.game.round.my_answer.song_guess.title, "Dreams");
  assert.deepEqual(m.ui.state.game.round.submitted_player_ids, ["me"]);
  assert.deepEqual([...m.ui.listeners], ["friend"]);
});
test("a late receipt cannot submit a replacement attempt", () => {
  const m = model();
  m.applySnapshot(snapshot("game", "replacement", 2), "room");
  m.acceptAnswer("game", "round", { song_guess: selected, who_player_ids: [] });
  assert.equal(m.ui.state.game.round.my_answer, null);
  assert.equal(m.ui.songGuess, null);
});
test("a new game and forgotten identity clear answers and selections", () => {
  const m = model();
  m.acceptAnswer("game", "round", {
    song_guess: selected,
    who_player_ids: ["friend"],
  });
  m.applySnapshot(snapshot("new-game", "round", 1), "room");
  assert.equal(m.ui.state.game.round.my_answer, null);
  assert.equal(m.ui.listeners.size, 0);
  m.forgetRoom();
  assert.equal(m.ui.roomId, null);
  assert.equal(m.ui.state, null);
  assert.equal(m.readySent.size, 0);
});
test("polls from another room or an older revision cannot overwrite current state", () => {
  const m = model();
  const older = snapshot();
  older.room.revision = 0;
  assert.equal(m.applySnapshot(older, "room"), false);
  assert.equal(m.applySnapshot(snapshot(), "another-room"), false);
  assert.equal(m.ui.state.room.revision, 1);
});
test("unsubmitted drafts survive polling and reset for the next round", () => {
  const m = model();
  m.ui.songGuess = selected;
  m.ui.listeners.add("friend");
  m.applySnapshot(snapshot("game", "round", 2), "room");
  assert.equal(m.ui.songGuess, selected);
  assert.equal(m.ui.listeners.size, 1);
  m.applySnapshot(snapshot("game", "next", 3), "room");
  assert.equal(m.ui.songGuess, null);
  assert.equal(m.ui.listeners.size, 0);
});
test("storage denial still supports a usable browser session", () => {
  const denied = {
    getItem() {
      throw Error("denied");
    },
    setItem() {
      throw Error("denied");
    },
    removeItem() {
      throw Error("denied");
    },
  };
  const safe = safeStorage(denied);
  safe.setItem("room", "one");
  assert.equal(safe.getItem("room"), "one");
  safe.removeItem("room");
  assert.equal(safe.getItem("room"), null);
});
test("LAN HTTP request identifiers use getRandomValues without randomUUID", () => {
  const id = requestId({
    getRandomValues(bytes) {
      bytes.fill(7);
      return bytes;
    },
  });
  assert.match(
    id,
    /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/,
  );
});
test("transport preserves signed song tokens and sends room cookies", async () => {
  let request;
  const t = createTransport(
    () => "room",
    () => snapshot(),
    async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({ accepted: true }) };
    },
  );
  await t.api(t.roundPath("/answers"), {
    method: "POST",
    body: { song_guess_token: selected.token, who_player_ids: [] },
  });
  assert.equal(request.options.credentials, "same-origin");
  assert.deepEqual(JSON.parse(request.options.body), {
    song_guess_token: "signed-selection",
    who_player_ids: [],
  });
  assert.equal(request.url, "/api/rooms/room/games/game/rounds/round/answers");
});
test("cancelled song searches abort the actual fetch request", async () => {
  let signal;
  const t = createTransport(
    () => "room",
    () => null,
    async (url, options) => {
      signal = options.signal;
      return { ok: true, json: async () => ({ songs: [] }) };
    },
  );
  const controller = new AbortController();
  controller.abort();
  await t.api("/search", { signal: controller.signal });
  assert.equal(signal.aborted, true);
});
test("server clock estimation uses request midpoint and ignores slow outliers", async () => {
  let now = 100;
  let server = 112;
  let delay = 4;
  const t = createTransport(
    () => "room",
    () => null,
    async () => {
      now += delay;
      return { ok: true, json: async () => ({ server_now_ms: server }) };
    },
    () => now,
  );
  await t.api("/state");
  assert.equal(t.now(), 114);
  server = 10000;
  delay = 1000;
  await t.api("/state");
  assert.equal(t.now(), 1114);
});
test("concurrent forced refreshes still perform one state read at a time", async () => {
  const m = model();
  let active = 0,
    max = 0,
    reads = 0;
  const runtime = createRuntime(
    m,
    {
      path: (s) => s,
      api: async () => {
        reads++;
        active++;
        max = Math.max(max, active);
        await new Promise((r) => setTimeout(r, 5));
        active--;
        return snapshot();
      },
    },
    { synchronize: async () => {} },
    { synchronize: async () => {} },
    () => {},
    () => {},
    () => {},
  );
  await Promise.all([
    runtime.refresh(),
    runtime.refresh({ fresh: true }),
    runtime.refresh({ fresh: true }),
  ]);
  assert.equal(max, 1);
  assert.equal(reads, 3);
});
function runtimeHarness() {
  const m = model();
  const requests = { state: [], heartbeat: [] };
  const timers = new Map();
  const effects = { render: 0, synchronize: 0, readiness: 0, renew: 0, forget: 0, notice: 0 };
  let timerId = 0;
  const runtime = createRuntime(
    m,
    {
      path: (suffix) => suffix,
      api: (path) => {
        const request = deferred();
        requests[path === "/state" ? "state" : "heartbeat"].push(request);
        return request.promise;
      },
    },
    {
      synchronize: async () => effects.synchronize++,
      renewLease: async () => effects.renew++,
    },
    { synchronize: async () => effects.readiness++, reset() {} },
    () => effects.render++,
    () => effects.notice++,
    () => effects.forget++,
    (callback, delay) => {
      const id = ++timerId;
      timers.set(id, { callback, delay });
      return id;
    },
    (id) => timers.delete(id),
  );
  return { m, runtime, requests, timers, effects };
}

test("runtime restart keeps one poll and heartbeat while older requests finish", async () => {
  const { m, runtime, requests, timers, effects } = runtimeHarness();
  runtime.start();
  assert.equal(requests.state.length, 1);
  assert.equal(requests.heartbeat.length, 1);
  runtime.stop();
  runtime.start();
  assert.equal(requests.state.length, 1); // The new poll waits for the in-flight read.
  assert.equal(requests.heartbeat.length, 2); // Heartbeats stay independent.
  requests.state[0].resolve(snapshot("stale-game", "stale-round", 99));
  requests.heartbeat[0].resolve({ accepted: true });
  await new Promise(setImmediate);
  assert.equal(m.ui.state.game.id, "game");
  assert.deepEqual(effects, {
    render: 0,
    synchronize: 0,
    readiness: 0,
    renew: 0,
    forget: 0,
    notice: 0,
  });
  assert.equal(timers.size, 0);
  assert.equal(requests.state.length, 2);
  requests.state[1].resolve(snapshot("game", "round", 2));
  requests.heartbeat[1].resolve({ accepted: true });
  await new Promise(setImmediate);
  assert.equal(m.ui.state.game.state_version, 2);
  assert.deepEqual(effects, {
    render: 1,
    synchronize: 1,
    readiness: 1,
    renew: 1,
    forget: 0,
    notice: 0,
  });
  assert.deepEqual(
    [...timers.values()].map(({ delay }) => delay).sort((a, b) => a - b),
    [500, 5000],
  );
  const [pollId, poll] = [...timers].find(([, timer]) => timer.delay === 500);
  timers.delete(pollId);
  poll.callback();
  assert.equal(requests.state.length, 3);
  requests.state[2].resolve(snapshot("game", "round", 3));
  await new Promise(setImmediate);
  assert.equal(timers.size, 2);
  runtime.stop();
  assert.equal(timers.size, 0);
});

test("stopping runtime discards pending errors and prevents timer renewal", async () => {
  const { m, runtime, requests, timers, effects } = runtimeHarness();
  runtime.start();
  runtime.stop();
  requests.state[0].reject(
    Object.assign(new Error("Expired old session"), { status: 401 }),
  );
  requests.heartbeat[0].resolve({ accepted: true });
  await new Promise(setImmediate);
  assert.equal(timers.size, 0);
  assert.equal(m.ui.disconnected, false);
  assert.deepEqual(effects, {
    render: 0,
    synchronize: 0,
    readiness: 0,
    renew: 0,
    forget: 0,
    notice: 0,
  });
});

test("answer submission freezes its payload and handles a late round change", async () => {
  const m = model();
  m.ui.songGuess = selected;
  m.ui.listeners.add("friend");
  const gate = deferred();
  let sent;
  const action = createActions({
    model: m,
    transport: {
      api: async (url, options) => {
        sent = options.body;
        await gate.promise;
      },
      roundPath: () => "/answer",
      now: () => 2000,
    },
    audio: {},
    runtime: { refresh: async () => {} },
    render() {},
    notice() {},
    forgetRoom() {},
    navigator: {},
    confirm: () => true,
  });
  const pending = action("submit-answer");
  m.applySnapshot(snapshot("game", "new-round", 2), "room");
  gate.resolve();
  await pending;
  assert.deepEqual(sent, {
    song_guess_token: "signed-selection",
    who_player_ids: ["friend"],
  });
  assert.equal(m.ui.state.game.round.my_answer, null);
});
test("no answer is sent at or after the deadline", async () => {
  const m = model();
  let calls = 0;
  const action = createActions({
    model: m,
    transport: {
      api: async () => calls++,
      roundPath: () => "/answer",
      now: () => 21000,
    },
    audio: {},
    runtime: { refresh: async () => {} },
    render() {},
    notice() {},
    forgetRoom() {},
    navigator: {},
    confirm: () => true,
  });
  await action("submit-answer");
  assert.equal(calls, 0);
  assert.equal(m.ui.state.game.round.my_answer, null);
});
test("waveform derives levels from audio samples and keeps silence zero", () => {
  const quiet = { getChannelData: () => new Float32Array(4800) };
  assert.deepEqual(waveformLevels(quiet), Array(48).fill(0));
  const data = new Float32Array(4800);
  data.fill(0.5, 2400);
  const levels = waveformLevels({ getChannelData: () => data });
  assert.equal(levels.length, 48);
  assert.equal(levels[0], 0);
  assert.equal(levels[47], 1);
  assert(levels.every((level) => level >= 0 && level <= 1));
});
test("host preloading deduplicates source URLs and publishes real waveform levels", async () => {
  const state = snapshot();
  state.game.phase = "setup";
  let fetches = 0,
    decoded = 0;
  const checks = [];
  const sources = [];
  const samples = new Float32Array(4800).fill(0.4);
  class Context extends EventTarget {
    state = "running";
    sampleRate = 48000;
    destination = {};
    currentTime = 5;
    async resume() {}
    createBuffer() {
      return {};
    }
    createBufferSource() {
      const source = {
        connect() {},
        start(...args) {
          this.starts = args;
        },
        stop(...args) {
          this.stops = args;
        },
      };
      sources.push(source);
      return source;
    }
    async decodeAudioData() {
      decoded++;
      return { duration: 30, getChannelData: () => samples };
    }
  }
  const api = async (url, options) => {
    if (url.endsWith("/audio-controller")) return { lease_id: "lease" };
    if (url.endsWith("/audio"))
      return {
        candidates: [
          { candidate_id: "one", preview_url: "/clip" },
          { candidate_id: "two", preview_url: "/clip" },
        ],
      };
    if (url.endsWith("/preload-check")) checks.push(options.body);
    return { accepted: true };
  };
  const environment = {
    AudioContext: Context,
    fetch: async () => {
      fetches++;
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) };
    },
    AbortController,
    setTimeout,
    clearTimeout,
  };
  const audio = createAudioController(
    { api, path: (s) => s, roundPath: (s) => s },
    () => state,
    () => 2000,
    "tab",
    () => {},
    (message) => assert.fail(message),
    environment,
  );
  await audio.enable();
  await audio.synchronize();
  for (let i = 0; i < 30 && checks.length < 2; i++)
    await new Promise((r) => setTimeout(r, 2));
  assert.equal(checks.length, 2);
  assert.equal(fetches, 1);
  assert.equal(decoded, 1);
  assert.equal(checks[0].waveform.length, 48);
  state.game.round.audio_candidate_id = "one";
  state.game.round.starts_at_ms = 3000;
  state.game.round.deadline_at_ms = 23000;
  state.game.phase = "countdown";
  await audio.synchronize();
  await audio.synchronize();
  assert.equal(sources.length, 2);
  assert.deepEqual(sources[1].starts, [6]);
  assert.deepEqual(sources[1].stops, [26]);
  audio.reset();
});
