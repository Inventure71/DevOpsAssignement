import test from "node:test";
import assert from "node:assert/strict";
import { createMusicAdmission } from "../../frontend/application/music-admission.mjs";
import { createActions } from "../../frontend/application/actions.mjs";
import { createModel } from "../../frontend/application/state.mjs";
import { screenKey } from "../../frontend/application/screen-host.mjs";

function actionsSession(api, mode = "normal") {
  const model = createModel();
  model.ui.draftNickname = " Jules ";
  model.ui.draftCode = "ABC123";
  model.ui.launchStatus = "ready";
  model.ui.mode = mode;
  model.ui.launchConfig = { launch_mode: mode, modes: {
    demo: { enabled: true, reason: null },
    normal: { enabled: mode === "normal", reason: mode === "normal" ? null : "Unavailable in this session." },
  } };
  const oauth = [], admissions = [], errors = [];
  const transport = { api, path: (suffix) => suffix };
  const action = createActions({ model, transport, audio: {}, runtime: {},
    render() {}, notice: (message) => errors.push(message), forgetRoom() {},
    musicAdmission: { open: async (fields) => oauth.push(fields) },
    admitted: async (receipt) => admissions.push(receipt),
  });
  return { model, action, oauth, admissions, errors };
}

test("admission errors stay in the form instead of producing a duplicate toast", async () => {
  const s = actionsSession(async () => { throw new Error("Cannot join this room."); });
  s.model.ui.screen = "join";
  await s.action("admit");
  assert.deepEqual(s.model.ui.error, { message: "Cannot join this room." });
  assert.deepEqual(s.errors, []);
  assert.equal(s.model.ui.pending, false);
});

for (const joining of [false, true]) {
  test(`HTTPS admission recovery preserves ${joining ? "the invitation" : "Demo form"}`, async () => {
    const s = actionsSession(async (url) => {
      if (url.includes("room-codes")) return { room_id: "demo-room", mode: "demo" };
      const error = new Error("Open the shared HTTPS game address to create or join a room.");
      error.code = "session_https_required";
      error.details = { application_url: "https://game.example/" };
      throw error;
    }, "demo");
    s.model.ui.mode = "demo";
    s.model.ui.screen = joining ? "join" : "create";
    await s.action("admit");
    assert.equal(s.model.ui.canonicalUrl, joining
      ? "https://game.example/?join=ABC123" : "https://game.example/");
    assert.match(s.model.ui.error.message, /HTTPS/);
    assert.equal(s.model.ui.roomId, null);
    assert.equal(s.model.ui.draftNickname, " Jules ");
    assert.equal(s.model.ui.pending, false);
    assert.deepEqual(s.admissions, []);
    assert.deepEqual(s.errors, []);
  });
}

test("a real launch lets the host choose Spotify or Demo and switch back", async () => {
  const requests = [];
  const s = actionsSession(async (...args) => {
    requests.push(args);
    return { room_id: "demo-room" };
  });
  await s.action("admit");
  assert.deepEqual(s.oauth, [{ nickname: "Jules", character_id: "coral", mode: "normal" }]);
  assert.deepEqual(requests, []);
  await s.action("entry-mode", "demo");
  assert.equal(s.model.ui.mode, "demo");
  await s.action("admit");
  assert.deepEqual(requests[0], ["/api/rooms", { method: "POST", body: {
    nickname: "Jules", character_id: "coral", mode: "demo",
  } }]);
  assert.deepEqual(s.admissions, [{ room_id: "demo-room" }]);
  await s.action("entry-mode", "normal");
  await s.action("admit");
  assert.equal(s.model.ui.mode, "normal");
  assert.equal(s.oauth.length, 2);
  assert.equal(requests.length, 1);
});

test("a Demo launch creates Demo rooms and cannot switch to Spotify", async () => {
  const requests = [];
  const s = actionsSession(async (...args) => {
    requests.push(args);
    return { room_id: "demo-room" };
  }, "demo");
  await s.action("entry-mode", "normal");
  assert.equal(s.model.ui.mode, "demo");
  await s.action("admit");
  assert.equal(requests[0][1].body.mode, "demo");
  assert.deepEqual(s.oauth, []);
  assert.deepEqual(s.admissions, [{ room_id: "demo-room" }]);
});

test("Normal join restores its room cookie before attempting Spotify authorization", async () => {
  const s = actionsSession(async (url) => url.includes("room-codes")
    ? { room_id: "normal-room", mode: "normal" }
    : { room_id: "normal-room", player_id: "existing" });
  s.model.ui.screen = "join";
  await s.action("admit");
  assert.deepEqual(s.oauth, []);
  assert.equal(s.admissions[0].player_id, "existing");
});

test("new Normal join authorizes only when server specifically requires sign-in", async () => {
  let code = "music_sign_in_required";
  const s = actionsSession(async (url) => {
    if (url.includes("room-codes")) return { room_id: "normal-room", mode: "normal" };
    const error = new Error("Sign in required");
    error.code = code;
    throw error;
  });
  s.model.ui.screen = "join";
  await s.action("admit");
  assert.deepEqual(s.oauth, [{ nickname: "Jules", character_id: "coral", mode: "normal", room_id: "normal-room" }]);
  code = "room_full";
  await s.action("admit");
  assert.equal(s.oauth.length, 1);
  assert.equal(s.model.ui.error.message, "Sign in required");
  assert.equal(s.model.ui.pending, false);
});

const fields = { nickname: "Jules", character_id: "coral", mode: "normal" };
const admissionId = "connection-A";
const admission = { room_id: "new-room", player_id: "player", code: "ABC123" };
const configured = { providers: {
  spotify: { id: "spotify", label: "Spotify", enabled: true, application_url: "http://127.0.0.1:8000/" },
  apple: { id: "apple", label: "Apple Music", enabled: false, reason: "Coming later" },
} };
const authorization = { kind: "redirect", url: "https://accounts.spotify.com/authorize?state=receipt" };
function session(api, saved = new Map(), options = {}) {
  const ui = { roomId: "old-room", page: "play", state: {} };
  const jobs = new Map(), requests = [], admissions = [], urls = [], navigation = [];
  const location = { origin: "http://127.0.0.1:8000", href: "http://127.0.0.1:8000/?music=processing&join=ABC123", assign: (url) => navigation.push(url) };
  let nextJob = 0;
  const controller = createMusicAdmission({ ui,
    api: async (...args) => { requests.push(args); return api(...args); },
    admitted: async (receipt) => { admissions.push(receipt); ui.roomId = receipt.room_id; },
    render() {}, location, history: { replaceState: (_, __, url) => urls.push(url.href) },
    storage: { getItem: (key) => saved.get(key), setItem: (key, value) => saved.set(key, value), removeItem: (key) => saved.delete(key) },
    schedule: (callback, delay) => { const id = ++nextJob; jobs.set(id, { callback, delay }); return id; }, cancel: (id) => jobs.delete(id),
    ...options,
  });
  async function advance() { const [id, job] = jobs.entries().next().value; jobs.delete(id); job.callback(); await new Promise(setImmediate); }
  return { controller, ui, jobs, requests, admissions, urls, navigation, advance, saved };
}
function responses(url) {
  if (url === "/api/music/config") return configured;
  if (url === "/api/music/cancel") return { status: "cancelled" };
  if (url === "/api/music/admissions") return { authorization };
  if (url === "/api/music/acknowledge") return { acknowledged: true };
  assert.fail(`Unexpected request: ${url}`);
}

test("Real form stages connection with only a configuration read and no membership or OAuth mutation", async () => {
  const s = session(responses);
  await s.controller.open(fields, "ABC123");
  assert.deepEqual(s.requests.map(([url]) => url), ["/api/music/config"]);
  assert.deepEqual(s.ui.musicConnection.fields, fields);
  assert.equal(s.ui.musicConnection.code, "ABC123");
  assert.equal(screenKey({ ui: s.ui }), "music-connection");
  assert.deepEqual(s.navigation, []);
  assert.deepEqual(s.admissions, []);
});

test("provider selection cancels previous authorization and posts a provider-neutral admission", async () => {
  const s = session(responses);
  await s.controller.open({ ...fields, room_id: "room" }, "ABC123");
  await s.controller.start("spotify");
  assert.deepEqual(s.requests.slice(1).map(([url]) => url), ["/api/music/cancel", "/api/music/config", "/api/music/admissions"]);
  assert.deepEqual(s.requests[3][1].body, { nickname: "Jules", character_id: "coral", room_id: "room", provider: "spotify" });
  assert.deepEqual(s.navigation, [authorization.url]);
});

for (const [name, capability, message] of [
  ["unavailable provider", { enabled: false, reason: "Music unavailable" }, /Music unavailable/],
  ["wrong game origin", { application_url: "https://game.example/" }, /configured game address/],
  ["LAN loopback callback", { requires_shared_url: true }, /server computer only/],
]) test(`${name} cannot start authorization`, async () => {
  const s = session((url) => url === "/api/music/config" ? { providers: { ...configured.providers, spotify: { ...configured.providers.spotify, ...capability } } } : responses(url));
  await s.controller.open(fields, "ABC123");
  await assert.rejects(s.controller.start(), message);
  assert.equal(s.requests.some(([url]) => url === "/api/music/admissions"), false);
  assert.deepEqual(s.navigation, []);
  if (name === "wrong game origin") assert.equal(s.ui.canonicalUrl, "https://game.example/?join=ABC123");
  else assert.equal(s.ui.canonicalUrl, null);
});

test("Apple Music is explicitly deferred and cannot create an import", async () => {
  const s = session(responses);
  await s.controller.open(fields);
  await assert.rejects(s.controller.start("apple"), /Coming later/);
  assert.equal(s.requests.some(([url]) => url === "/api/music/admissions"), false);
});

for (const url of ["https://evil.example/authorize", "https://accounts.spotify.com/token", "https://user:password@accounts.spotify.com/authorize"]) {
  test(`reject unauthorized redirect ${url}`, async () => {
    const s = session((path) => path === "/api/music/admissions" ? { authorization: { kind: "redirect", url } } : responses(path));
    await s.controller.open(fields);
    await assert.rejects(s.controller.start(), /authorization address/);
    assert.deepEqual(s.navigation, []);
  });
}

test("callback polling restores draft and admits only after complete receipt", async () => {
  let statusCalls = 0;
  const s = session((url) => url === "/api/music/status" ? ++statusCalls === 1
    ? { status: "processing", connection: { ...fields, room_id: "room", provider: "spotify" } }
    : { status: "complete", admission_id: admissionId, admission } : responses(url));
  await s.controller.resume();
  assert.equal(s.ui.roomId, null);
  assert.equal(s.ui.character, "coral");
  assert.equal(s.ui.draftNickname, "Jules");
  assert.equal(screenKey({ ui: s.ui }), "music-import");
  assert.deepEqual(s.admissions, []);
  await s.advance();
  assert.deepEqual(s.admissions, [admission]);
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.jobs.size, 0);
  assert.equal(new URL(s.urls[0]).searchParams.has("music"), false);
});

for (const callback of [undefined, "error"]) test(`failed callback ${callback} restores server identity at provider selection`, async () => {
  const error = { code: "music_authorization_denied", message: "Music authorization denied." };
  const s = session((url) => url === "/api/music/status" ? { status: "failed", connection: { ...fields, room_id: "room" }, error } : responses(url));
  await s.controller.resume(callback);
  assert.equal(screenKey({ ui: s.ui }), "music-connection");
  assert.deepEqual(s.ui.musicConnection.fields, { ...fields, room_id: "room" });
  assert.equal(s.ui.error, error);
  assert.equal(s.jobs.size, 0);
  assert.deepEqual(s.admissions, []);
});

test("full reload recovers a nonsecret draft when a callback receipt expires", async () => {
  const first = session(responses);
  await first.controller.open({ ...fields, room_id: "room" }, "ABC123");
  const s = session((url) => { if (url === "/api/music/status") throw Object.assign(new Error("Sign-in expired."), { status: 401 }); return responses(url); }, first.saved);
  await s.controller.recover();
  assert.equal(s.ui.draftNickname, "Jules");
  assert.equal(s.ui.draftCode, "ABC123");
  assert.equal(screenKey({ ui: s.ui }), "music-connection");
  assert.deepEqual(Object.keys(JSON.parse([...first.saved.values()][0])).sort(), ["code", "fields"]);
});

for (const operation of ["back", "start"]) test(`${operation} accepts completion that won the cancellation race`, async () => {
  const s = session((url) => url === "/api/music/cancel" ? { status: "complete", admission_id: admissionId, connection: fields, admission } : responses(url));
  await s.controller.open(fields);
  await s.controller[operation]();
  assert.deepEqual(s.admissions, [admission]);
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.requests.some(([url]) => url === "/api/music/admissions"), false);
  assert.deepEqual(s.navigation, []);
});

test("Back waits for cancellation before clearing the draft and keeps form identity", async () => {
  let resolve;
  const s = session((url) => url === "/api/music/cancel" ? new Promise((done) => { resolve = done; }) : responses(url));
  await s.controller.open(fields);
  const pending = s.controller.back();
  await new Promise(setImmediate);
  assert.ok(s.ui.musicConnection);
  resolve({ status: "cancelled" });
  await pending;
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.ui.draftNickname, "Jules");
  assert.deepEqual(s.admissions, []);
});

test("cancellation failure preserves the staged draft and a retry can finish cancellation", async () => {
  let online = false;
  const s = session((url) => { if (url === "/api/music/cancel" && !online) throw new Error("Offline"); return responses(url); });
  await s.controller.open(fields);
  await assert.rejects(s.controller.back(), /Offline/);
  assert.deepEqual(s.ui.musicConnection.fields, fields);
  assert.equal(s.saved.size, 1);
  online = true;
  await s.controller.back();
  assert.equal(s.ui.musicConnection, null);
});

test("late config cannot overwrite a newer staged draft or recreate a cancelled screen", async () => {
  let resolve;
  let count = 0;
  const s = session((url) => url === "/api/music/config" && ++count === 1 ? new Promise((done) => { resolve = done; }) : responses(url));
  const opening = s.controller.open(fields);
  await s.controller.open({ ...fields, nickname: "Other" });
  resolve({ providers: { spotify: { enabled: false } } });
  await opening;
  assert.equal(s.ui.musicConnection.fields.nickname, "Other");
  assert.equal(s.ui.musicConnection.providers.spotify.enabled, true);
  await s.controller.back();
  assert.equal(s.ui.musicConnection, null);
});

test("Back serializes behind in-flight admission and late admission never redirects", async () => {
  let resolve;
  const s = session((url) => url === "/api/music/admissions" ? new Promise((done) => { resolve = done; }) : responses(url));
  await s.controller.open(fields);
  const start = s.controller.start();
  await new Promise(setImmediate);
  const back = s.controller.back();
  resolve({ authorization });
  await Promise.all([start, back]);
  assert.deepEqual(s.navigation, []);
  assert.equal(s.requests.filter(([url]) => url === "/api/music/cancel").length, 2);
  assert.equal(s.ui.musicConnection, null);
});

test("pagehide aborts local polling without cancelling server authorization or accepting stale completion", async () => {
  let resolve;
  const s = session(() => new Promise((done) => { resolve = done; }));
  const pending = s.controller.resume();
  s.controller.stop();
  assert.equal(s.requests[0][1].signal.aborted, true);
  resolve({ status: "complete", admission_id: admissionId, admission });
  await pending;
  assert.deepEqual(s.admissions, []);
  assert.equal(s.requests.some(([url]) => url === "/api/music/cancel"), false);
});

test("offline polling retries finitely, and manual retry uses the existing receipt", async () => {
  let online = false;
  const s = session(() => { if (!online) throw new Error("Offline"); return { status: "complete", admission_id: admissionId, admission }; });
  await s.controller.resume();
  await s.advance();
  await s.advance();
  assert.equal(s.ui.musicImport.status, "interrupted");
  assert.equal(s.jobs.size, 0);
  online = true;
  await s.controller.resume();
  assert.deepEqual(s.admissions, [admission]);
  assert.equal(s.requests.filter(([url]) => url === "/api/music/status").length, 4);
});

test("accepted room retires the completed receipt so a later Real room gets fresh authorization", async () => {
  let complete = true;
  const s = session((url) => {
    if (url === "/api/music/cancel" && complete) return { status: "complete", admission_id: admissionId, connection: fields, admission };
    if (url === "/api/music/acknowledge") { assert.equal(s.ui.roomId, admission.room_id); complete = false; return { acknowledged: true }; }
    return responses(url);
  });
  await s.controller.open(fields);
  await s.controller.start();
  assert.deepEqual(s.admissions, [admission]);
  assert.deepEqual(s.navigation, []);
  s.ui.roomId = null;
  await s.controller.open({ ...fields, nickname: "New room" });
  await s.controller.start();
  assert.deepEqual(s.navigation, [authorization.url]);
  assert.equal(s.requests.filter(([url]) => url === "/api/music/acknowledge").length, 1);
  assert.deepEqual(s.requests.find(([url]) => url === "/api/music/acknowledge")[1].body,
    { admission_id: admissionId });
});

test("a delayed tab acknowledges its original connection after another tab connects", async () => {
  let finishAcceptance;
  let current = { status: "complete", admission_id: admissionId, connection: fields, admission };
  const acknowledgements = [];
  const api = (url, options) => {
    if (url === "/api/music/status") return current;
    if (url === "/api/music/acknowledge") {
      acknowledgements.push(options.body);
      return { acknowledged: false };
    }
    return responses(url);
  };
  const oldTab = session(api, new Map(), { admitted: async (receipt) => {
    await new Promise((resolve) => { finishAcceptance = resolve; });
    oldTab.ui.roomId = receipt.room_id;
  } });
  const accepting = oldTab.controller.resume();
  await new Promise(setImmediate);
  assert.equal(typeof finishAcceptance, "function");
  current = { status: "complete", admission_id: "connection-B", connection: fields,
    admission: { ...admission, room_id: "other-room", player_id: "other-player" } };
  const newTab = session(api);
  await newTab.controller.resume();
  finishAcceptance();
  await accepting;
  assert.deepEqual(acknowledgements,
    [{ admission_id: "connection-B" }, { admission_id: admissionId }]);
  assert.equal(oldTab.ui.roomId, admission.room_id);
  assert.equal(newTab.ui.roomId, "other-room");
  assert.equal(oldTab.ui.error, null);
});

test("acknowledgment failure keeps the successfully accepted room", async () => {
  const s = session((url) => {
    if (url === "/api/music/status") return { status: "complete", admission_id: admissionId, connection: fields, admission };
    if (url === "/api/music/acknowledge") throw new Error("Offline");
    return responses(url);
  });
  await s.controller.resume();
  assert.equal(s.ui.roomId, admission.room_id);
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.ui.error, null);
});

test("stale config during start cannot create admission or redirect after Back", async () => {
  let resolve, configCalls = 0;
  const s = session((url) => url === "/api/music/config" && ++configCalls === 2 ? new Promise((done) => { resolve = done; }) : responses(url));
  await s.controller.open(fields);
  const start = s.controller.start();
  await new Promise(setImmediate);
  const back = s.controller.back();
  resolve(configured);
  await Promise.all([start, back]);
  assert.equal(s.requests.some(([url]) => url === "/api/music/admissions"), false);
  assert.deepEqual(s.navigation, []);
  assert.equal(s.ui.musicConnection, null);
});

test("stale status cannot replace identity from a newer connection draft", async () => {
  let resolve;
  const s = session((url) => url === "/api/music/status" ? new Promise((done) => { resolve = done; }) : responses(url));
  const resume = s.controller.resume();
  await s.controller.open({ ...fields, nickname: "Other" });
  resolve({ status: "failed", connection: fields });
  await resume;
  assert.equal(s.ui.musicConnection.fields.nickname, "Other");
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.error, null);
});

test("admission controller uses an injected authorization strategy without Spotify capabilities", async () => {
  const capability = { id: "alternative", label: "Alternative source", enabled: true };
  const calls = [];
  const s = session((url) => {
    if (url === "/api/music/config") return { providers: { alternative: capability } };
    if (url === "/api/music/admissions") return { authorization: { kind: "redirect", url: "https://music.example/connect" } };
    return responses(url);
  }, new Map(), { authorizers: { alternative: {
    application: (provider, location, code) => { calls.push([provider, location.origin, code]); return null; },
    authorization: (response) => { calls.push(response); return response.url; },
  } } });
  await s.controller.open(fields, "ABC123");
  assert.deepEqual(s.ui.musicConnection.providers, { alternative: capability });
  await s.controller.start("alternative");
  assert.deepEqual(s.requests.find(([url]) => url === "/api/music/admissions")[1].body,
    { nickname: "Jules", character_id: "coral", provider: "alternative" });
  assert.deepEqual(calls, [[capability, "http://127.0.0.1:8000", "ABC123"], { kind: "redirect", url: "https://music.example/connect" }]);
  assert.deepEqual(s.navigation, ["https://music.example/connect"]);
});

for (const providers of [null, [], { alternative: { id: "wrong", label: "Alternative", enabled: true } }, { alternative: { id: "alternative", enabled: true } }, { alternative: { id: "alternative", label: "Alternative", enabled: "yes" } }]) {
  test(`generic capability validation rejects malformed metadata ${JSON.stringify(providers)}`, async () => {
    const s = session(() => ({ providers }));
    await s.controller.open(fields);
    assert.equal(s.ui.musicConnection.configError, "The music configuration is invalid.");
    assert.equal(s.ui.musicConnection.providers, undefined);
  });
}

test("queued processing status cannot renew polling after a newer Back cancels the attempt", async () => {
  let resolve, cancelCalls = 0;
  const s = session((url) => {
    if (url === "/api/music/cancel" && ++cancelCalls === 1) return new Promise((done) => { resolve = done; });
    if (url === "/api/music/status") return { status: "processing", connection: fields };
    return responses(url);
  });
  await s.controller.open(fields);
  const start = s.controller.start();
  await new Promise(setImmediate);
  const resume = s.controller.resume();
  await new Promise(setImmediate);
  const back = s.controller.back();
  resolve({ status: "cancelled" });
  await Promise.all([start, resume, back]);
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.jobs.size, 0);
  assert.deepEqual(s.admissions, []);
});

test("a cancelled server receipt returns safely to providers without admitting an old room", async () => {
  const first = session(responses);
  await first.controller.open(fields);
  const s = session((url) => url === "/api/music/status" ? { status: "cancelled" } : responses(url), first.saved);
  await s.controller.recover();
  assert.equal(screenKey({ ui: s.ui }), "music-connection");
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.error, null);
  assert.equal(s.jobs.size, 0);
  assert.deepEqual(s.admissions, []);
});

test("pagehide while heartbeat/state restoration is blocked preserves completion for pageshow recovery", async () => {
  let finishRestoration;
  const restoration = new Promise((resolve) => { finishRestoration = resolve; });
  let complete = true, accepted = 0;
  const s = session((url) => {
    if (url === "/api/music/status") {
      if (!complete) throw Object.assign(new Error("Sign-in expired."), { status: 401 });
      return { status: "complete", admission_id: admissionId, connection: fields, admission };
    }
    if (url === "/api/music/acknowledge") {
      complete = false;
      return { acknowledged: true };
    }
    return responses(url);
  }, new Map(), { admitted: async (receipt) => {
    accepted++;
    // The real admitted callback remembers membership before heartbeat/state.
    s.ui.roomId = receipt.room_id;
    await restoration;
  } });
  const pending = s.controller.resume();
  await new Promise(setImmediate);
  assert.equal(accepted, 1);
  assert.equal(s.ui.roomId, admission.room_id);
  s.controller.stop();
  finishRestoration();
  await pending;
  assert.equal(complete, true, "an interrupted restoration must retain its server receipt");
  assert.equal(s.requests.some(([url]) => url === "/api/music/acknowledge"), false);
  assert.equal(s.ui.musicImport.status, "processing");
  await s.controller.resume();
  assert.equal(accepted, 2);
  assert.equal(s.ui.roomId, admission.room_id);
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.ui.error, null);
  assert.equal(s.requests.filter(([url]) => url === "/api/music/acknowledge").length, 1);
});

test("pagehide during acknowledgment keeps accepted room visible without resuming a retired import", async () => {
  let finishAcknowledgment;
  let complete = true;
  const s = session((url) => {
    if (url === "/api/music/status") {
      if (!complete) throw Object.assign(new Error("Sign-in expired."), { status: 401 });
      return { status: "complete", admission_id: admissionId, connection: fields, admission };
    }
    if (url === "/api/music/acknowledge") return new Promise((resolve) => {
      finishAcknowledgment = () => { complete = false; resolve({ acknowledged: true }); };
    });
    return responses(url);
  });
  await s.controller.open(fields);
  const pending = s.controller.resume();
  await new Promise(setImmediate);
  assert.equal(typeof finishAcknowledgment, "function");
  assert.equal(s.ui.roomId, admission.room_id);
  assert.equal(s.ui.musicImport, null, "membership is published before receipt retirement");
  assert.equal(s.ui.musicConnection, null);
  assert.equal(s.saved.size, 0);
  assert.equal(new URL(s.urls.at(-1)).searchParams.has("music"), false);
  s.controller.stop();
  finishAcknowledgment();
  await pending;
  // BFCache pageshow only resumes an import still present in UI; this session
  // instead retains roomId for the ordinary room heartbeat/state restoration.
  if (s.ui.musicImport) await s.controller.resume();
  assert.equal(complete, false);
  assert.equal(s.ui.roomId, admission.room_id);
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.ui.error, null);
  assert.equal(s.requests.filter(([url]) => url === "/api/music/status").length, 1);
  assert.deepEqual(s.admissions, [admission]);
});

test("pageshow refreshes a staged connection after pagehide interrupts configuration", async () => {
  const model = createModel();
  Object.assign(model.ui, {
    draftNickname: " Jules ", character: "sage", launchStatus: "ready", mode: "normal",
    launchConfig: { modes: { normal: { enabled: true }, demo: { enabled: true } } },
  });
  const requests = [];
  let finishOldConfiguration;
  const api = async (url) => {
    requests.push(url);
    assert.equal(url, "/api/music/config");
    if (requests.length === 1)
      return new Promise((resolve) => { finishOldConfiguration = resolve; });
    return configured;
  };
  const controller = createMusicAdmission({
    ui: model.ui, api, render() {}, admitted() { assert.fail("configuration cannot admit a player"); },
    location: { href: "http://127.0.0.1:8000/", origin: "http://127.0.0.1:8000" },
    history: { replaceState() {} },
    storage: { getItem: () => null, setItem() {}, removeItem() {} },
  });
  const action = createActions({ model, transport: { api }, musicAdmission: controller,
    render() {}, notice() {} });
  const opening = action("admit");
  await new Promise(setImmediate);
  assert.equal(model.ui.musicConnection.loading, true);
  controller.stop(); // The application's pagehide handler.
  await controller.resumePage(); // The application's persisted pageshow handler.
  assert.equal(model.ui.musicConnection.loading, false);
  assert.equal(model.ui.musicConnection.providers.spotify.enabled, true);
  // A late response from the page before suspension must not overwrite this one.
  finishOldConfiguration({ providers: { spotify: { ...configured.providers.spotify, enabled: false } } });
  await opening;
  assert.deepEqual(model.ui.musicConnection.fields,
    { nickname: "Jules", character_id: "sage", mode: "normal" });
  assert.equal(model.ui.musicConnection.providers.spotify.enabled, true);
  assert.equal(model.ui.musicConnection.configError, null);
  assert.equal(model.ui.pending, false);
  assert.deepEqual(requests, ["/api/music/config", "/api/music/config"]);
  assert.equal(model.ui.roomId, null);

  model.ui.musicConnection = null;
  model.rememberRoom(admission);
  await controller.resumePage();
  assert.equal(model.ui.roomId, admission.room_id);
  assert.equal(requests.length, 2, "an accepted room must use ordinary room restoration");
});

for (const [name, savedCode, screen, currentCode, recovers] of [
  ["different invitation", "OLD123", "join", "NEW123", false],
  ["new invitation after a create draft", undefined, "join", "NEW123", false],
  ["matching invitation with normalized code", "ABC123", "join", " abc123 ", true],
  ["reload without explicit invitation", "OLD123", "create", "", true],
]) {
  test(`automatic recovery respects ${name}`, async () => {
    const saved = new Map([["repeat_music_draft", JSON.stringify({
      fields: savedCode ? { ...fields, room_id: "saved-room" } : fields,
      ...(savedCode ? { code: savedCode } : {}),
    })]]);
    const s = session((url) => url === "/api/music/status"
      ? { status: "complete", admission_id: admissionId, admission }
      : responses(url), saved);
    Object.assign(s.ui, { roomId: null, state: null, screen, draftCode: currentCode,
      draftNickname: "New player", character: "rose" });
    await s.controller.recover();
    if (recovers) {
      assert.deepEqual(s.admissions, [admission]);
      assert.deepEqual(s.requests.map(([url]) => url), ["/api/music/status", "/api/music/acknowledge"]);
      assert.equal(s.ui.roomId, admission.room_id);
    } else {
      assert.deepEqual(s.requests, []);
      assert.deepEqual(s.admissions, []);
      assert.equal(s.ui.draftCode, currentCode);
      assert.equal(s.ui.draftNickname, "New player");
      assert.equal(s.ui.character, "rose");
      assert.equal(s.ui.musicConnection, undefined);
      assert.equal(s.ui.roomId, null);
      assert.equal(saved.size, 1);
    }
  });
}

for (const command of ["connect-music", "music-back"]) {
  for (const stale of [false, true]) {
    test(`${command} mutation failures ${stale ? "stay silent after pageshow" : "remain actionable in the current page"}`, async () => {
      const model = createModel();
      Object.assign(model.ui, { launchStatus: "ready",
        launchConfig: { modes: { normal: { enabled: true }, demo: { enabled: true } } } });
      let rejectMutation;
      const api = async (url) => url === "/api/music/cancel"
        ? new Promise((_, reject) => { rejectMutation = reject; }) : responses(url);
      const controller = createMusicAdmission({ ui: model.ui, api, render() {},
        admitted() { assert.fail("a failed mutation cannot admit a player"); },
        location: { origin: "http://127.0.0.1:8000", href: "http://127.0.0.1:8000/",
          assign() { assert.fail("a failed mutation cannot redirect"); } },
        history: { replaceState() {} },
      });
      await controller.open(fields);
      const action = createActions({ model, transport: { api }, musicAdmission: controller,
        render() {}, notice() { assert.fail("admission errors belong in the form"); } });
      const pending = action(command, "spotify");
      await new Promise(setImmediate);
      assert.equal(typeof rejectMutation, "function");
      if (stale) {
        controller.stop();
        await controller.resumePage();
        assert.equal(model.ui.musicConnection.loading, false);
        assert.deepEqual(model.ui.musicConnection.providers, configured.providers);
      }
      rejectMutation(new Error("Connection timed out"));
      await pending;
      if (stale) {
        assert.equal(model.ui.error, null);
        assert.equal(model.ui.musicConnection.error ?? null, null);
      } else {
        assert.deepEqual(model.ui.error, { message: "Connection timed out" });
        assert.equal(model.ui.musicConnection.error, "Connection timed out");
      }
      assert.deepEqual(model.ui.musicConnection.fields, fields);
      assert.equal(model.ui.pending, false);
    });
  }
}
