import { createModel, safeStorage } from "./application/state.mjs";
import { createTransport, requestId } from "./transport/client.mjs";
import { createAudioController } from "./audio/host.mjs";
import { createRuntime } from "./application/runtime.mjs";
import { createActions } from "./application/actions.mjs";
import { createLobbyScreen } from "./screens/lobby.mjs";
import { createRoundScreen } from "./screens/round.mjs";
import { createEntryScreen } from "./screens/entry.mjs";
import { createResultsScreen } from "./screens/results.mjs";
import { createInfoScreen } from "./screens/info.mjs";
import { createHistoryScreen } from "./screens/history.mjs";
import { element, text } from "./dom.mjs";
import { createScreenHost } from "./application/screen-host.mjs";
import { createSiteHeader } from "./components/site-header.mjs";

let browserStorage;
try {
  browserStorage = globalThis.localStorage;
} catch {
  browserStorage = null;
}
const params = new URLSearchParams(location.search);
const model = createModel(
  safeStorage(browserStorage),
  params.get("room") || undefined,
);
const ui = model.ui;
ui.page = params.get("page") || "play";
if (params.has("join")) {
  ui.screen = "join";
  ui.draftCode = params.get("join").toUpperCase();
  ui.roomId = null;
}
const root = document.querySelector("#main");
const toast = document.querySelector("#notice");
const transport = createTransport(
  () => ui.roomId,
  () => ui.state,
);
let toastTimer,
  action,
  audio,
  runtime,
  frame,
  lastTick = 0;
function notice(message) {
  text(toast, message);
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.hidden = true), 6500);
}
function emit(name, payload) {
  void action(name, payload);
}
function forgetRoom() {
  audio.reset();
  model.forgetRoom();
  const url = new URL(location.href);
  url.searchParams.delete("room");
  history.replaceState({}, "", url);
  render();
}
const search = (query, { signal } = {}) =>
  transport.api(transport.path(`/song-search?q=${encodeURIComponent(query)}`), {
    signal,
  });
function viewModel() {
  return {
    state: ui.state,
    ui,
    audio: audio.status,
    now: transport.now(),
    search,
  };
}
const screens = createScreenHost(root, {
  info: (vm) => createInfoScreen(vm.ui.page, navigate),
  entry: () => createEntryScreen(emit),
  restoring: () => ({
    element: element(
      '<section class="entry-loading"><repeat-character color="coral" mood="idle"></repeat-character><h1>Back to your room…</h1></section>',
    ),
    update() {},
  }),
  history: () =>
    createHistoryScreen(() => {
      ui.historyOpen = false;
      render();
    }),
  results: () => createResultsScreen(emit),
  round: () => createRoundScreen(emit),
  lobby: () => createLobbyScreen(emit),
});
const header = createSiteHeader(document, { navigate, emit });
function render() {
  screens.update(viewModel());
  header.update(ui.state, ui.page);
  if (ui.state) {
    const url = new URL(location.href);
    if (url.searchParams.get("room") !== ui.roomId) {
      url.searchParams.set("room", ui.roomId);
      history.replaceState({}, "", url);
    }
  }
  syncFrame();
}
function navigate(page) {
  ui.page = page;
  ui.historyOpen = false;
  const url = new URL(location.href);
  if (page === "play") url.searchParams.delete("page");
  else url.searchParams.set("page", page);
  history.pushState({}, "", url);
  render();
}
audio = createAudioController(
  transport,
  () => ui.state,
  transport.now,
  requestId(),
  model.readySent,
  render,
  notice,
);
runtime = createRuntime(model, transport, audio, render, notice, forgetRoom);
action = createActions({
  model,
  transport,
  audio,
  runtime,
  render,
  notice,
  forgetRoom,
});
root.addEventListener("player-select", (event) => {
  const { id } = event.detail;
  const round = ui.state?.game?.round;
  if (
    ui.state?.game?.phase !== "answering" ||
    round?.my_answer ||
    ui.pending ||
    transport.now() >= round?.deadline_at_ms
  )
    return;
  ui.listeners.has(id) ? ui.listeners.delete(id) : ui.listeners.add(id);
  render();
});
root.addEventListener("song-select", (event) => {
  ui.songGuess = event.detail.song;
  render();
});
window.addEventListener("popstate", () => {
  ui.page = new URLSearchParams(location.search).get("page") || "play";
  render();
});
function syncFrame() {
  if (document.hidden || !screens.animated) {
    cancelAnimationFrame(frame);
    frame = null;
  } else if (!frame) frame = requestAnimationFrame(tick);
}
function tick(timestamp) {
  frame = null;
  if (!document.hidden && timestamp - lastTick >= 80) {
    screens.tick(transport.now());
    lastTick = timestamp;
  }
  syncFrame();
}
document.addEventListener("visibilitychange", () => {
  syncFrame();
  if (!document.hidden) {
    screens.tick(transport.now());
    void runtime.refresh({ fresh: true });
  }
});
window.addEventListener("pagehide", () => {
  runtime.stop();
  audio.suspend();
  cancelAnimationFrame(frame);
  frame = null;
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    runtime.start();
    syncFrame();
  }
});
render();
runtime.start();
