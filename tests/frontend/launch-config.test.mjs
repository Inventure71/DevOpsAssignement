import test from "node:test";
import assert from "node:assert/strict";
import { createLaunchConfig, modeAvailable } from "../../frontend/application/launch-config.mjs";
import { createModel } from "../../frontend/application/state.mjs";
import { createActions } from "../../frontend/application/actions.mjs";
import { createRuntime } from "../../frontend/application/runtime.mjs";
import { screenKey } from "../../frontend/application/screen-host.mjs";

function model() {
  return createModel({ getItem: () => null, setItem() {}, removeItem() {} });
}

function config(mode, enabled = true) {
  return { launch_mode: mode, modes: {
    demo: { enabled: true, reason: null },
    normal: { enabled: mode === "normal" && enabled, reason: mode === "normal" && enabled ? null : "Unavailable in this session." },
  } };
}

function actions(m, api) {
  const mutations = [], notices = [];
  const action = createActions({
    model: m, transport: { api, path: (suffix) => suffix }, audio: {}, runtime: {},
    render() {}, notice: (message) => notices.push(message), forgetRoom() {},
    musicAdmission: { start: async (fields) => mutations.push(fields) },
    admitted: async (receipt) => mutations.push(receipt),
  });
  return { action, mutations, notices };
}

for (const mode of ["demo", "normal"]) {
  test(`${mode} launch selects its available mode only after configuration is loaded`, async () => {
    const m = model();
    let resolve;
    const requests = [];
    const controller = createLaunchConfig({ ui: m.ui, render() {}, api: (url) => {
      requests.push(url);
      return new Promise((done) => { resolve = done; });
    } });
    assert.equal(modeAvailable(m.ui, mode), false);
    const first = controller.load(), second = controller.load();
    assert.equal(first, second, "Concurrent initialization shares its request");
    await new Promise(setImmediate);
    assert.equal(m.ui.launchStatus, "loading");
    assert.equal(modeAvailable(m.ui, mode), false);
    resolve(config(mode));
    assert.equal(await first, true);
    assert.deepEqual(requests, ["/api/config"]);
    assert.equal(m.ui.mode, mode);
    assert.equal(modeAvailable(m.ui, mode), true);
    assert.equal(modeAvailable(m.ui, "demo"), true);
    assert.equal(modeAvailable(m.ui, "normal"), mode === "normal");
  });
}

test("configuration failure disables admissions and retry recovers without assuming a mode", async () => {
  const m = model();
  let available = false;
  const controller = createLaunchConfig({ ui: m.ui, render() {}, api: async () => {
    if (!available) throw new Error("Offline");
    return config("demo");
  } });
  assert.equal(await controller.load(), false);
  assert.equal(m.ui.launchStatus, "error");
  assert.match(m.ui.launchError, /Try again/);
  const s = actions(m, () => assert.fail("Admission must wait for configuration"));
  await s.action("admit");
  assert.equal(m.ui.error.message, m.ui.launchError);
  assert.deepEqual(s.mutations, []);
  available = true;
  assert.equal(await controller.load(), true);
  assert.equal(m.ui.launchError, null);
  assert.equal(m.ui.mode, "demo");
});

test("invalid capabilities never enable either mode", async () => {
  for (const invalid of [null, {}, { launch_mode: "both" },
    { launch_mode: "demo", modes: { demo: { enabled: true, reason: null }, normal: { enabled: true, reason: null } } },
    { launch_mode: "normal", modes: { normal: { enabled: "yes", reason: null } } }]) {
    const m = model();
    const controller = createLaunchConfig({ ui: m.ui, render() {}, api: async () => invalid });
    assert.equal(await controller.load(), false);
    assert.equal(modeAvailable(m.ui, "demo"), false);
    assert.equal(modeAvailable(m.ui, "normal"), false);
  }
});

test("an unconfigured Normal launch selects Demo and keeps Spotify unavailable", async () => {
  const m = model();
  const controller = createLaunchConfig({ ui: m.ui, render() {}, api: async () => config("normal", false) });
  assert.equal(await controller.load(), true);
  assert.equal(m.ui.mode, "demo");
  let requests = 0;
  const s = actions(m, async () => { requests++; return { room_id: "demo-room" }; });
  await s.action("entry-mode", "normal");
  assert.equal(m.ui.mode, "demo");
  await s.action("admit");
  assert.deepEqual(s.mutations, [{ room_id: "demo-room" }]);
  assert.equal(requests, 1);
});

test("a ready server without music keeps both admissions disabled", async () => {
  const m = model();
  const unavailable = config("demo", false);
  unavailable.modes.demo = { enabled: false, reason: "Demo music is not installed on this server." };
  const controller = createLaunchConfig({ ui: m.ui, render() {}, api: async () => unavailable });
  assert.equal(await controller.load(), true);
  assert.equal(m.ui.launchStatus, "ready");
  assert.equal(modeAvailable(m.ui, "demo"), false);
  assert.equal(modeAvailable(m.ui, "normal"), false);
  const s = actions(m, () => assert.fail("Missing music must block admission"));
  await s.action("admit");
  assert.match(m.ui.error.message, /not installed/);
  assert.deepEqual(s.mutations, []);
});

for (const launch of ["demo", "normal"]) {
  test(`${launch} launch rejects a resolved Spotify room when Spotify is unavailable`, async () => {
    const m = model();
    m.ui.launchStatus = "ready";
    m.ui.launchConfig = config(launch, false);
    m.ui.mode = launch;
    m.ui.screen = "join";
    m.ui.draftCode = "ABC123";
    const requests = [];
    const s = actions(m, async (url) => {
      requests.push(url);
      return { room_id: "other-room", mode: "normal" };
    });
    await s.action("admit");
    assert.deepEqual(requests, ["/api/room-codes/ABC123"]);
    assert.match(m.ui.error.message, /Unavailable/);
    assert.deepEqual(s.mutations, []);
    assert.equal(m.ui.pending, false);
  });
}

test("a real launch joins a Demo room without Spotify admission", async () => {
  const m = model();
  m.ui.launchStatus = "ready";
  m.ui.launchConfig = config("normal");
  m.ui.screen = "join";
  m.ui.draftCode = "ABC123";
  const requests = [];
  const s = actions(m, async (url) => {
    requests.push(url);
    return url.includes("room-codes")
      ? { room_id: "demo-room", mode: "demo" }
      : { room_id: "demo-room", player_id: "guest" };
  });
  await s.action("admit");
  assert.deepEqual(requests, ["/api/room-codes/ABC123", "/api/rooms/demo-room/join"]);
  assert.deepEqual(s.mutations, [{ room_id: "demo-room", player_id: "guest" }]);
});

test("restoring an unavailable previous room returns to entry with an explanation", async () => {
  const m = model();
  m.rememberRoom({ room_id: "previous-room" });
  assert.equal(screenKey({ ui: m.ui }), "restoring");
  const notices = [];
  const runtime = createRuntime(m, { path: (suffix) => suffix, api: async () => {
    throw Object.assign(new Error("This room is unavailable in this session."), {
      status: 409, code: "mode_unavailable",
    });
  } }, {}, {}, () => {}, (message) => notices.push(message), () => m.forgetRoom());
  await runtime.refresh();
  assert.equal(m.ui.roomId, null);
  assert.equal(screenKey({ ui: m.ui }), "entry");
  assert.deepEqual(notices, ["This room is unavailable in this session."]);
});
