import { element, text } from "../dom.mjs";
import { phaseProgress } from "../game/results.mjs";
import { createRevealView } from "./reveal.mjs";
import { createStandingsView } from "../components/standings.mjs";

const END_REASONS = {
  host_timeout: "The host disconnected for too long.",
  server_restart: "The server restarted during the match.",
  initial_readiness_timeout:
    "A player did not check in before the match began.",
  host_preparation_timeout: "The audio could not be prepared in time.",
  too_many_skipped: "More than 30% of the planned songs could not be played.",
  pool_exhausted: "There were not enough playable songs to finish the match.",
  host_left: "The host left the room.",
  host_ended: "The host ended the match.",
};

export function createResultsScreen(emit) {
  const root = element(
    `<section class="results-screen"><header class="results-heading"><h1 class="results-title"></h1><p class="results-subtitle muted"></p></header><div class="results-body"></div><div class="standings-timer phase-timer"><p class="next-phase" role="status"></p><div class="phase-track" aria-hidden="true"><span class="phase-fill"></span></div></div><div class="results-actions"><button class="button button-primary back-lobby" type="button">Back to lobby →</button><button class="button button-outline view-history" type="button">Room history</button></div></section>`,
  );
  const reveal = createRevealView();
  const standings = createStandingsView();
  root.querySelector(".results-body").append(reveal.element, standings.element);
  const find = (selector) => root.querySelector(selector);
  let model;
  find(".back-lobby").addEventListener("click", () => emit("back-lobby"));
  find(".view-history").addEventListener("click", () => emit("show-history"));
  function update(vm) {
    model = vm;
    const game = vm.state?.game;
    if (!game) return;
    const finished = ["completed", "aborted"].includes(game.status);
    const showingReveal =
      game.phase === "reveal" && Boolean(game.round?.reveal);
    root.dataset.phase = showingReveal ? "reveal" : "leaderboard";
    reveal.element.hidden = !showingReveal;
    standings.element.hidden = showingReveal;
    find(".results-actions").hidden = !finished;
    find(".standings-timer").hidden = showingReveal || finished;
    text(
      find(".results-title"),
      showingReveal
        ? "Round complete!"
        : game.status === "aborted"
          ? "Match ended early"
          : "Leaderboard",
    );
    text(
      find(".results-subtitle"),
      game.status === "aborted"
        ? `${END_REASONS[game.end_reason] ?? "The match could not continue."} These are the partial rankings.`
        : showingReveal
          ? "Here’s the reveal."
          : finished
            ? "Final standings."
            : "Current standings after this round.",
    );
    if (showingReveal) reveal.update(vm.state);
    else standings.update(game.leaderboard, vm.state.me.id);
    find(".back-lobby").disabled =
      Boolean(vm.ui.pending) || Boolean(vm.ui.disconnected);
    tick(vm.now);
  }
  function tick(now) {
    const game = model?.state?.game;
    if (!game) return;
    const timing = phaseProgress(game, now);
    for (const timer of root.querySelectorAll(".phase-timer")) {
      timer.hidden =
        !timing ||
        (timer.classList.contains("standings-timer") &&
          game.phase === "reveal");
      if (!timing) continue;
      text(
        timer.querySelector(".next-phase"),
        `${timing.label} in ${timing.seconds}s`,
      );
      timer.querySelector(".phase-fill").style.transform =
        `scaleX(${timing.fraction})`;
    }
  }
  return {
    element: root,
    update,
    tick,
    destroy() {
      model = null;
      reveal.destroy();
      standings.destroy();
    },
  };
}
