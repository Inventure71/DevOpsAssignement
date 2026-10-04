import "../components/listener-result.mjs";
import { element, syncKeyedChildren, text } from "../dom.mjs";
import { roundResult } from "../game/results.mjs";

export function createRevealView() {
  const view = element(`<div class="reveal-view"><div class="reveal-layout">
    <div class="reveal-players reveal-players-left" aria-label="Your listener guesses"></div>
    <article class="reveal-panel"><div class="reveal-cover-wrap"><img class="reveal-artwork" alt="" hidden><div class="artwork-fallback" role="img" aria-label="Album artwork unavailable"><svg viewBox="0 0 80 80" aria-hidden="true"><path d="M31 53V19l32-7v33M31 28l32-7"/><ellipse cx="21" cy="55" rx="10" ry="7"/><ellipse cx="53" cy="47" rx="10" ry="7"/></svg></div></div>
    <h2 class="reveal-song-title"></h2><p class="reveal-song-artist muted"></p>
    <div class="guess-summary"><div class="guess-summary-row"><span>Song guess</span><span class="result-badge song-verdict"></span></div><div class="guess-summary-row"><span>Artist match</span><span class="result-badge artist-verdict"></span></div><div class="guess-summary-row"><span>Listener guesses</span><span class="result-badge listeners-verdict"></span></div></div>
    <p class="round-points"></p><p class="own-song-guess muted"></p><div class="phase-timer"><p class="next-phase" role="status"></p><div class="phase-track" aria-hidden="true"><span class="phase-fill"></span></div></div></article>
    <div class="reveal-players reveal-players-right" aria-label="Your listener guesses"></div>
    </div></div>`);
  const find = (selector) => view.querySelector(selector);
  const cards = [new Map(), new Map()];
  const image = find(".reveal-artwork"),
    fallback = find(".artwork-fallback");
  let artworkURL = null;
  image.addEventListener("error", () => {
    image.hidden = true;
    fallback.hidden = false;
  });
  image.addEventListener("load", () => {
    image.hidden = false;
    fallback.hidden = true;
  });
  function update(state) {
    const result = roundResult(state);
    if (!result) return;
    text(find(".reveal-song-title"), result.song.title);
    text(find(".reveal-song-artist"), result.song.artist);
    image.alt = `Cover artwork for ${result.song.title}`;
    const url = result.song.artwork_url || null;
    if (artworkURL !== url) {
      artworkURL = url;
      image.hidden = true;
      fallback.hidden = false;
      if (url) image.src = url;
      else image.removeAttribute("src");
    }
    for (const [selector, verdict] of [
      [".song-verdict", result.songVerdict],
      [".artist-verdict", result.artistVerdict],
      [".listeners-verdict", result.listenerVerdict],
    ]) {
      const badge = find(selector);
      text(badge, verdict.label);
      badge.dataset.tone = verdict.tone;
    }
    text(find(".round-points"), `+${result.points.toLocaleString()} points`);
    find(".round-points").dataset.tone =
      result.points > 0 ? "correct" : "neutral";
    text(find(".own-song-guess"), result.guessLabel);
    const midpoint = Math.ceil(result.players.length / 2);
    for (const [index, subset] of [
      result.players.slice(0, midpoint),
      result.players.slice(midpoint),
    ].entries()) {
      syncKeyedChildren(
        find(index ? ".reveal-players-right" : ".reveal-players-left"),
        subset,
        cards[index],
        {
          key: (player) => player.id,
          create: () => document.createElement("listener-result"),
          update: (card, player) => {
            card.data = player;
          },
        },
      );
    }
  }
  return {
    element: view,
    update,
    destroy() {
      cards.forEach((map) => map.clear());
    },
  };
}
