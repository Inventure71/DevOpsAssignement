import test from "node:test";
import assert from "node:assert/strict";
import { createAudioController } from "../../frontend/audio/host.mjs";
import { createRoundReadiness } from "../../frontend/application/round-readiness.mjs";
import { createUpcomingReadiness } from "../../frontend/application/upcoming-readiness.mjs";
import { createModel } from "../../frontend/application/state.mjs";
import { createRuntime } from "../../frontend/application/runtime.mjs";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

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

function audioSession({
  failFirstManifest = false,
  interceptRequest,
  resumeContext,
  decodeClip,
  roundPath = (suffix) => `/rounds/round${suffix}`,
  getState,
} = {}) {
  const clock = { now: 0 };
  let state = {
    room: { id: "room" },
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
  const readState = () => getState ? getState() : state;
  const requests = [],
    sources = [],
    notices = [];
  let renders = 0;
  let fetches = 0,
    decodes = 0;
  let sessionContext;
  const samples = new Float32Array(4800);
  samples.fill(0.25, 2400);
  class Context extends EventTarget {
    constructor() {
      super();
      sessionContext = this;
    }
    state = "running";
    sampleRate = 48000;
    destination = {};
    currentTime = 10;
    async resume() {
      await resumeContext?.(this);
    }
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
      const buffer = { duration: 30, getChannelData: () => samples };
      return decodeClip ? decodeClip(buffer) : buffer;
    }
  }
  const api = async (url, options = {}) => {
    requests.push({ url, ...options });
    const intercepted = interceptRequest?.(url, options);
    if (intercepted !== undefined) return intercepted;
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
      roundPath: (suffix) => roundPath(suffix, state),
    },
    readState,
    () => clock.now,
    "tab",
    () => renders++,
    (message) => notices.push(message),
    environment,
  );
  const readiness = createRoundReadiness(
    { api, path: (suffix) => suffix, roundPath: (suffix) => `/rounds/round${suffix}` },
    readState,
    readySent,
    (round) => audio.readiness(round),
    (message) => notices.push(message),
  );
  const upcomingReadiness = createUpcomingReadiness(
    { api, path: (suffix) => suffix },
    readState,
    (round) => audio.readiness(round),
    (message) => notices.push(message),
    { now: () => clock.now, browserId: "browser", isVisible: () => true },
  );
  return {
    audio,
    api,
    readiness,
    upcomingReadiness,
    state,
    clock,
    sources,
    context: () => sessionContext,
    notices,
    readySent,
    setState(value) {
      state = value;
    },
    requestsFor: (suffix) =>
      requests.filter((request) => request.url.endsWith(suffix)),
    counts: () => ({ fetches, decodes }),
    renders: () => renders,
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
  await session.readiness.synchronize();
  await session.readiness.synchronize();
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

test("explicit URL room references restore each tab independently", () => {
  const firstTab = createModel("room-a");
  firstTab.rememberRoom({ room_id: "room-a" });
  const secondTab = createModel("room-b");
  secondTab.rememberRoom({ room_id: "room-b" });
  assert.equal(firstTab.ui.roomId, "room-a");

  const restoredFirst = createModel("room-a");
  const restoredSecond = createModel("room-b");
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
    createModel().ui.roomId,
    null,
    "the plain entry route does not implicitly restore a room",
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

test("leaving during audio unlock prevents a lease request in the next room", async () => {
  const resume = deferred();
  const session = audioSession({ resumeContext: () => resume.promise });
  const enable = session.audio.enable();
  session.audio.reset();
  session.state.room.id = "new-room";
  resume.resolve();
  await enable;
  assert.equal(session.requestsFor("/audio-controller").length, 0);
  assert.equal(session.audio.status.leaseId, null);
  assert.equal(session.sources.length, 0);
});

for (const outcome of ["success", "conflict"]) {
  test(`a late lease ${outcome} cannot resurrect playback after leaving`, async () => {
    const lease = deferred();
    const session = audioSession({
      interceptRequest: (url) =>
        url.endsWith("/audio-controller") ? lease.promise : undefined,
    });
    const enable = session.audio.enable();
    await settleUntil(
      () => session.requestsFor("/audio-controller").length === 1,
      "lease request",
    );
    session.audio.reset();
    session.setState(null);
    assert.equal(session.requestsFor("/audio-controller")[0].signal.aborted, true);
    if (outcome === "success") lease.resolve({ lease_id: "abandoned-lease" });
    else lease.reject(Object.assign(new Error("Old conflict"), { status: 409 }));
    await enable;
    assert.deepEqual(session.audio.status, {
      unlocked: true, leaseId: null, conflict: false,
    });
    assert.deepEqual(session.notices, []);
  });

  test(`a late renewal ${outcome} cannot replace the lease acquired by takeover`, async () => {
    const renewal = deferred();
    let attempts = 0;
    const session = audioSession({
      interceptRequest: (url) => {
        if (!url.endsWith("/audio-controller")) return;
        attempts++;
        if (attempts === 2) return renewal.promise;
        return { lease_id: attempts === 1 ? "original" : "replacement" };
      },
    });
    await session.audio.enable();
    const renew = session.audio.renewLease();
    await session.audio.enable(true);
    if (outcome === "success") renewal.resolve({ lease_id: "stale" });
    else renewal.reject(Object.assign(new Error("Old conflict"), { status: 409 }));
    await renew;
    assert.equal(session.audio.status.leaseId, "replacement");
    assert.equal(session.audio.status.conflict, false);
    assert.equal(session.requestsFor("/audio-controller")[2].body.takeover, true);
    assert.equal(session.requestsFor("/audio-controller")[1].signal.aborted, true);
    session.audio.reset();
  });

  test(`a late manifest ${outcome} cannot affect a restarted game with the same ID`, async () => {
    const abandoned = deferred();
    let manifests = 0;
    const session = audioSession({
      interceptRequest: (url) => {
        if (url.endsWith("/audio") && ++manifests === 1) return abandoned.promise;
      },
    });
    await session.audio.enable();
    await session.audio.synchronize();
    session.audio.reset();
    await session.audio.enable();
    await session.audio.synchronize();
    await settleUntil(
      () => session.requestsFor("/preload-check").length === 2,
      "replacement preload",
    );
    if (outcome === "success") abandoned.resolve({
      candidates: [{ candidate_id: "stale", preview_url: "/stale" }],
    });
    else abandoned.reject(new Error("Old manifest failed"));
    await new Promise(setImmediate);
    assert.equal(session.audio.readiness(session.state.game.round).ready, true);
    assert.equal(session.requestsFor("/preload-check").length, 2);
    assert.deepEqual(session.notices, []);
    assert.deepEqual(session.counts(), { fetches: 1, decodes: 1 });
    session.audio.reset();
  });
}

test("late clip decoding cannot publish checks or audio into a replacement session", async () => {
  const oldDecode = deferred();
  let decoding = 0;
  const session = audioSession({
    decodeClip: (buffer) => ++decoding === 1 ? oldDecode.promise : buffer,
  });
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(() => session.counts().decodes === 1, "pending decode");
  session.audio.reset();
  await session.audio.enable(true);
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "new decode checks",
  );
  oldDecode.resolve({ duration: 30, getChannelData: () => new Float32Array(100) });
  await new Promise(setImmediate);
  assert.equal(session.requestsFor("/preload-check").length, 2);
  assert.equal(session.audio.readiness(session.state.game.round).ready, true);
  assert.deepEqual(session.notices, []);
  session.audio.reset();
});

test("room identity changes invalidate a lease even without an explicit reset", async () => {
  const session = audioSession();
  await session.audio.enable();
  session.state.room.id = "replacement-room";
  await session.audio.renewLease();
  await session.audio.synchronize();
  assert.equal(session.requestsFor("/audio-controller").length, 1);
  assert.equal(session.audio.status.leaseId, null);
  assert.equal(session.requestsFor("/audio").length, 0);
});

test("guest readiness acknowledges once without consulting host audio", async () => {
  const session = audioSession();
  session.state.me.is_host = false;
  session.state.game.phase = "ready";
  await session.readiness.synchronize();
  await session.readiness.synchronize();
  assert.equal(session.requestsFor("/ready").length, 1);
  assert.deepEqual(session.requestsFor("/ready")[0].body, {
    readiness_generation: 3, lease_id: null,
  });
  assert.equal(session.requestsFor("/audio-controller").length, 0);
  assert.equal(session.sources.length, 0);
});

test("late readiness failure cannot clear a new room acknowledgement with the same round ID", async () => {
  const abandoned = deferred();
  let acknowledgements = 0;
  const session = audioSession({
    interceptRequest: (url) => {
      if (url.endsWith("/ready") && ++acknowledgements === 1) return abandoned.promise;
    },
  });
  session.state.me.is_host = false;
  session.state.game.phase = "ready";
  const first = session.readiness.synchronize();
  session.readiness.reset();
  session.state.room.id = "replacement-room";
  await session.readiness.synchronize();
  abandoned.reject(new Error("Previous room offline"));
  await first;
  assert.ok(session.readySent.has("round:3"));
  assert.equal(session.requestsFor("/ready").length, 2);
  assert.deepEqual(session.notices, []);
});

test("an older enable cannot overwrite a newer explicit takeover", async () => {
  const previous = deferred();
  let leases = 0;
  const session = audioSession({
    interceptRequest: (url) => {
      if (!url.endsWith("/audio-controller")) return;
      return ++leases === 1 ? previous.promise : { lease_id: "takeover" };
    },
  });
  const first = session.audio.enable();
  await settleUntil(() => leases === 1, "first lease attempt");
  await session.audio.enable(true);
  previous.resolve({ lease_id: "old" });
  await first;
  assert.equal(session.audio.status.leaseId, "takeover");
  assert.equal(session.audio.status.conflict, false);
  session.audio.reset();
});

test("late interruption errors stay silent after leaving the room", async () => {
  const previous = deferred();
  const session = audioSession({
    interceptRequest: (url) => url.endsWith("/audio-failure") ? previous.promise : undefined,
  });
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "initial preload",
  );
  session.state.game.phase = "countdown";
  await session.audio.synchronize();
  session.audio.suspend();
  const report = session.audio.synchronize();
  assert.equal(session.requestsFor("/audio-failure").length, 1);
  session.audio.reset();
  session.setState(null);
  previous.reject(new Error("Abandoned room failed"));
  await report;
  assert.deepEqual(session.notices, []);
  assert.equal(session.audio.status.leaseId, null);
});

test("a live lease conflict stops the host source and requires explicit takeover", async () => {
  let leases = 0;
  const session = audioSession({
    interceptRequest: (url) => {
      if (!url.endsWith("/audio-controller")) return;
      if (++leases === 2)
        throw Object.assign(new Error("Other host tab owns audio"), { status: 409 });
    },
  });
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "initial preload",
  );
  session.state.game.phase = "countdown";
  await session.audio.synchronize();
  const source = session.sources[1];
  await assert.rejects(session.audio.renewLease(), { status: 409 });
  assert.deepEqual(source.stops, [[31], []]);
  assert.deepEqual(session.audio.status, {
    unlocked: true, leaseId: null, conflict: true,
  });
  assert.equal(session.audio.readiness(session.state.game.round).ready, false);
  session.audio.reset();
});

test("an old playback poll cannot report its suspended audio against a replacement room", async () => {
  const previousReport = deferred();
  let failures = 0;
  let canResume = true;
  const session = audioSession({
    resumeContext: (context) => {
      context.state = canResume ? "running" : "suspended";
    },
    roundPath: (suffix, state) =>
      `/rooms/${state.room.id}/games/${state.game.id}/rounds/${state.game.round.id}${suffix}`,
    interceptRequest: (url) => {
      if (url.endsWith("/audio-failure") && ++failures === 1)
        return previousReport.promise;
    },
  });
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "initial preload",
  );
  session.state.game.phase = "answering";
  session.context().state = "suspended";
  const oldPoll = session.audio.synchronize();
  assert.equal(session.requestsFor("/audio-failure").length, 1);

  session.audio.reset();
  const replacement = structuredClone(session.state);
  replacement.room.id = "new-room";
  replacement.game.id = "new-game";
  replacement.game.phase = "ready";
  replacement.game.round.id = "new-round";
  replacement.game.round.readiness_generation = 9;
  session.setState(replacement);
  canResume = false;
  await assert.rejects(session.audio.enable(), /Host speaker couldn’t start/);
  previousReport.resolve({ accepted: true });
  await oldPoll;

  assert.equal(session.requestsFor("/audio-failure").length, 1);
  assert.equal(session.audio.status.leaseId, null);
  assert.deepEqual(session.notices, []);
  session.audio.reset();
});

test("a delayed ready acknowledgement cannot block polling or host countdown scheduling", async () => {
  const readyReply = deferred();
  const model = createModel("room");
  const session = audioSession({
    getState: () => model.ui.state,
    interceptRequest: (url) => url.endsWith("/ready") ? readyReply.promise : undefined,
  });
  model.applySnapshot(session.state, "room");
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(
    () => session.requestsFor("/preload-check").length === 2,
    "initial preload",
  );

  const ready = structuredClone(session.state);
  ready.game.phase = "ready";
  ready.game.state_version = 1;
  const countdown = structuredClone(ready);
  countdown.game.status = "playing";
  countdown.game.phase = "countdown";
  countdown.game.state_version = 2;
  const snapshots = [ready, countdown];
  const timers = new Map();
  let reads = 0;
  let nextTimer = 0;
  const runtime = createRuntime(
    model,
    {
      path: (suffix) => suffix,
      api: async (url) => {
        if (url === "/state") {
          reads++;
          return snapshots.shift();
        }
        return { accepted: true };
      },
    },
    session.audio,
    session.readiness,
    () => {},
    (message) => session.notices.push(message),
    () => assert.fail("The room must remain connected"),
    (callback, delay) => {
      const id = ++nextTimer;
      timers.set(id, { callback, delay });
      return id;
    },
    (id) => timers.delete(id),
  );
  runtime.start();
  await new Promise(setImmediate);
  assert.equal(session.requestsFor("/ready").length, 1);
  const poll = [...timers.values()].find(({ delay }) => delay === 500);
  assert.ok(poll, "The next state read is scheduled while ready POST is pending");
  poll.callback();
  await new Promise(setImmediate);
  assert.equal(reads, 2);
  assert.equal(model.ui.state.game.phase, "countdown");
  assert.deepEqual(session.sources[1].starts, [[11]]);
  assert.equal(session.requestsFor("/ready").length, 1);

  readyReply.resolve({ accepted: true });
  await new Promise(setImmediate);
  assert.equal(model.ui.disconnected, false);
  assert.deepEqual(session.notices, []);
  runtime.stop();
  session.audio.reset();
});

for (const state of ["suspended", "interrupted", "closed"]) {
  test(`${state} host audio blocks current and upcoming acknowledgements until enabled again`, async (t) => {
    const session = audioSession({
      resumeContext: (context) => { context.state = "running"; },
    });
    t.after(() => {
      session.upcomingReadiness.reset();
      session.audio.reset();
    });
    await session.audio.enable();
    await session.audio.synchronize();
    await settleUntil(
      () => session.audio.readiness(session.state.game.round).ready,
      "decoded host audio",
    );
    session.state.game.phase = "reveal";
    session.state.game.upcoming_round = {
      id: "next", readiness_generation: 4, audio_candidate_id: "two",
    };
    assert.equal(session.audio.readiness(session.state.game.upcoming_round).ready, true);
    const fetched = session.counts().fetches;
    await session.audio.synchronize();
    assert.equal(session.counts().fetches, fetched, "decoded upcoming audio is reused");
    assert.equal(session.sources.length, 1, "results never start playback");
    const originalContext = session.context();
    const before = session.renders();
    originalContext.state = state;
    originalContext.dispatchEvent(new Event("statechange"));
    assert.equal(session.renders(), before + 1, "audio state changes refresh the UI");
    assert.equal(session.audio.status.unlocked, false);
    assert.equal(session.audio.readiness(session.state.game.round).ready, false);

    session.state.game.phase = "ready";
    await session.readiness.synchronize();
    await session.audio.synchronize();
    assert.equal(session.readySent.size, 0);
    session.state.game.phase = "leaderboard";
    await session.upcomingReadiness.synchronize();
    assert.equal(session.requestsFor("/ready").length, 0);
    assert.equal(session.requestsFor("/audio-failure").length, 0);
    assert.equal(session.sources.length, 1, "only the gesture unlock source exists");

    await session.audio.enable();
    await session.audio.synchronize();
    await settleUntil(
      () => session.audio.readiness(session.state.game.upcoming_round).ready,
      "recovered host audio",
    );
    assert.equal(session.audio.status.unlocked, true);
    await session.upcomingReadiness.synchronize();
    session.state.game.phase = "ready";
    await session.readiness.synchronize();
    await session.readiness.synchronize();
    assert.deepEqual(session.requestsFor("/ready").map((request) => request.url), [
      "/games/game/preparations/next/ready", "/rounds/round/ready",
    ]);
    if (state === "closed") {
      assert.notEqual(session.context(), originalContext);
      const recoveredRenders = session.renders();
      originalContext.dispatchEvent(new Event("statechange"));
      assert.equal(session.renders(), recoveredRenders, "replaced contexts are detached");
    } else assert.equal(session.context(), originalContext);
  });
}

test("a resolved resume that leaves audio suspended cannot acquire a speaker lease", async (t) => {
  const session = audioSession({
    resumeContext: (context) => { context.state = "suspended"; },
  });
  t.after(() => session.audio.reset());
  await assert.rejects(session.audio.enable(), /Host speaker couldn’t start/);
  assert.equal(session.audio.status.unlocked, false);
  assert.equal(session.audio.status.leaseId, null);
  assert.equal(session.requestsFor("/audio-controller").length, 0);
  assert.equal(session.sources.length, 0);
});

test("suspension during lease acquisition is reflected when enable completes", async (t) => {
  const lease = deferred();
  const session = audioSession({
    interceptRequest: (url) => url.endsWith("/audio-controller") ? lease.promise : undefined,
  });
  t.after(() => session.audio.reset());
  const enable = session.audio.enable();
  await settleUntil(() => session.requestsFor("/audio-controller").length === 1, "lease acquisition");
  session.context().state = "suspended";
  lease.resolve({ lease_id: "lease" });
  await enable;
  assert.equal(session.audio.status.leaseId, "lease");
  assert.equal(session.audio.status.unlocked, false);
  await session.audio.synchronize();
  await settleUntil(() => session.requestsFor("/preload-check").length === 2, "decoded clips");
  session.state.game.phase = "ready";
  await session.readiness.synchronize();
  assert.equal(session.requestsFor("/ready").length, 0);
});

test("suspension after acknowledging readiness still reports one playback failure", async (t) => {
  const session = audioSession();
  t.after(() => session.audio.reset());
  await session.audio.enable();
  await session.audio.synchronize();
  await settleUntil(() => session.audio.readiness(session.state.game.round).ready, "decoded host audio");
  session.state.game.phase = "ready";
  await session.readiness.synchronize();
  assert.equal(session.requestsFor("/ready").length, 1);
  session.context().state = "suspended";
  session.state.game.phase = "countdown";
  await session.audio.synchronize();
  await session.audio.synchronize();
  assert.equal(session.requestsFor("/audio-failure").length, 1);
  assert.equal(session.sources.at(-1).starts.length, 0, "suspended audio never starts the song");
});

test("stopping and restoring polling aborts an upcoming request and checks in again", async (t) => {
  const pending = deferred();
  let preparationRequests = 0;
  const session = audioSession({
    interceptRequest: (url) => url.includes("/preparations/") && ++preparationRequests === 1
      ? pending.promise : undefined,
  });
  session.state.me.is_host = false;
  session.state.game.status = "playing";
  session.state.game.phase = "reveal";
  session.state.game.upcoming_round = { id: "next", round_number: 2, readiness_generation: 1 };
  const model = { ui: { roomId: "room", state: session.state }, applySnapshot: () => true };
  const runtime = createRuntime(
    model, { path: (suffix) => suffix, api: async () => session.state },
    { synchronize: async () => {}, renewLease: async () => {} },
    session.readiness, () => {}, (message) => session.notices.push(message),
    () => assert.fail("The room must stay connected"), () => 1, () => {},
  );
  t.after(() => runtime.stop());
  runtime.start();
  await new Promise(setImmediate);
  const requests = () => session.requestsFor("/ready");
  assert.equal(requests().length, 1);
  runtime.stop();
  assert.equal(requests()[0].signal.aborted, true);
  runtime.start();
  await new Promise(setImmediate);
  assert.equal(requests().length, 2, "A frozen reply cannot block a restored page");
  assert.equal(requests()[1].signal.aborted, false);
  pending.reject(new Error("Cancelled old page"));
  await new Promise(setImmediate);
  assert.deepEqual(session.notices, []);
});
