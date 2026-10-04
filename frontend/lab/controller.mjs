import { createLabAudio } from "../audio/lab.mjs";
import {
  LAB_SCENES,
  createLabState,
  createLabUi,
  createRoundFixture,
} from "./fixtures.mjs";

/** Only server-selected, locally installed audio is used by the UI lab. */
export async function fetchLabPreview(fetch = globalThis.fetch, signal) {
  const response = await fetch("/api/demo/preview", { signal });
  if (!response.ok) throw new Error("Demo preview is unavailable.");
  const { song } = await response.json();
  if (
    !song || typeof song.title !== "string" || !song.title.trim() ||
    typeof song.artist !== "string" || !song.artist.trim() ||
    typeof song.preview_url !== "string" ||
    !song.preview_url.startsWith("/static/demo/local/") || song.preview_url.includes("..") ||
    !(song.artwork_url === null || typeof song.artwork_url === "string")
  )
    throw new Error("Invalid Demo preview metadata.");
  return song;
}

/** Owns fixture navigation, timing and preview audio; screens remain reusable. */
export function createLabController({
  root, navigation, params, fetch = globalThis.fetch,
}) {
  const state = createLabState(Date.now());
  const ui = createLabUi();
  const listeners = new AbortController();
  const errorNotice = document.createElement("p");
  errorNotice.className = "preview-error form-error";
  errorNotice.setAttribute("role", "alert");
  const sceneButtons = [...navigation.querySelectorAll("[data-scene]")];
  let screen, sceneName;
  let sceneGeneration = 0,
    measuredLevels = [],
    frame = 0,
    lastFrame = 0;
  let disposed = false;
  let preview = null,
    songs = [],
    previewPromise = null,
    previewError = null;
  const previewRequest = new AbortController();
  let previewTimeout;
  function preparePreview() {
    if (previewPromise) return previewPromise;
    previewTimeout = setTimeout(() => previewRequest.abort(), 10000);
    previewPromise = fetchLabPreview(fetch, previewRequest.signal).then((song) => {
      if (disposed) return false;
      songs = [
        { ...song, token: "lab-active-song" },
        {
          token: "lab-other-guess",
          title: "Another title (sample guess)",
          artist: "Another artist (sample guess)",
          artwork_url: null,
        },
      ];
      preview = createLabAudio({
        url: song.preview_url,
        onChange({ levels, error }) {
          measuredLevels = levels;
          if (state.game?.round) state.game.round.waveform = levels;
          if (state.game?.phase === "setup")
            state.game.preparation = { checked: levels.length ? 1 : 0, total: 1 };
          if (error && ["listening", "submitted"].includes(sceneName)) {
            errorNotice.textContent = `${error} Select the scene again to retry.`;
            root.append(errorNotice);
          } else errorNotice.remove();
          update();
        },
      });
      return true;
    }).catch(() => {
      if (!disposed)
        previewError = "Demo music couldn’t load. Run the Demo setup, then reload this page. Characters and Lobby are still available.";
      return false;
    }).finally(() => clearTimeout(previewTimeout));
    return previewPromise;
  }
  const searchSongs = async (query) => {
    const term = query.toLowerCase();
    return {
      songs: songs.filter((song) =>
        `${song.title} ${song.artist}`.toLowerCase().includes(term),
      ),
    };
  };
  function update() {
    if (disposed || !screen) return;
    screen.update({
      state,
      ui,
      audio: { unlocked: true, leaseId: "lab-lease", conflict: false },
      now: Date.now(),
      search: searchSongs,
    });
  }
  function canAnswer() {
    return (
      state.game?.phase === "answering" &&
      Date.now() < state.game.round.deadline_at_ms &&
      !state.game.round.my_answer
    );
  }
  function action(name, value) {
    if (name === "submit-answer") {
      if (!canAnswer()) return;
      state.game.round.my_answer = {
        song_guess: ui.songGuess,
        who_player_ids: [...ui.listeners],
      };
      state.game.round.submitted_player_ids = [
        ...new Set([...state.game.round.submitted_player_ids, state.me.id]),
      ];
    } else if (name === "character") {
      ui.character = value;
      state.me.character_id = value;
    } else if (name === "setting") state.settings[value.name] = value.value;
    update();
  }
  function selectNavigation(name) {
    for (const button of sceneButtons)
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.scene === name),
      );
  }
  async function showScene(requestedName, gesture) {
    if (disposed) return;
    const name = LAB_SCENES.includes(requestedName)
      ? requestedName
      : "characters";
    const generation = ++sceneGeneration;
    if (name === "submitted" && sceneName === "listening" && canAnswer()) {
      sceneName = name;
      ui.songGuess ||= songs[0];
      action("submit-answer");
      selectNavigation(name);
      return;
    }
    preview?.stop();
    sceneName = name;
    screen?.destroy?.();
    screen = null;
    root.replaceChildren();
    selectNavigation(name);
    if (name === "characters") {
      state.game = null;
      const { createCharacterStudio } = await import("./characters.mjs");
      if (disposed || generation !== sceneGeneration) return;
      root.append(createCharacterStudio());
      return;
    }
    const audioScene = ["listening", "submitted"].includes(name);
    // Resume from the scene click, before any asynchronous metadata/import work.
    const audioStart = audioScene && gesture && preview ? preview.play() : null;
    if (name !== "lobby" && !await preparePreview()) {
      if (!disposed && generation === sceneGeneration) {
        errorNotice.textContent = previewError;
        root.append(errorNotice);
      }
      return;
    }
    if (disposed || generation !== sceneGeneration) return;
    const now = Date.now();
    let createScreen;
    if (name === "lobby") {
      state.room.state = "lobby";
      state.game = null;
      ({ createLobbyScreen: createScreen } =
        await import("../screens/lobby.mjs"));
    } else {
      state.room.state = "playing";
      ui.songGuess = name === "submitted" ? songs[0] : null;
      state.game = createRoundFixture({
        scene: name,
        state,
        ui,
        now,
        levels: measuredLevels,
        params,
        songs,
      });
      if (["reveal", "leaderboard"].includes(name))
        ({ createResultsScreen: createScreen } =
          await import("../screens/results.mjs"));
      else
        ({ createRoundScreen: createScreen } =
          await import("../screens/round.mjs"));
    }
    if (disposed || generation !== sceneGeneration) return;
    screen = createScreen(action);
    root.append(screen.element);
    const waveform = screen.element.querySelector("music-waveform");
    if (waveform) waveform.appearance = { mode: params.get("waveform") };
    update();
    if (audioScene && !audioStart) {
      errorNotice.textContent = `Select ${name === "submitted" ? "Submitted" : "Listening"} to start the preview.`;
      root.append(errorNotice);
    }
    if (audioStart) {
      const timing = await audioStart;
      if (
        !timing ||
        disposed ||
        generation !== sceneGeneration ||
        !state.game?.round
      )
        return;
      state.game.round.starts_at_ms = timing.startsAt;
      state.game.round.deadline_at_ms = timing.deadline;
      state.game.phase = "countdown";
      update();
    }
  }
  function navigate(name, gesture = false) {
    const generation = sceneGeneration + 1;
    void showScene(name, gesture).catch((error) => {
      if (disposed || generation !== sceneGeneration) return;
      errorNotice.textContent = error.message;
      root.append(errorNotice);
    });
  }
  function tick(now) {
    frame = 0;
    if (disposed || document.hidden) return;
    if (now - lastFrame >= 80) {
      lastFrame = now;
      const clock = Date.now();
      if (
        state.game?.phase === "countdown" &&
        clock >= state.game.round.starts_at_ms
      ) {
        state.game.phase = "answering";
        update();
      }
      screen?.tick?.(clock);
    }
    frame = requestAnimationFrame(tick);
  }
  function resumeClock() {
    if (!disposed && !frame && !document.hidden)
      frame = requestAnimationFrame(tick);
  }
  function suspend() {
    preview?.stop();
    cancelAnimationFrame(frame);
    frame = 0;
  }
  function listen(target, name, handler, options = {}) {
    target.addEventListener(name, handler, {
      ...options,
      signal: listeners.signal,
    });
  }
  listen(root, "player-select", (event) => {
    if (!canAnswer()) return;
    const id = event.detail.id;
    ui.listeners.has(id) ? ui.listeners.delete(id) : ui.listeners.add(id);
    update();
  });
  listen(root, "song-select", (event) => {
    if (!canAnswer()) return;
    ui.songGuess = event.detail.song;
    update();
  });
  listen(navigation, "click", (event) => {
    const button = event.target.closest("[data-scene]");
    if (button) navigate(button.dataset.scene, true);
  });
  listen(document, "visibilitychange", () =>
    document.hidden ? suspend() : resumeClock(),
  );
  listen(window, "pagehide", suspend);
  listen(window, "pageshow", resumeClock);
  return {
    start() {
      void preparePreview();
      navigate(params.get("scene") || "characters");
      resumeClock();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      sceneGeneration++;
      listeners.abort();
      cancelAnimationFrame(frame);
      previewRequest.abort();
      clearTimeout(previewTimeout);
      preview?.close();
      screen?.destroy?.();
    },
  };
}
