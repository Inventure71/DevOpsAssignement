import assert from "node:assert/strict";
import {createModel} from "../../temporary_frontend/static/js/state.js";
import {createTransport, requestId} from "../../temporary_frontend/static/js/transport.js";
import {bindActions} from "../../temporary_frontend/static/js/actions.js";
import {createRenderer} from "../../temporary_frontend/static/js/renderer.js";
import {createAudioController} from "../../temporary_frontend/static/js/audio.js";
import {createRuntime} from "../../temporary_frontend/static/js/runtime.js";
import {createViews} from "../../temporary_frontend/static/js/views.js";

// These checks exercise production modules with controlled browser/IO ports.
// They complement, rather than replace, the real browser and Python API tests.
const memoryStorage = () => {
  const values = new Map();
  return {getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key)};
};
const snapshot = (roundId = "round-1", version = 1) => ({
  room: {id: "room", code: "ABC123", revision: 1},
  me: {id: "me", is_host: true},
  players: [{id: "me", nickname: "Host", character_id: "vinyl", is_host: true, connected: true, song_count: 4}],
  settings: {answer_seconds: 20, round_count: 5, difficulty: "mixed", decoys_enabled: true},
  game: {id: "game", status: "playing", phase: "answering", state_version: version, requested_rounds: 5,
    round: {id: roundId, round_number: 1, starts_at_ms: 1000, deadline_at_ms: 21000, audio_candidate_id: "clip-0", readiness_generation: 1,
      submitted_player_ids: [], ready_player_ids: [], excluded_player_ids: [], options: [{index: 0, title: "Song", artist: "Artist"}]}},
});
const model = () => { const result = createModel(memoryStorage()); result.rememberRoom({room_id: "room"}); return result; };
const port = () => {
  const handlers = new Map();
  return {handlers, addEventListener: (event, handler) => handlers.set(event, handler)};
};
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };
let checks = 0;
async function check(name, run) { await run(); checks++; console.log(`✓ ${name}`); }

await check("HTTP LAN fallback generates valid unique command UUIDs", () => {
  const crypto = {getRandomValues: bytes => globalThis.crypto.getRandomValues(bytes)};
  const ids = Array.from({length: 100}, () => requestId(crypto));
  assert.equal(new Set(ids).size, 100);
  ids.forEach(id => assert.match(id, /^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/));
});

await check("transport sends JSON and cookies, preserves structured server errors", async () => {
  let outgoing;
  const transport = createTransport(() => "room", () => snapshot(), async (url, options) => {
    outgoing = {url, options};
    return {ok: false, status: 409, json: async () => ({error: {code: "answer_locked", message: "Already submitted", details: {round: "round-1"}}})};
  });
  await assert.rejects(transport.api(transport.roundPath("/answers"), {method: "POST", body: {song_option: 0}}), error => error.code === "answer_locked" && error.status === 409);
  assert.equal(outgoing.url, "/api/rooms/room/games/game/rounds/round-1/answers");
  assert.equal(outgoing.options.credentials, "same-origin");
  assert.equal(outgoing.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(outgoing.options.body), {song_option: 0});
});

await check("accepted answers survive a stale in-flight polling snapshot", () => {
  const store = model();
  store.applySnapshot(snapshot(), "room");
  const answer = {song_option: 0, who_player_ids: []};
  store.acceptAnswer("game", "round-1", answer);
  store.applySnapshot(snapshot(), "room");
  assert.deepEqual(store.ui.state.game.round.my_answer, answer);
  assert.deepEqual(store.ui.state.game.round.submitted_player_ids, ["me"]);
});

await check("late submission receipts never write the next round or another game", () => {
  const store = model();
  store.applySnapshot(snapshot("round-2", 2), "room");
  store.acceptAnswer("game", "round-1", {song_option: 0, who_player_ids: []});
  assert.equal(store.ui.state.game.round.my_answer, undefined);
  store.acceptAnswer("other-game", "round-2", {song_option: 1, who_player_ids: []});
  assert.equal(store.ui.state.game.round.my_answer, undefined);
  assert.equal(store.applySnapshot(snapshot("round-1", 1), "room"), false);
  assert.equal(store.applySnapshot(snapshot("round-3", 3), "other-room"), false);
});

await check("leaving clears room identity, history, readiness and answer drafts", () => {
  const store = model();
  store.applySnapshot(snapshot(), "room");
  store.ui.history = {games: [1]}; store.ui.historyOpen = true; store.readySent.add("round-1:1");
  store.forgetRoom();
  assert.equal(store.ui.roomId, null); assert.equal(store.ui.state, null);
  assert.equal(store.ui.history, null); assert.equal(store.ui.historyOpen, false);
  assert.equal(store.readySent.size, 0);
});

await check("entry submit buttons preserve the browser's native submit event", async () => {
  const store = model(); store.forgetRoom(); store.ui.draftNickname = "Host";
  const app = port(), leaveButton = port(); let renders = 0; const calls = [];
  const transport = {api: async (url, options) => { calls.push({url, options}); return {room_id: "room"}; }, path: suffix => `/api/rooms/room${suffix}`};
  bindActions({app, leaveButton, navigator: {}, confirm: () => true}, store, transport, {}, () => renders++, assert.fail, () => {});
  await app.handlers.get("click")({target: {closest: () => ({type: "submit", dataset: {}, disabled: false})}});
  assert.equal(renders, 0);
  let prevented = false;
  await app.handlers.get("submit")({target: {id: "entry-form"}, preventDefault: () => { prevented = true; }});
  assert.equal(prevented, true); assert.equal(store.ui.pending, false);
  assert.equal(calls[0].options.body.nickname, "Host"); assert.equal(store.ui.roomId, "room");
});

await check("submission action captures its URL and payload before awaiting the server", async () => {
  const store = model(); store.applySnapshot(snapshot(), "room"); store.ui.songOption = 0; store.ui.listeners.add("me");
  const wait = deferred(); let sent;
  const transport = {api: async (url, options) => { sent = {url, body: options.body}; await wait.promise; }, roundPath: suffix => `/rounds/${store.ui.state.game.round.id}${suffix}`};
  const app = port(); bindActions({app, leaveButton: port(), navigator: {}, confirm: () => true}, store, transport, {}, () => {}, assert.fail, () => {});
  const response = app.handlers.get("click")({target: {closest: () => ({dataset: {action: "submit-answer"}, disabled: false})}});
  store.applySnapshot(snapshot("round-2", 2), "room");
  wait.resolve(); await response;
  assert.equal(sent.url, "/rounds/round-1/answers");
  assert.deepEqual(sent.body, {song_option: 0, who_player_ids: ["me"]});
  assert.equal(store.ui.state.game.round.my_answer, undefined);
});

await check("renderer preserves form focus, updates clocks without replacing markup and falls back artwork", () => {
  let replacements = 0, focused = 0, selected;
  const image = {src: "/broken-cover.svg", addEventListener: (_, handler) => { image.fail = handler; }};
  const field = {focus: () => focused++, setSelectionRange: (...range) => { selected = range; }};
  const timer = {dataset: {countdown: "5000"}}, progress = {dataset: {progressStart: "1000", progressEnd: "5000"}, style: {}};
  const app = {set innerHTML(value) { replacements++; }, setAttribute: () => {}, querySelector: () => field,
    querySelectorAll: selector => selector === "img[data-cover]" ? [image] : selector === "[data-countdown]" ? [timer] : [progress]};
  const document = {activeElement: {tagName: "INPUT", name: "nickname", selectionStart: 2, selectionEnd: 4}};
  const renderer = createRenderer({app, leaveButton: {}, document}, () => "same screen", () => 2000, () => snapshot());
  renderer.render(); renderer.render();
  assert.equal(replacements, 1); assert.equal(focused, 1); assert.deepEqual(selected, [2, 4]);
  assert.equal(timer.textContent, 3); assert.equal(progress.style.width, "75%");
  image.fail(); assert.equal(image.src, "/static/images/cover-placeholder.svg");
});

await check("polling ignores stale state and schedules the next request only after completing", async () => {
  const store = model(); store.applySnapshot(snapshot("round-2", 2), "room");
  const wait = deferred(), timers = []; let renders = 0, syncs = 0;
  const runtime = createRuntime(store, {api: async () => { await wait.promise; return snapshot("round-1", 1); }, path: () => "/state"},
    {synchronize: async () => syncs++}, () => renders++, assert.fail, assert.fail, (callback, delay) => timers.push(delay));
  const pending = runtime.poll(); assert.equal(timers.length, 0); wait.resolve(); await pending;
  assert.deepEqual(timers, [500]); assert.equal(renders, 0); assert.equal(syncs, 0);
});

await check("screen templates escape player input and preserve four-track start restriction", () => {
  const store = model(); const state = snapshot(); state.game = null; state.players[0].nickname = "<script>alert(1)</script>";
  state.players.push({...state.players[0], id: "second", is_host: false}, {...state.players[0], id: "third", is_host: false});
  store.applySnapshot(state, "room");
  const html = createViews(store.ui, () => ({unlocked: true, leaseId: "lease"}), () => 1000)();
  assert.ok(html.includes("&lt;script&gt;")); assert.ok(!html.includes("<script>alert"));
  assert.ok(html.includes('data-action="start" disabled')); assert.ok(html.includes("four temporary tracks"));
});

await check("host preloads the manifest, reports checks, ACKs readiness and plays each attempt once", async () => {
  let state = snapshot(); state.game.phase = "setup";
  const calls = [], sources = []; let activeLoads = 0, maxLoads = 0, downloaded = 0;
  class AudioContext {
    constructor() { this.state = "suspended"; this.sampleRate = 48000; this.currentTime = 0; this.destination = {}; }
    async resume() { this.state = "running"; }
    createBuffer() { return {}; }
    createBufferSource() { const source = {connect() {}, start: (...args) => { source.started = args; }, stop: (...args) => { source.stopped = args; }}; sources.push(source); return source; }
    async decodeAudioData() { return {duration: 30}; }
  }
  const candidates = Array.from({length: 6}, (_, index) => ({candidate_id: `clip-${index}`, preview_url: `/clip-${index}.mp3`}));
  const transport = {path: suffix => suffix, roundPath: suffix => `/round${suffix}`, api: async (url, options) => {
    calls.push({url, options});
    if (url === "/audio-controller") return {lease_id: "lease"};
    if (url.endsWith("/audio")) return {candidates};
    return {};
  }};
  const environment = {...globalThis, AudioContext, AbortController, setTimeout, clearTimeout, fetch: async () => {
    activeLoads++; maxLoads = Math.max(maxLoads, activeLoads); await new Promise(resolve => setTimeout(resolve, 1)); activeLoads--; downloaded++;
    return {ok: true, arrayBuffer: async () => new ArrayBuffer(1)};
  }};
  const notices = [], audio = createAudioController(transport, () => state, () => 1000, "tab", new Set(), () => {}, message => notices.push(message), environment);
  await audio.enable(); await audio.synchronize();
  for (let tries = 0; tries < 100 && calls.filter(call => call.url.endsWith("/preload-check")).length < 6; tries++) await new Promise(resolve => setTimeout(resolve, 2));
  assert.equal(downloaded, 6); assert.equal(calls.filter(call => call.url.endsWith("/preload-check")).length, 6); assert.ok(maxLoads <= 4);
  state.game.phase = "ready"; await audio.synchronize(); await audio.synchronize();
  assert.equal(calls.filter(call => call.url === "/round/ready").length, 1);
  state.game.phase = "countdown"; await audio.synchronize(); await audio.synchronize();
  assert.equal(sources.length, 2); assert.deepEqual(sources[1].started, [0]); assert.deepEqual(sources[1].stopped, [20]);
  state.game.phase = "reveal"; await audio.synchronize(); assert.deepEqual(sources[1].stopped, []); assert.deepEqual(notices, []);
  audio.reset(); assert.equal(audio.status.leaseId, null);
});

await check("host lease conflict stops playback and exposes an explicit takeover state", async () => {
  let leaseCalls = 0;
  class AudioContext { constructor() { this.state = "running"; this.destination = {}; } async resume() {} createBuffer() {} createBufferSource() { return {connect() {}, start() {}}; } }
  const transport = {path: suffix => suffix, api: async () => { if (leaseCalls++) throw Object.assign(new Error("Another tab"), {status: 409}); return {lease_id: "lease"}; }};
  const audio = createAudioController(transport, () => snapshot(), () => 1000, "tab", new Set(), () => {}, assert.fail, {...globalThis, AudioContext});
  await audio.enable(); await assert.rejects(audio.renewLease(), /Another tab/);
  assert.equal(audio.status.leaseId, null); assert.equal(audio.status.conflict, true);
});

console.log(`${checks} frontend behavior checks passed.`);
