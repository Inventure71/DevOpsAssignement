import { createLabAudio } from "../audio/lab.mjs";
import { createCharacterStudio } from "./characters.mjs";
import {
  LAB_SCENES,
  LAB_SONGS,
  createLabState,
  createLabUi,
  createRoundFixture,
} from "./fixtures.mjs";

/** Owns fixture navigation, timing and preview audio; screens remain reusable. */
export function createLabController({ root, navigation, params }) {
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
  const preview = createLabAudio({
    url: "/static/demo/clips/song-001.mp3",
    onChange({ levels, error }) {
      measuredLevels = levels;
      if (state.game?.round) state.game.round.waveform = levels;
      if (state.game?.phase === "setup")
        state.game.preparation = { checked: levels.length ? 1 : 0, total: 1 };
      if (error && ["listening", "submitted"].includes(sceneName)) {
        errorNotice.textContent = error;
        root.append(errorNotice);
      } else errorNotice.remove();
      update();
    },
  });
  const searchSongs = async (query) => {
    await new Promise((resolve) => setTimeout(resolve, 180));
    const term = query.toLowerCase();
    return {
      songs: LAB_SONGS.filter((song) =>
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
  async function showScene(requestedName) {
    if (disposed) return;
    const name = LAB_SCENES.includes(requestedName)
      ? requestedName
      : "characters";
    const generation = ++sceneGeneration;
    if (name === "submitted" && sceneName === "listening" && canAnswer()) {
      sceneName = name;
      ui.songGuess ||= LAB_SONGS[0];
      action("submit-answer");
      selectNavigation(name);
      return;
    }
    preview.stop();
    sceneName = name;
    screen?.destroy?.();
    screen = null;
    root.replaceChildren();
    selectNavigation(name);
    if (name === "characters") {
      state.game = null;
      root.append(createCharacterStudio());
      return;
    }
    const audioStart = ["listening", "submitted"].includes(name)
      ? preview.play()
      : null;
    const now = Date.now();
    let createScreen;
    if (name === "lobby") {
      state.room.state = "lobby";
      state.game = null;
      ({ createLobbyScreen: createScreen } =
        await import("../screens/lobby.mjs"));
    } else {
      state.room.state = "playing";
      ui.songGuess = name === "submitted" ? LAB_SONGS[0] : null;
      state.game = createRoundFixture({
        scene: name,
        state,
        ui,
        now,
        levels: measuredLevels,
        params,
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
  function navigate(name) {
    const generation = sceneGeneration + 1;
    void showScene(name).catch((error) => {
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
    preview.stop();
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
    if (button) navigate(button.dataset.scene);
  });
  // The first browser gesture unlocks sound; only the scene controller starts it.
  for (const event of ["pointerdown", "keydown"])
    listen(
      document,
      event,
      () => {
        void preview.unlock().catch(() => {});
      },
      { once: true },
    );
  listen(document, "visibilitychange", () =>
    document.hidden ? suspend() : resumeClock(),
  );
  listen(window, "pagehide", suspend);
  listen(window, "pageshow", resumeClock);
  return {
    start() {
      navigate(params.get("scene") || "characters");
      resumeClock();
      void preview.load().catch(() => {});
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      sceneGeneration++;
      listeners.abort();
      cancelAnimationFrame(frame);
      preview.close();
      screen?.destroy?.();
    },
  };
}
