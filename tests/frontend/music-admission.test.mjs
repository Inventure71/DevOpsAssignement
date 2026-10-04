import test from "node:test";
import assert from "node:assert/strict";
import { createMusicAdmission } from "../../frontend/application/music-admission.mjs";
import { createActions } from "../../frontend/application/actions.mjs";
import { createModel } from "../../frontend/application/state.mjs";
import { screenKey } from "../../frontend/application/screen-host.mjs";

function session(api) {
  const ui = { roomId: "old-room", page: "play", state: {} };
  const jobs = new Map();
  const requests = [], admissions = [], urls = [], navigation = [];
  const location = {
    origin: "http://127.0.0.1:8000",
    href: "http://127.0.0.1:8000/?spotify=processing&join=ABC123",
    assign: (url) => navigation.push(url),
  };
  let nextJob = 0;
  const controller = createMusicAdmission({
    ui,
    api: async (...args) => {
      requests.push(args);
      return api(...args);
    },
    admitted: async (receipt) => admissions.push(receipt),
    render() {},
    location,
    history: { replaceState: (_, __, url) => urls.push(url.href) },
    schedule: (callback, delay) => {
      const id = ++nextJob;
      jobs.set(id, { callback, delay });
      return id;
    },
    cancel: (id) => jobs.delete(id),
  });
  async function advance() {
    const [id, job] = jobs.entries().next().value;
    jobs.delete(id);
    job.callback();
    await new Promise(setImmediate);
  }
  return { controller, ui, jobs, requests, admissions, urls, navigation, advance };
}

const configured = {
  enabled: true,
  maximum_players: 5,
  application_url: "http://127.0.0.1:8000/",
};

test("Normal admission checks configuration and redirects using server cookie authorization", async () => {
  const values = {
    "/api/music/spotify/config": configured,
    "/api/music/spotify/admissions": {
      authorization_url: "https://accounts.spotify.com/authorize?state=receipt",
    },
  };
  const s = session((url) => values[url]);
  const fields = { nickname: "Jules", character_id: "coral", room_id: "room" };
  await s.controller.start(fields);
  assert.deepEqual(s.requests[1], [
    "/api/music/spotify/cancel", { method: "POST", body: {} },
  ]);
  assert.deepEqual(s.requests[2], [
    "/api/music/spotify/admissions", { method: "POST", body: fields },
  ]);
  assert.deepEqual(s.navigation, [values["/api/music/spotify/admissions"].authorization_url]);
  assert.equal(s.jobs.size, 0);
});

test("unconfigured Spotify and mismatched callback origin stop before creating admission", async () => {
  const missing = session(() => ({ ...configured, enabled: false }));
  await assert.rejects(missing.controller.start({}), /not configured/);
  assert.equal(missing.requests.length, 1);
  const mismatch = session(() => ({ ...configured, application_url: "https://game.example/" }));
  await assert.rejects(mismatch.controller.start({}), /configured game address/);
  assert.equal(mismatch.ui.canonicalUrl, "https://game.example/");
  assert.equal(mismatch.requests.length, 1);
  assert.deepEqual(mismatch.navigation, []);
});

test("LAN sign-in never sends another device to the server's loopback address", async () => {
  const s = session(() => ({ ...configured, requires_shared_url: true }));
  s.ui.canonicalUrl = "http://127.0.0.1:8000/";
  await assert.rejects(s.controller.start({}), /server computer only/);
  assert.equal(s.ui.canonicalUrl, null);
  assert.equal(s.requests.length, 1);
  assert.deepEqual(s.navigation, []);
});

test("callback restores imported room only after a complete receipt, then stops polling", async () => {
  let calls = 0;
  const admission = { room_id: "new-room", player_id: "player", code: "ABC123" };
  const s = session(() => ++calls === 1
    ? { status: "processing" }
    : { status: "complete", admission });
  await s.controller.resume();
  assert.equal(s.ui.roomId, null, "a stale saved room does not obscure callback progress");
  assert.equal(screenKey({ ui: s.ui }), "music-import");
  assert.deepEqual(s.admissions, []);
  assert.equal(s.jobs.size, 1);
  await s.advance();
  assert.deepEqual(s.admissions, [admission]);
  assert.equal(s.ui.musicImport, null);
  assert.equal(s.jobs.size, 0);
  assert.equal(new URL(s.urls[0]).searchParams.has("spotify"), false);
});

for (const [name, error] of [
  ["denied authorization", { code: "denied", message: "Spotify authorization was denied." }],
  ["insufficient history", { code: "insufficient_playable_songs", message: "Not enough playable songs.",
    details: { candidate_count: 60, playable_count: 4 } }],
]) {
  test(`${name} retains diagnostics, stops polling and never admits or falls back to Demo`, async () => {
    const s = session(() => ({ status: "failed", error }));
    await s.controller.resume();
    assert.deepEqual(s.ui.musicImport, { status: "failed", error });
    assert.equal(s.ui.error, error);
    assert.equal(screenKey({ ui: s.ui }), "music-import");
    assert.deepEqual(s.admissions, []);
    assert.equal(s.jobs.size, 0);
    assert.equal(s.requests.length, 1);
    assert.equal(new URL(s.urls[0]).searchParams.has("spotify"), false);
  });
}

test("an invalid OAuth callback shows verification failure without polling or cancelling a valid receipt", async () => {
  const s = session(() => { throw new Error("Must not be called"); });
  await s.controller.resume("error");
  assert.match(s.ui.error.message, /verification failed/);
  assert.equal(s.ui.musicImport.status, "failed");
  assert.deepEqual(s.requests, []);
  assert.equal(s.jobs.size, 0);
  assert.equal(new URL(s.urls[0]).searchParams.has("spotify"), false);
});

test("expired receipts stay visible rather than silently returning to entry", async () => {
  const s = session(() => { throw Object.assign(new Error("Sign-in expired."), { status: 401 }); });
  await s.controller.resume();
  assert.equal(s.ui.musicImport.status, "failed");
  assert.equal(s.ui.musicImport.error.message, "Sign-in expired.");
  assert.equal(s.jobs.size, 0);
});

test("connection failures retry finitely and manual retry resumes the existing receipt", async () => {
  let online = false;
  const s = session(() => {
    if (!online) throw new Error("Offline");
    return { status: "complete", admission: { room_id: "room" } };
  });
  await s.controller.resume();
  await s.advance();
  await s.advance();
  assert.equal(s.ui.musicImport.status, "interrupted");
  assert.equal(s.jobs.size, 0);
  assert.equal(s.urls.length, 0, "callback URL stays recoverable across reloads");
  online = true;
  await s.controller.resume();
  assert.equal(s.admissions.length, 1);
  assert.equal(s.requests.length, 4);
});

test("leaving the page aborts polling and ignores a late import receipt", async () => {
  let resolve;
  const s = session(() => new Promise((done) => { resolve = done; }));
  const pending = s.controller.resume();
  s.controller.stop();
  assert.equal(s.requests[0][1].signal.aborted, true);
  resolve({ status: "complete", admission: { room_id: "room" } });
  await pending;
  assert.deepEqual(s.admissions, []);
  assert.equal(s.jobs.size, 0);
});

function actionsSession(api, mode = "normal") {
  const model = createModel({ getItem: () => null, setItem() {}, removeItem() {} });
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
    musicAdmission: { start: async (fields) => oauth.push(fields) },
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
  assert.deepEqual(s.oauth, [{ nickname: "Jules", character_id: "coral" }]);
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
  assert.deepEqual(s.oauth, [{ nickname: "Jules", character_id: "coral", room_id: "normal-room" }]);
  code = "room_full";
  await s.action("admit");
  assert.equal(s.oauth.length, 1);
  assert.equal(s.model.ui.error.message, "Sign in required");
  assert.equal(s.model.ui.pending, false);
});
