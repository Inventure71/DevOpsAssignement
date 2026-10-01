import { element, text } from "../dom.mjs";

// Renders supplied history only. Fetching and navigation belong to the caller.
export function createHistoryScreen(onBack) {
  const section = element(
    '<section class="history-screen"><h1>Room history</h1><div class="history-games"></div><button class="button button-outline">Back to room</button></section>',
  );
  let signature;
  section.querySelector("button").addEventListener("click", onBack);
  return {
    element: section,
    update(vm) {
      const next = JSON.stringify(vm.ui.history);
      if (next === signature) return;
      signature = next;
      const list = section.querySelector(".history-games");
      list.replaceChildren();
      const games = vm.ui.history?.games;
      if (!games) {
        text(list, "Loading history…");
        return;
      }
      if (!games.length) {
        text(list, "No completed games yet.");
        return;
      }
      for (const game of games) {
        const item = document.createElement("article");
        item.className = "history-game";
        const title = document.createElement("h2");
        title.textContent = `${game.status === "completed" ? "Completed game" : "Partial game"} · ${new Date(game.ended_at_ms).toLocaleDateString()}`;
        const ranks = document.createElement("ol");
        for (const rank of game.leaderboard) {
          const row = document.createElement("li");
          row.textContent = `${rank.nickname} · ${rank.score} points`;
          ranks.append(row);
        }
        item.append(title, ranks);
        list.append(item);
      }
    },
    destroy() {},
  };
}
