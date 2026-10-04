import test from "node:test";
import assert from "node:assert/strict";
import { BLOB_COLORS } from "../../frontend/components/blob-palette.mjs";
import {
  createLabState,
  createLabUi,
  createRoundFixture,
} from "../../frontend/lab/fixtures.mjs";

function fixture(query = "", scene = "reveal") {
  const state = createLabState(1000);
  return createRoundFixture({
    scene,
    state,
    ui: createLabUi(),
    now: 1000,
    levels: [0, 1],
    params: new URLSearchParams(query),
  });
}

test("reveal fixtures expose only the current player's answer, including edge cases", () => {
  for (const query of [
    "",
    "wrong-answer",
    "missing-answer",
    "artist-only",
    "nobody",
  ]) {
    const reveal = fixture(query).round.reveal;
    assert.deepEqual(Object.keys(reveal).sort(), [
      "listener_ids",
      "my_answer",
      "song",
    ]);
    assert.equal(reveal.my_answer.player_id, "lab-0");
    assert.equal("answers" in reveal, false);
  }
  assert.equal(
    fixture("wrong-answer").round.reveal.my_answer.song_match,
    "wrong",
  );
  assert.equal(
    fixture("missing-answer").round.reveal.my_answer.status,
    "missing",
  );
  assert.equal(
    fixture("missing-answer").round.reveal.my_answer.song_guess,
    null,
  );
  assert.equal(
    fixture("artist-only").round.reveal.my_answer.song_match,
    "artist",
  );
  assert.equal(fixture("artist-only").round.reveal.my_answer.points, 50);
  for (const query of ["missing-answer", "missing-answer&nobody"]) {
    assert.equal(fixture(query).round.reveal.my_answer.who_player_ids, null);
    assert.equal(fixture(query).round.reveal.my_answer.status, "missing");
  }
  assert.deepEqual(fixture("nobody").round.reveal.listener_ids, []);
  assert.deepEqual(fixture("nobody").round.reveal.my_answer.who_player_ids, []);
});

test("separate lab sessions own their player identities and mutable selections", () => {
  const first = createLabState(1000),
    second = createLabState(2000);
  assert.deepEqual(
    first.players.map((player) => player.character_id),
    BLOB_COLORS.map((color) => color.id),
  );
  assert.equal(first.me, first.players[0]);
  first.me.character_id = "rose";
  assert.equal(second.me.character_id, "coral");
  const firstUi = createLabUi(),
    secondUi = createLabUi();
  firstUi.listeners.clear();
  assert.equal(secondUi.listeners.size, 3);
});

test("submitted, missing artwork and tied ranks remain independently reproducible", () => {
  const submitted = fixture("", "submitted");
  assert.equal(submitted.phase, "setup");
  assert.ok(submitted.round.my_answer);
  assert.ok(submitted.round.submitted_player_ids.includes("lab-0"));
  const leaderboard = fixture("broken-artwork&tied-ranks", "leaderboard");
  assert.equal(leaderboard.phase, "leaderboard");
  assert.equal(
    leaderboard.round.reveal.song.artwork_url,
    "/ui/missing-lab-cover.png",
  );
  assert.equal(
    leaderboard.leaderboard[0].score,
    leaderboard.leaderboard[1].score,
  );
  assert.equal(leaderboard.leaderboard[1].rank, 1);
});

const { fetchLabPreview, createLabController } = await import("../../frontend/lab/controller.mjs");
const activeSong = {
  title: "Installed title", artist: "Installed artist",
  preview_url: "/static/demo/local/clips/current.m4a",
  artwork_url: "https://example.com/current-cover.jpg",
};

test("lab metadata and submitted/reveal fixtures use the active installed song", async () => {
  const request = new AbortController();
  const song = await fetchLabPreview(async (url, options) => {
    assert.equal(url, "/api/demo/preview");
    assert.equal(options.signal, request.signal);
    return { ok: true, json: async () => ({ song: activeSong }) };
  }, request.signal);
  const state = createLabState(1000);
  const songs = [{ ...song, token: "active" }, { title: "Alternate sample", artist: "Other sample", token: "other" }];
  for (const scene of ["submitted", "reveal", "leaderboard"]) {
    const game = createRoundFixture({
      scene, state, ui: createLabUi(), now: 1000, levels: [],
      params: new URLSearchParams(), songs,
    });
    const selected = scene === "submitted" ? game.round.my_answer.song_guess : game.round.reveal.song;
    assert.equal(selected.title, song.title);
    assert.equal(selected.artist, song.artist);
    assert.equal(selected.artwork_url, song.artwork_url);
  }
  const wrong = createRoundFixture({
    scene: "reveal", state, ui: createLabUi(), now: 1000, levels: [],
    params: new URLSearchParams("wrong-answer"), songs,
  });
  assert.equal(wrong.round.reveal.song.title, song.title);
  assert.equal(wrong.round.reveal.my_answer.song_guess.title, "Alternate sample");
});

test("lab metadata rejects unavailable, malformed and nonlocal preview responses", async () => {
  await assert.rejects(fetchLabPreview(async () => ({ ok: false })), /unavailable/);
  for (const song of [null, {}, { ...activeSong, title: "" },
    { ...activeSong, preview_url: "https://outside.example/music.mp3" },
    { ...activeSong, preview_url: "/static/demo/clips/song-001.mp3" },
    { ...activeSong, preview_url: "/static/demo/../private" },
    { ...activeSong, artwork_url: {} }]) {
    await assert.rejects(fetchLabPreview(async () => ({ ok: true, json: async () => ({ song }) })), /Invalid/);
  }
  await assert.rejects(fetchLabPreview(async () => { throw new Error("Network failed"); }), /Network failed/);
});

function controllerHarness(t, fetch, environment = {}, query = "scene=listening") {
  class Node extends EventTarget {
    children = [];
    textContent = "";
    dataset = {};
    attributes = new Map();
    selectors = new Map();
    classList = { toggle() {} };
    setAttribute(name, value) { this.attributes.set(name, value); }
    getAttribute(name) { return this.attributes.get(name); }
    tick() {}
    react() {}
    insertBefore(node, before) { this.children.splice(before ? this.children.indexOf(before) : this.children.length, 0, node); }
    querySelector(selector) {
      if (!this.selectors.has(selector)) this.selectors.set(selector, new Node());
      return this.selectors.get(selector);
    }
    append(node) { this.children.push(node); }
    replaceChildren() { this.children = []; }
    remove() {}
    querySelectorAll() { return []; }
    get content() {
      const child = this.querySelector("template-content");
      child.innerHTML = this.innerHTML;
      return { firstElementChild: child };
    }
  }
  let controller;
  const previous = new Map();
  const globals = {
    document: Object.assign(new Node(), { hidden: false, createElement: () => new Node() }),
    window: new Node(), requestAnimationFrame: () => 1, cancelAnimationFrame() {},
    HTMLElement: Node,
    customElements: { define() {}, get() {} },
    matchMedia: () => Object.assign(new EventTarget(), { matches: true }),
    IntersectionObserver: class { observe() {} unobserve() {} },
    ResizeObserver: class { observe() {} unobserve() {} },
    ...environment,
  };
  for (const [name, value] of Object.entries(globals)) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
  }
  t.after(() => {
    controller?.dispose();
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  });
  const root = new Node();
  const navigation = new Node();
  controller = createLabController({ root, navigation, params: new URLSearchParams(query), fetch });
  return {
    controller, root,
    select(scene) {
      navigation.closest = () => ({ dataset: { scene } });
      navigation.dispatchEvent(new Event("click"));
    },
  };
}
const settleLab = () => new Promise(setImmediate);

test("failed metadata gives installation guidance without audio or unhandled work", async (t) => {
  let requests = 0;
  const { controller, root } = controllerHarness(t, async () => { requests++; throw new Error("Offline"); });
  controller.start();
  await settleLab();
  assert.equal(requests, 1);
  assert.match(root.children.at(-1).textContent, /Run the Demo setup/);
  assert.match(root.children.at(-1).textContent, /Characters and Lobby/);
});

test("disposal aborts pending metadata and a late success cannot start playback or paint", async (t) => {
  let resolve, signal;
  const pending = new Promise((done) => { resolve = done; });
  const { controller, root } = controllerHarness(t, (_url, options) => { signal = options.signal; return pending; });
  controller.start();
  controller.dispose();
  assert.equal(signal.aborted, true);
  resolve({ ok: true, json: async () => ({ song: activeSong }) });
  await settleLab();
  assert.equal(root.children.length, 0);
});


test("successful startup uses installed metadata without autoplay; a scene click starts its audio", async (t) => {
  let contexts = 0, playback = 0, metadataRequests = 0;
  const source = { connect() {}, disconnect() {}, stop() {}, start() { playback++; } };
  class Context {
    constructor() { contexts++; }
    currentTime = 0;
    destination = {};
    resume() { return Promise.resolve(); }
    close() { return Promise.resolve(); }
    decodeAudioData() {
      return Promise.resolve({ duration: 30, numberOfChannels: 1, getChannelData: () => new Float32Array(300) });
    }
    createBufferSource() { return source; }
  }
  const session = controllerHarness(t, async () => {
    metadataRequests++;
    return { ok: true, json: async () => ({ song: activeSong }) };
  }, {
    AudioContext: Context,
    fetch: async (url) => {
      assert.equal(url, activeSong.preview_url);
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) };
    },
  });
  session.controller.start();
  for (let turn = 0; turn < 50 && session.root.children.length < 2; turn++) await settleLab();
  assert.match(session.root.children.at(-1).textContent, /Select Listening to start/);
  assert.equal(contexts, 0);
  assert.equal(playback, 0);
  session.select("listening");
  for (let turn = 0; turn < 20 && playback === 0; turn++) await settleLab();
  assert.equal(playback, 1);
  assert.equal(metadataRequests, 1);
  assert.equal(session.root.children[0].querySelector("song-search").selection, null);
  const results = await session.root.children[0].querySelector("song-search").search("Installed");
  assert.equal(results.songs[0].title, activeSong.title);
  assert.equal(results.songs[0].artist, activeSong.artist);
});

test("characters remain usable when the installed preview metadata is unavailable", async (t) => {
  const session = controllerHarness(t, async () => { throw new Error("Unavailable"); }, {}, "scene=characters");
  session.controller.start();
  for (let turn = 0; turn < 50 && !session.root.children.length; turn++) await settleLab();
  assert.equal(session.root.children.length, 1);
  assert.match(session.root.children[0].innerHTML, /Meet your blob/);
  assert.ok(session.root.children[0].querySelector(".studio-character"));
});
