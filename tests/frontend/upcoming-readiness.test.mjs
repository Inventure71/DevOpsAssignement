import test from "node:test";
import assert from "node:assert/strict";
import { createUpcomingReadiness } from "../../frontend/application/upcoming-readiness.mjs";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function session({ host = false, intercept } = {}) {
  const state = {
    room: { id: "room" },
    me: { id: "player", is_host: host },
    game: {
      id: "game", status: "playing", phase: "reveal",
      upcoming_round: {
        id: "preparation", round_number: 2,
        readiness_generation: 3, ...(host ? { audio_candidate_id: "clip" } : {}),
      },
    },
  };
  const clock = { value: 1000 };
  const visibility = { visible: true };
  const playback = { ready: true, leaseId: "lease" };
  const requests = [], notices = [], inspected = [];
  const transport = {
    now: () => clock.value,
    path: (suffix) => `/api/rooms/${state.room.id}${suffix}`,
    async api(url, options) {
      const request = { url, ...options };
      requests.push(request);
      return intercept?.(request, requests.length);
    },
  };
  const controller = createUpcomingReadiness(
    transport, () => state,
    (preparation) => { inspected.push(preparation); return playback; },
    (message) => notices.push(message),
    { browserId: "browser", isVisible: () => visibility.visible },
  );
  return { state, clock, visibility, playback, requests, notices, inspected, controller };
}

test("guests acknowledge upcoming preparations immediately and renew at the polling deadline", async () => {
  const s = session();
  await s.controller.synchronize();
  assert.equal(s.requests[0].url, "/api/rooms/room/games/game/preparations/preparation/ready");
  assert.equal(s.requests[0].method, "POST");
  assert.deepEqual(s.requests[0].body, {
    readiness_generation: 3, browser_id: "browser", lease_id: null,
  });
  assert.equal(s.inspected.length, 0);
  s.state.game.phase = "leaderboard";
  s.clock.value = 2999;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 1);
  s.clock.value = 3000;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 2);
  assert.equal(s.requests[1].body.browser_id, "browser");
});

test("delayed POSTs deduplicate concurrent polling and renew from send time", async () => {
  const pending = deferred();
  const s = session({ intercept: (_, count) => count === 1 ? pending.promise : undefined });
  const first = s.controller.synchronize();
  s.clock.value = 4000;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 1);
  pending.resolve();
  await first;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 2);
});

test("host acknowledgements require decoded audio and an active speaker lease", async () => {
  const s = session({ host: true });
  s.playback.ready = false;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 0);
  s.playback.ready = true;
  s.playback.leaseId = null;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 0);
  s.playback.leaseId = "lease";
  await s.controller.synchronize();
  assert.equal(s.inspected.at(-1), s.state.game.upcoming_round);
  assert.equal(s.requests[0].body.lease_id, "lease");
  s.playback.ready = false; // Covers a suspended context through the audio contract.
  s.clock.value += 2500;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 1);
  assert.equal(s.requests[0].signal.aborted, true);
  s.playback.ready = true;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 2);
});

for (const [name, change] of [
  ["preparation", (s) => { s.state.game.upcoming_round.id = "next"; }],
  ["generation", (s) => { s.state.game.upcoming_round.readiness_generation++; }],
  ["room", (s) => { s.state.room.id = "other-room"; }],
  ["player", (s) => { s.state.me.id = "other-player"; }],
  ["game", (s) => { s.state.game.id = "other-game"; }],
  ["role", (s) => { s.state.me.is_host = false; }],
  ["lease", (s) => { s.playback.leaseId = "replacement-lease"; }],
  ["candidate", (s) => { s.state.game.upcoming_round.audio_candidate_id = "replacement-clip"; }],
]) {
  test(`${name} changes abort old work and a stale success cannot throttle the new target`, async () => {
    const old = deferred(), replacement = deferred();
    const s = session({ host: true, intercept: (_, count) =>
      count === 1 ? old.promise : count === 2 ? replacement.promise : undefined });
    const first = s.controller.synchronize();
    change(s);
    const second = s.controller.synchronize();
    assert.equal(s.requests.length, 2);
    assert.equal(s.requests[0].signal.aborted, true);
    assert.equal(s.requests[1].signal.aborted, false);
    old.resolve();
    await first;
    await s.controller.synchronize();
    assert.equal(s.requests.length, 2, "old completion must not release new in-flight work");
    replacement.resolve();
    await second;
    s.clock.value += 1999;
    await s.controller.synchronize();
    assert.equal(s.requests.length, 2);
    s.clock.value++;
    await s.controller.synchronize();
    assert.equal(s.requests.length, 3);
    assert.deepEqual(s.notices, []);
  });
}

test("reset aborts pending acknowledgements without letting stale failures affect a new session", async () => {
  const old = deferred();
  const s = session({ intercept: (_, count) => count === 1 ? old.promise : undefined });
  const first = s.controller.synchronize();
  s.controller.reset();
  assert.equal(s.requests[0].signal.aborted, true);
  await s.controller.synchronize();
  old.reject(new Error("old connection failed"));
  await first;
  assert.deepEqual(s.notices, []);
  await s.controller.synchronize();
  assert.equal(s.requests.length, 2);
});

test("hidden pages stop acknowledgements and resume immediately when visible", async () => {
  const old = deferred();
  const s = session({ intercept: (_, count) => count === 1 ? old.promise : undefined });
  const first = s.controller.synchronize();
  s.visibility.visible = false;
  await s.controller.synchronize();
  assert.equal(s.requests[0].signal.aborted, true);
  s.clock.value += 3000;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 1);
  s.visibility.visible = true;
  await s.controller.synchronize();
  old.resolve();
  await first;
  assert.equal(s.requests.length, 2);
});

test("failures retry on the next poll and notices are bounded per target", async () => {
  const s = session({ intercept: (_, count) => {
    if (count <= 2) throw new Error("Connection interrupted");
  } });
  for (let poll = 0; poll < 3; poll++) {
    await s.controller.synchronize();
    s.clock.value += 500;
  }
  assert.equal(s.requests.length, 3);
  assert.deepEqual(s.notices, ["Connection interrupted"]);
  await s.controller.synchronize();
  assert.equal(s.requests.length, 3);
  s.state.game.upcoming_round.id = "new-preparation";
  await s.controller.synchronize();
  assert.equal(s.requests.length, 4);
});

for (const status of [409, 410]) {
  test(`${status} responses stay silent and permit another poll`, async () => {
    const s = session({ intercept: () => { throw Object.assign(new Error("stale"), { status }); } });
    await s.controller.synchronize();
    s.clock.value += 500;
    await s.controller.synchronize();
    assert.equal(s.requests.length, 2);
    assert.deepEqual(s.notices, []);
  });
}

test("a changed target before the next poll cannot retain success or show a stale error", async () => {
  for (const failed of [false, true]) {
    const pending = deferred();
    const s = session({ intercept: (_, count) => count === 1 ? pending.promise : undefined });
    const first = s.controller.synchronize();
    s.state.game.upcoming_round.id = "next";
    if (failed) pending.reject(new Error("old preparation failed"));
    else pending.resolve();
    await first;
    await s.controller.synchronize();
    assert.equal(s.requests.length, 2);
    assert.deepEqual(s.notices, []);
  }
});

test("no acknowledgement runs outside live result phases or without an upcoming preparation", async () => {
  const s = session();
  for (const phase of ["setup", "ready", "countdown", "answering", "finished"]) {
    s.state.game.phase = phase;
    await s.controller.synchronize();
  }
  s.state.game.phase = "reveal";
  for (const status of ["completed", "aborted"]) {
    s.state.game.status = status;
    await s.controller.synchronize();
  }
  s.state.game.status = "playing";
  s.state.game.upcoming_round = null;
  await s.controller.synchronize();
  assert.equal(s.requests.length, 0);
});
