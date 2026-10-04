import test from "node:test";
import assert from "node:assert/strict";
import { createActions } from "../../frontend/application/actions.mjs";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

// Exercise the production command boundary with controllable audio/network waits.
function session({ status: initial = {}, enable, api } = {}) {
  const state = {
    room: { id: "room", revision: 4, minimum_players: 3 },
    me: { id: "host", is_host: true },
    players: ["Host", "Ada", "Sam"].map((nickname) => ({ nickname, song_count: 10 })),
  };
  const ui = { state, roomId: "room", pending: false, dismissedGame: "old-game" };
  const status = { unlocked: false, leaseId: null, conflict: false, ...initial };
  const requests = [], enables = [], notices = [], pending = [];
  let refreshes = 0;
  const action = createActions({
    model: { ui },
    transport: {
      path: (suffix) => `/api/rooms/${ui.state.room.id}${suffix}`,
      async api(url, options) {
        requests.push({ url, ...options });
        return api?.(url, options);
      },
    },
    audio: {
      get status() { return status; },
      async enable(takeover) {
        enables.push(takeover);
        if (enable) await enable(status, takeover);
        else Object.assign(status, { unlocked: true, leaseId: "new-lease", conflict: false });
      },
    },
    runtime: { async refresh() { refreshes++; } },
    render() { pending.push(ui.pending); },
    notice(message) { notices.push(message); },
  });
  return { state, ui, status, action, requests, enables, notices, pending, refreshes: () => refreshes };
}

test("Start game activates audio in the gesture stack and waits for its lease before posting", async () => {
  const gate = deferred();
  const s = session({ enable: async (status) => {
    await gate.promise;
    Object.assign(status, { unlocked: true, leaseId: "gesture-lease" });
  } });
  const first = s.action("start");
  assert.deepEqual(s.enables, [false], "activation happens before yielding to another task");
  assert.equal(s.requests.length, 0, "start waits for successful audio activation");
  assert.equal(s.ui.pending, "start");
  await s.action("start");
  assert.equal(s.enables.length, 1, "repeated clicks share the pending command");
  gate.resolve();
  await first;
  assert.equal(s.requests.length, 1);
  assert.equal(s.requests[0].url, "/api/rooms/room/start");
  assert.equal(s.requests[0].method, "POST");
  assert.equal(s.requests[0].body.lease_id, "gesture-lease");
  assert.equal(s.requests[0].body.room_revision, 4);
  assert.ok(s.requests[0].body.request_id);
  assert.equal(s.ui.dismissedGame, null);
  assert.equal(s.ui.pending, false);
  assert.equal(s.refreshes(), 1);
  assert.deepEqual(s.notices, []);
});

test("a running speaker with its lease is reused when starting another game", async () => {
  const s = session({ status: { unlocked: true, leaseId: "existing-lease" } });
  await s.action("start");
  assert.deepEqual(s.enables, []);
  assert.equal(s.requests[0].body.lease_id, "existing-lease");
});

for (const [name, status] of [
  ["suspended speaker", { unlocked: false, leaseId: "old-lease" }],
  ["missing lease", { unlocked: true, leaseId: null }],
  ["known tab conflict", { unlocked: true, leaseId: null, conflict: true }],
]) {
  test(`Start game recovers a ${name} before starting`, async () => {
    const s = session({ status });
    await s.action("start");
    assert.deepEqual(s.enables, [Boolean(status.conflict)]);
    assert.equal(s.requests[0].body.lease_id, "new-lease");
  });
}

test("failed audio activation stays in the lobby and a new Start game click can retry", async () => {
  let attempts = 0;
  const s = session({ enable: async (status) => {
    if (++attempts === 1) throw new Error("Speaker permission denied");
    Object.assign(status, { unlocked: true, leaseId: "retry-lease" });
  } });
  await s.action("start");
  assert.equal(s.requests.length, 0);
  assert.equal(s.ui.pending, false);
  assert.equal(s.ui.dismissedGame, "old-game");
  assert.deepEqual(s.notices, ["Speaker permission denied"]);
  await s.action("start");
  assert.equal(s.enables.length, 2);
  assert.equal(s.requests.length, 1);
  assert.equal(s.requests[0].body.lease_id, "retry-lease");
});

for (const [name, status] of [
  ["context suspends", { unlocked: false, leaseId: "lease" }],
  ["lease disappears", { unlocked: true, leaseId: null }],
]) {
  test(`no game starts if the ${name} during activation`, async () => {
    const s = session({ enable: async (current) => Object.assign(current, status) });
    await s.action("start");
    assert.equal(s.requests.length, 0);
    assert.match(s.notices[0], /Click Start game to try again/);
    assert.equal(s.ui.pending, false);
  });
}

test("retry after an uncertain start response preserves the idempotency key and speaker lease", async () => {
  let attempts = 0;
  const s = session({ api: async () => {
    if (++attempts === 1) throw new Error("Response lost");
  } });
  await s.action("start");
  await s.action("start");
  assert.equal(s.enables.length, 1);
  assert.equal(s.requests.length, 2);
  assert.deepEqual(s.requests[0].body, s.requests[1].body);
});

for (const [name, replace] of [
  ["room", (s) => { s.ui.state = { ...s.state, room: { ...s.state.room, id: "other-room" } }; }],
  ["player", (s) => { s.ui.state = { ...s.state, me: { id: "other-player", is_host: true } }; }],
  ["host role", (s) => { s.ui.state = { ...s.state, me: { ...s.state.me, is_host: false } }; }],
  ["session", (s) => { s.ui.state = null; }],
]) {
  test(`a changed ${name} while activating audio cannot receive the old start command`, async () => {
    const gate = deferred();
    const s = session({ enable: async (status) => {
      await gate.promise;
      Object.assign(status, { unlocked: true, leaseId: "lease" });
    } });
    const first = s.action("start");
    replace(s);
    gate.resolve();
    await first;
    assert.equal(s.requests.length, 0);
    assert.deepEqual(s.notices, []);
    assert.equal(s.ui.pending, false);
  });
}

test("audio activation retains the clicked room revision and a later click starts the new revision", async () => {
  const gate = deferred();
  const s = session({ enable: async (status) => {
    await gate.promise;
    Object.assign(status, { unlocked: true, leaseId: "lease" });
  }, api: async (_, { body }) => {
    if (body.room_revision !== s.ui.state.room.revision) throw new Error("Room changed");
  } });
  const first = s.action("start");
  s.ui.state = { ...s.state, room: { ...s.state.room, revision: 5 } };
  gate.resolve();
  await first;
  assert.equal(s.requests[0].body.room_revision, 4);
  assert.deepEqual(s.notices, ["Room changed"]);
  await s.action("start");
  assert.equal(s.requests[1].body.room_revision, 5);
  assert.notEqual(s.requests[0].body.request_id, s.requests[1].body.request_id);
});

test("room eligibility blocks audio activation as well as start requests", async () => {
  for (const alter of [
    (s) => { s.state.me.is_host = false; },
    (s) => { s.state.players.pop(); },
    (s) => { s.state.players[1].song_count = 9; },
    (s) => { s.ui.disconnected = true; },
    (s) => { s.ui.pending = "setting"; },
    (s) => { s.ui.state = null; },
  ]) {
    const s = session();
    alter(s);
    await s.action("start");
    assert.deepEqual(s.enables, []);
    assert.deepEqual(s.requests, []);
  }
});
