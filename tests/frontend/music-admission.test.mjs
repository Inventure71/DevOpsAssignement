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

test("denied or failed imports show an actionable error and never admit or fall back to Demo", async () => {
  const s = session(() => ({ status: "failed", error: { code: "denied", message: "Spotify authorization was denied." } }));
  await s.controller.resume();
  assert.equal(s.ui.error.code, "denied");
  assert.equal(s.ui.musicImport, null);
  assert.deepEqual(s.admissions, []);
  assert.equal(s.jobs.size, 0);
  assert.equal(s.requests.length, 1);
});

test("an invalid OAuth callback shows verification failure without polling or cancelling a valid receipt", async () => {
  const s = session(() => { throw new Error("Must not be called"); });
  await s.controller.resume("error");
  assert.match(s.ui.error.message, /verification failed/);
  assert.equal(s.ui.musicImport, null);
  assert.deepEqual(s.requests, []);
  assert.equal(s.jobs.size, 0);
  assert.equal(new URL(s.urls[0]).searchParams.has("spotify"), false);
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

function actionsSession(api) {
  const model = createModel({ getItem: () => null, setItem() {}, removeItem() {} });
  model.ui.draftNickname = " Jules ";
  model.ui.draftCode = "ABC123";
  const oauth = [], admissions = [], errors = [];
  const transport = { api, path: (suffix) => suffix };
  const action = createActions({ model, transport, audio: {}, runtime: {},
    render() {}, notice: (message) => errors.push(message), forgetRoom() {},
    musicAdmission: { start: async (fields) => oauth.push(fields) },
    admitted: async (receipt) => admissions.push(receipt),
  });
  return { model, action, oauth, admissions, errors };
}

test("host explicitly chooses Normal OAuth or Demo admission", async () => {
  const requests = [];
  const s = actionsSession(async (...args) => {
    requests.push(args);
    return { room_id: "demo-room" };
  });
  await s.action("admit");
  assert.deepEqual(s.oauth, [{ nickname: "Jules", character_id: "coral" }]);
  assert.deepEqual(requests, []);
  await s.action("entry-mode", "demo");
  await s.action("admit");
  assert.deepEqual(requests[0], ["/api/rooms", { method: "POST", body: {
    nickname: "Jules", character_id: "coral", mode: "demo",
  } }]);
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
