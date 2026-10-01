import "./character.mjs";
import { getBlobColor } from "./blob-palette.mjs";
import { element, syncKeyedChildren, text } from "../dom.mjs";
import { standingsModel } from "../game/results.mjs";

export function createStandingsView() {
  const view = element(
    '<div class="standings-view"><ol class="podium-grid" aria-label="Leading players"></ol><ol class="standings-list" aria-label="Remaining rankings"></ol><p class="standings-empty muted" hidden>No rankings yet.</p></div>',
  );
  const podium = new Map(),
    rows = new Map();
  function update(standings, me) {
    const model = standingsModel(standings);
    view.querySelector(".standings-empty").hidden = standings.length !== 0;
    const cards = view.querySelector(".podium-grid");
    cards.dataset.count = String(model.podium.length);
    syncKeyedChildren(cards, model.podium, podium, {
      key: (player) => player.player_id,
      create: () =>
        element(
          '<li class="podium-card"><span class="podium-rank"></span><svg class="podium-crown" viewBox="0 0 64 42" aria-label="First place" role="img"><path d="M7 33 3 9l16 12L32 2l13 19L61 9l-4 24zM9 39h46" fill="currentColor" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/></svg><repeat-character class="podium-character" mood="celebrating"></repeat-character><h2 class="podium-name"></h2><span class="podium-score"></span></li>',
        ),
      update: (card, player) => {
        paint(card, player, me);
        card.value = player.rank;
        card.dataset.place = String(model.podium.indexOf(player) + 1);
        card.dataset.rank = String(player.rank);
        text(card.querySelector(".podium-rank"), player.rank);
        card
          .querySelector(".podium-rank")
          .setAttribute("aria-label", `Rank ${player.rank}`);
        card
          .querySelector(".podium-crown")
          .toggleAttribute("hidden", player.rank !== 1);
        text(card.querySelector(".podium-name"), player.nickname);
        text(
          card.querySelector(".podium-score"),
          `${player.score.toLocaleString()} points`,
        );
      },
    });
    syncKeyedChildren(
      view.querySelector(".standings-list"),
      model.remaining,
      rows,
      {
        key: (player) => player.player_id,
        create: () =>
          element(
            '<li class="standing-row"><span class="standing-rank"></span><repeat-character class="standing-character" mood="idle"></repeat-character><span class="standing-name"></span><span class="standing-score"></span></li>',
          ),
        update: (row, player) => {
          paint(row, player, me);
          row.value = player.rank;
          text(row.querySelector(".standing-rank"), player.rank);
          text(row.querySelector(".standing-name"), player.nickname);
          text(
            row.querySelector(".standing-score"),
            `${player.score.toLocaleString()} points`,
          );
        },
      },
    );
  }
  function paint(node, player, me) {
    node.dataset.me = String(player.player_id === me);
    const palette = getBlobColor(player.character_id);
    node.style.setProperty("--player-wash", palette.light);
    node.style.setProperty("--player-accent", palette.accent);
    const sprite = node.querySelector("repeat-character");
    if (sprite.getAttribute("color") !== player.character_id)
      sprite.setAttribute("color", player.character_id);
  }
  return {
    element: view,
    update,
    destroy() {
      podium.clear();
      rows.clear();
    },
  };
}
