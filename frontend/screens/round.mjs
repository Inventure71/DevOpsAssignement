import "../components/round-countdown.mjs";
import "../components/player-card.mjs";
import "../components/song-search.mjs";
import "../components/music-waveform.mjs";
import { syncKeyedGroups } from "../dom.mjs";
import { roundPreparation } from "../game/preparation.mjs";
import { roundTiming } from "../game/timing.mjs";

export function createRoundScreen(emit) {
  const element = document.createElement("section");
  element.className = "round-screen";
  element.innerHTML = `
    <div class="round-meta"><span class="round-label"></span><span class="round-connection" role="status"></span></div>
    <div class="round-layout"><div class="round-players round-players-left" aria-label="Players"></div>
      <div class="round-center"><div class="round-stage"><round-countdown class="round-timer"></round-countdown>
        <div class="round-heading"><h1 class="round-title"></h1><p class="round-subtitle"></p></div>
        <repeat-character class="round-character" color="coral" mood="listening"></repeat-character>
        <svg class="round-note round-note-one" viewBox="0 0 32 48" aria-hidden="true" focusable="false"><path d="M16 39V5l12 7v8l-12-7" fill="none" stroke="currentColor" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round"/><ellipse cx="9" cy="39" rx="8" ry="6" fill="currentColor"/></svg>
        <svg class="round-note round-note-two" viewBox="0 0 48 48" aria-hidden="true" focusable="false"><path d="M16 38V10l24-5v28M16 17l24-5" fill="none" stroke="currentColor" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round"/><ellipse cx="9" cy="38" rx="8" ry="6" fill="currentColor"/><ellipse cx="33" cy="33" rx="8" ry="6" fill="currentColor"/></svg>
      </div><div class="round-controls"><music-waveform class="round-waveform"></music-waveform>
        <div class="round-song-field"><song-search></song-search></div>
        <button class="button button-primary submit-guess" type="button">Submit guess <span aria-hidden="true">→</span></button>
        <p class="round-selection-hint">Select who you think is listening</p>
        <p class="round-empty-selection"></p><div class="round-recovery"></div>
      </div></div><div class="round-players round-players-right" aria-label="Players"></div>
    </div>`;
  const find = (selector) => element.querySelector(selector);
  const cards = new Map();
  let model;
  let lastTitle = "";
  const heading = find(".round-title");
  const subtitle = find(".round-subtitle");
  const ring = find("round-countdown");
  const sprite = find(".round-character");
  const search = find("song-search");
  const waveform = find("music-waveform");
  const submit = find(".submit-guess");
  submit.addEventListener("click", () => {
    if (search.hasUnselectedQuery) {
      search.reportSelectionRequired();
      return;
    }
    emit("submit-answer");
  });
  function update(vm) {
    model = vm;
    const { state, ui } = vm;
    if (!state?.game) return;
    const game = state.game;
    const round = game.round;
    const submitted = Boolean(round?.my_answer);
    const selected = new Set(
      round?.my_answer?.who_player_ids ?? ui.listeners ?? [],
    );
    const submittedIds = new Set(round?.submitted_player_ids ?? []);
    const locked =
      submitted ||
      game.phase !== "answering" ||
      Boolean(ui.pending) ||
      Boolean(ui.disconnected) ||
      Boolean(round?.deadline_at_ms && vm.now >= round.deadline_at_ms);
    element.classList.toggle("has-submitted", submitted);
    element.classList.toggle("is-preparing", game.phase !== "answering");
    find(".round-label").textContent = round
      ? `Round ${round.round_number} / ${game.playable_rounds}`
      : "Getting ready";
    find(".round-connection").textContent = ui.disconnected
      ? "Reconnecting…"
      : "";
    if (sprite.getAttribute("color") !== state.me.character_id)
      sprite.setAttribute("color", state.me.character_id);
    const mood = submitted
      ? "submitted"
      : game.phase === "answering"
        ? "listening"
        : "idle";
    if (sprite.getAttribute("mood") !== mood) sprite.setAttribute("mood", mood);
    if (vm.search) search.search = vm.search;
    if (vm.resolveSong) search.resolve = vm.resolveSong;
    search.selection = submitted ? round.my_answer.song_guess : ui.songGuess;
    search.submitted = submitted;
    search.disabled = locked;
    submit.disabled = locked;
    submit.textContent = submitted
      ? "✓ Submitted"
      : ui.pending === "submit-answer"
        ? "Submitting…"
        : "Submit guess →";
    submit.hidden = !["answering", "countdown"].includes(game.phase);
    find(".round-song-field").hidden = !["answering", "countdown"].includes(
      game.phase,
    );
    waveform.hidden = !["answering", "countdown"].includes(game.phase);
    ring.data = {
      startsAt: round?.starts_at_ms,
      deadline: round?.deadline_at_ms,
      now: vm.now,
      phase: game.phase,
      submitted,
    };
    waveform.data = {
      startsAt: round?.starts_at_ms,
      deadline: round?.deadline_at_ms,
      submitted,
      now: vm.now,
      levels: round?.waveform,
    };
    find(".round-selection-hint").textContent = submitted
      ? "Your guesses are locked in"
      : game.phase === "answering"
        ? "Select who you think is listening"
        : "";
    find(".round-empty-selection").textContent =
      game.phase === "answering" && !submitted && selected.size === 0
        ? "No players selected means nobody."
        : "";
    const midpoint = Math.ceil(state.players.length / 2);
    syncKeyedGroups(
      [
        {
          container: find(".round-players-left"),
          values: state.players.slice(0, midpoint),
        },
        {
          container: find(".round-players-right"),
          values: state.players.slice(midpoint),
        },
      ],
      cards,
      {
        key: (player) => player.id,
        create: () => document.createElement("player-card"),
        update: (card, player) => {
          card.data = {
            ...player,
            status: submittedIds.has(player.id) ? "submitted" : "listening",
            selected: selected.has(player.id),
            selectable: true,
            disabled: locked,
            variant: "round",
          };
        },
      },
    );
    updateRecovery(vm);
    tick(vm.now);
  }
  function updateRecovery(vm) {
    const game = vm.state.game;
    const round = game.round;
    const missing = game.missing_player_ids ?? [];
    const timedOut =
      game.phase === "ready" &&
      round &&
      vm.now >= round.readiness_deadline_at_ms;
    const controls = find(".round-recovery");
    const needsAudio =
      vm.state.me.is_host && (!vm.audio.unlocked || !vm.audio.leaseId);
    const signature = `${timedOut}:${needsAudio}:${vm.audio.conflict}:${vm.state.me.is_host}:${missing.join(",")}`;
    if (controls.dataset.signature !== signature) {
      controls.dataset.signature = signature;
      controls.replaceChildren();
      if (needsAudio) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button button-outline";
        button.textContent = vm.audio.conflict
          ? "Use audio in this tab"
          : "Enable shared audio";
        button.addEventListener("click", () =>
          emit(vm.audio.conflict ? "takeover-audio" : "enable-audio"),
        );
        controls.append(button);
      }
      if (timedOut && vm.state.me.is_host) {
        for (const [label, action] of [
          ["Try again", "retry-ready"],
          ["Continue without missing players", "continue-ready"],
        ]) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "button button-outline";
          button.textContent = label;
          button.dataset.action = action;
          button.addEventListener("click", () => emit(action, missing));
          controls.append(button);
        }
      }
    }
    controls.querySelectorAll("button").forEach((button) => {
      button.disabled =
        Boolean(vm.ui.pending) ||
        (button.dataset.action === "continue-ready" &&
          missing.includes(vm.state.me.id));
    });
  }
  function tick(now) {
    if (!model?.state?.game) return;
    const { game, players } = model.state;
    const round = game.round;
    const submitted = Boolean(round?.my_answer);
    let title = "",
      detail = "";
    if (game.phase === "answering") {
      const remaining = Math.ceil(
        roundTiming({
          startsAt: round.starts_at_ms,
          deadline: round.deadline_at_ms,
          now,
        }).remaining / 1000,
      );
      title = submitted
        ? "Guess submitted"
        : remaining > 0
          ? `${remaining}s left`
          : "Time’s up!";
      detail = submitted ? "Waiting for the others…" : "";
      if (now >= round.deadline_at_ms) {
        submit.disabled = true;
        search.disabled = true;
      }
    } else if (game.phase === "countdown") {
      title = `${Math.max(1, Math.ceil((round.starts_at_ms - now) / 1000))}`;
      detail = "Get your ears ready";
    } else {
      const preparation = roundPreparation(game, players, now, model.state.me.is_host);
      title = preparation?.title || "";
      detail = preparation?.message || "";
    }
    if (title !== lastTitle) {
      heading.textContent = title;
      lastTitle = title;
    }
    if (subtitle.textContent !== detail) subtitle.textContent = detail;
    ring.tick(now);
    waveform.tick?.(now);
  }
  return {
    element,
    update,
    tick,
    destroy() {
      model = null;
      cards.clear();
    },
  };
}
