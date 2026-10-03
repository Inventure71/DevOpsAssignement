import test from "node:test";
import assert from "node:assert/strict";

// Exercise the real component against the DOM surface it uses. Browser QA checks
// layout/focus; these tests deterministically control network completion order.
class Node {
  constructor() {
    this.children = []; this.attrs = new Map(); this.listeners = new Map();
    this.value = ""; this.hidden = false; this.textContent = "";
    this.classList = { toggle() {} };
  }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  setAttribute(name, value) { this.attrs.set(name, value); }
  getAttribute(name) { return this.attrs.get(name); }
  removeAttribute(name) { this.attrs.delete(name); }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children.push(...children); }
  setCustomValidity(value) { this.validationMessage = value; }
  reportValidity() { this.reported = true; }
  focus() { this.listeners.get("focus")?.(); }
  scrollIntoView() { this.scrolled = true; }
}
globalThis.HTMLElement = class extends Node {
  attachShadow() {
    const nodes = new Map();
    this.shadowRoot = new Node();
    this.shadowRoot.querySelector = (selector) => {
      if (!nodes.has(selector)) nodes.set(selector, new Node());
      return nodes.get(selector);
    };
  }
  dispatchEvent(event) { this.events.push(event); }
};
globalThis.customElements = { define() {} };
globalThis.document = { createElement: () => new Node() };
globalThis.CustomEvent = class { constructor(type, fields) { this.type = type; Object.assign(this, fields); } };
const { SongSearch } = await import("../../frontend/components/song-search.mjs");
function create(search = async () => ({ songs: [] })) {
  const component = new SongSearch();
  component.events = []; component.search = search;
  return component;
}
function type(component, value) { component.input.value = value; component.input.listeners.get("input")(); }
function key(component, name, fields = {}) {
  const event = { key: name, preventDefault() { this.prevented = true; }, ...fields };
  component.input.listeners.get("keydown")(event);
  return event;
}
const settle = () => new Promise(setImmediate);
const song = (title = "Dreams") => ({ title, artist: "Fleetwood Mac", token: `room:${title}` });

test("typing and focus never search; Search and Enter issue one explicit request", async () => {
  const calls = [];
  const component = create(async (query) => { calls.push(query); return { songs: [song()] }; });
  type(component, "D"); type(component, "Dreams"); component.input.focus();
  await settle();
  assert.deepEqual(calls, []);
  component.searchButton.listeners.get("click")();
  key(component, "Enter");
  await settle();
  assert.deepEqual(calls, ["Dreams"]);
  component.close(); component.input.focus();
  assert.equal(component.panel.hidden, false);
  key(component, "Enter"); await settle();
  assert.equal(calls.length, 1, "same resolved query opens existing results");
  type(component, "  Go Your Own Way  "); key(component, "Enter"); await settle();
  assert.deepEqual(calls, ["Dreams", "Go Your Own Way"]);
});

test("poll snapshots preserve the draft and keyboard selection requires a scoped result", async () => {
  const component = create(async () => ({ songs: [song(), song("The Chain")] }));
  type(component, "fleetwood"); component.selection = null; component.disabled = false;
  assert.equal(component.input.value, "fleetwood");
  assert.equal(component.hasUnselectedQuery, true);
  component.reportSelectionRequired();
  assert.equal(component.input.reported, true);
  await component.load();
  key(component, "ArrowUp");
  assert.equal(component._active, 1);
  assert.equal(component.list.children[1].getAttribute("aria-selected"), "true");
  assert.equal(component.input.getAttribute("aria-activedescendant"), component.list.children[1].id);
  key(component, "Enter");
  assert.equal(component.selection.token, "room:The Chain");
  assert.equal(component.panel.hidden, true);
  assert.equal(component.hasUnselectedQuery, false);
  assert.equal(component.events[0].detail.song.title, "The Chain");
  component.clearButton.listeners.get("click")();
  assert.equal(component.input.value, "");
  assert.equal(component.selection, null);
  assert.equal(component.events[1].detail.song, null);
});

test("editing aborts old work; late replies cannot replace current results or unlock newer requests", async () => {
  const requests = [];
  const component = create((query, { signal }) => new Promise((resolve) => requests.push({ query, signal, resolve })));
  type(component, "old"); const old = component.load();
  assert.equal(component.searchButton.disabled, true);
  assert.equal(component.panel.getAttribute("aria-busy"), "true");
  type(component, "new"); const current = component.load();
  assert.equal(requests[0].signal.aborted, true);
  requests[0].resolve({ songs: [song("Old")] }); await old;
  assert.equal(component.searchButton.disabled, true);
  assert.deepEqual(component._results, []);
  requests[1].resolve({ songs: [song("New")] }); await current;
  assert.equal(component._results[0].title, "New");
  assert.equal(component.searchButton.disabled, false);
  assert.equal(component.panel.getAttribute("aria-busy"), "false");
});

test("disabled and disconnected components reject late responses and selections", async () => {
  for (const stop of [(c) => { c.disabled = true; }, (c) => c.disconnectedCallback()]) {
    let resolve, signal;
    const component = create((_, fields) => { signal = fields.signal; return new Promise((done) => { resolve = done; }); });
    type(component, "Dreams"); const loading = component.load(); stop(component);
    resolve({ songs: [song()] }); await loading;
    assert.equal(signal.aborted, true);
    assert.deepEqual(component._results, []);
    component.choose(0);
    assert.equal(component.events.length, 0);
  }
});

test("short query, IME composition, empty results and retry errors have actionable states", async () => {
  let calls = 0;
  const component = create(async () => { calls++; if (calls === 1) throw Object.assign(new Error("provider cache quota secret"), { status: 429 }); return { songs: [] }; });
  type(component, "x"); await component.load();
  assert.equal(calls, 0); assert.match(component.hint.textContent, /two letters/);
  type(component, "Dreams"); key(component, "Enter", { isComposing: true }); await settle();
  assert.equal(calls, 0);
  await component.load();
  assert.match(component.status.textContent, /busy/);
  assert.doesNotMatch(component.status.textContent, /provider|quota|secret/);
  assert.equal(component.retryButton.hidden, false);
  component.retryButton.listeners.get("click")(); await settle();
  assert.equal(calls, 2);
  assert.match(component.status.textContent, /No songs found/);
  assert.equal(component.retryButton.hidden, true);
  assert.equal(component.list.children.length, 0);
  key(component, "Escape");
  assert.equal(component.input.getAttribute("aria-expanded"), "false");
});

test("bulk metadata selection resolves once before emitting the usable guess token", async () => {
  let done;
  const component = create(async () => ({ songs: [{ ...song(), resolve_required: true }] }));
  const resolutions = [];
  component.resolve = (selected, { signal }) => { resolutions.push({ selected, signal }); return new Promise((resolve) => { done = resolve; }); };
  type(component, "Dreams"); await component.load();
  const checking = component.choose(0);
  await component.choose(0);
  assert.equal(resolutions.length, 1);
  assert.equal(component.selection, null);
  assert.equal(component.events.length, 0);
  assert.equal(component.status.textContent, "Checking song…");
  assert.equal(component.panel.getAttribute("aria-busy"), "true");
  done({ ...song(), token: "resolved:room:Dreams" }); await checking;
  assert.equal(component.events.length, 1);
  assert.equal(component.events[0].detail.song.token, "resolved:room:Dreams");
  assert.equal(component.selection.resolve_required, undefined);
});

test("editing, lock, Escape and unmount cancel pending selection without admitting stale guesses", async () => {
  for (const change of [
    (c) => type(c, "The Chain"),
    (c) => { c.disabled = true; },
    (c) => key(c, "Escape"),
    (c) => c.disconnectedCallback(),
  ]) {
    let done, signal;
    const component = create(async () => ({ songs: [{ ...song(), resolve_required: true }] }));
    component.resolve = (_, fields) => { signal = fields.signal; return new Promise((resolve) => { done = resolve; }); };
    type(component, "Dreams"); await component.load();
    const checking = component.choose(0); change(component);
    done(song()); await checking;
    assert.equal(signal.aborted, true);
    assert.equal(component.selection, null);
    assert.equal(component.events.length, 0);
    assert.equal(component.panel.getAttribute("aria-busy"), "false");
  }
});

test("selection failure preserves results, retries that row, and never emits unresolved metadata", async () => {
  const component = create(async () => ({ songs: [{ ...song(), resolve_required: true }] }));
  let calls = 0;
  component.resolve = async () => { calls++; if (calls === 1) throw new Error("Apple signing worker internal error"); return song(); };
  type(component, "Dreams"); await component.load();
  await component.choose(0);
  assert.equal(component.selection, null);
  assert.equal(component.events.length, 0);
  assert.equal(component.list.children.length, 1);
  assert.equal(component.input.value, "Dreams");
  assert.equal(component.retryButton.hidden, false);
  assert.doesNotMatch(component.status.textContent, /Apple|worker|internal/);
  component.retryButton.listeners.get("click")(); await settle();
  assert.equal(calls, 2);
  assert.equal(component.selection.token, "room:Dreams");
  assert.equal(component.events.length, 1);
});

test("ambiguous selection presents resolved alternatives and choosing one requires no further lookup", async () => {
  const original = { ...song(), resolve_required: true };
  const alternatives = [song("Dreams (Fleetwood Mac)"), { ...song("Dreams (Other Artist)"), artist: "Other Artist" }];
  const component = create(async () => ({ songs: [original] }));
  let calls = 0;
  component.resolve = async () => {
    calls++;
    throw Object.assign(new Error("Ambiguous recording identity"), { status: 409, details: { alternatives } });
  };
  type(component, "Dreams"); await component.load();
  key(component, "ArrowDown");
  await component.choose(0);
  assert.equal(component.selection, null);
  assert.equal(component.events.length, 0);
  assert.equal(component.input.value, "Dreams");
  assert.equal(component.status.textContent, "Choose the song you mean.");
  assert.equal(component.retryButton.hidden, true);
  assert.equal(component._retrySelection, null);
  assert.equal(component._active, -1);
  assert.equal(component.input.getAttribute("aria-activedescendant"), undefined);
  assert.deepEqual(component._results, alternatives);
  assert.equal(component.list.children.length, 2);
  key(component, "ArrowDown"); key(component, "ArrowDown"); key(component, "Enter");
  assert.equal(component.selection.token, alternatives[1].token);
  assert.equal(component.events[0].detail.song.artist, "Other Artist");
  assert.equal(calls, 1);
});

test("invalid, unresolved, oversized or wrong-status alternative lists retain generic retry", async () => {
  for (const [status, alternatives] of [
    [409, null], [409, []], [409, [null]], [409, [{ ...song(), token: "" }]],
    [409, [{ ...song(), artist: "" }]], [409, [{ ...song(), resolve_required: true }]],
    [409, Array(21).fill(song())], [503, [song()]],
  ]) {
    const component = create(async () => ({ songs: [{ ...song(), resolve_required: true }] }));
    component.resolve = async () => { throw Object.assign(new Error("Invalid alternatives"), { status, details: { alternatives } }); };
    type(component, "Dreams"); await component.load(); await component.choose(0);
    assert.equal(component._results[0].resolve_required, true);
    assert.equal(component.retryButton.hidden, false);
    assert.equal(component.selection, null);
    assert.equal(component.events.length, 0);
    assert.match(component.status.textContent, /Couldn’t check/);
  }
});

test("late ambiguity cannot replace edited or disabled results", async () => {
  for (const stop of [(c) => type(c, "new query"), (c) => { c.disabled = true; }]) {
    let reject;
    const original = { ...song(), resolve_required: true };
    const component = create(async () => ({ songs: [original] }));
    component.resolve = () => new Promise((_, fail) => { reject = fail; });
    type(component, "Dreams"); await component.load(); const checking = component.choose(0);
    stop(component);
    reject(Object.assign(new Error("Late ambiguity"), { status: 409, details: { alternatives: [song("Late alternative")] } }));
    await checking;
    assert.equal(component.selection, null);
    assert.equal(component.events.length, 0);
    assert.equal(component._results.some((entry) => entry.title === "Late alternative"), false);
    assert.equal(component.panel.hidden, true);
  }
});
