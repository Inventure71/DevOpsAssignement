import "./character.mjs";
import { text } from "../dom.mjs";

// One revealed player and the local player's listener guess about them.
export class ListenerResult extends HTMLElement {
  connectedCallback() {
    if (this.firstElementChild) return;
    this.innerHTML = `<article class="listener-result"><repeat-character class="listener-character"></repeat-character><div class="listener-feedback"><h3 class="listener-name"></h3><span class="result-badge selection-badge"></span><span class="result-badge listener-verdict"></span><span class="listener-actual"></span></div></article>`;
    if (this._data) this.data = this._data;
  }
  set data(player) {
    this._data = player;
    if (!this.firstElementChild) return;
    const sprite = this.querySelector("repeat-character");
    for (const [attribute, value] of [
      ["color", player.character_id],
      ["mood", player.mood],
    ])
      if (sprite.getAttribute(attribute) !== value)
        sprite.setAttribute(attribute, value);
    text(this.querySelector(".listener-name"), player.nickname);
    const selection = this.querySelector(".selection-badge");
    text(selection, player.selection);
    selection.dataset.tone = player.selected ? "selected" : "neutral";
    const verdict = this.querySelector(".listener-verdict");
    text(
      verdict,
      `${player.tone === "correct" ? "✓ " : player.tone === "wrong" ? "× " : ""}${player.verdict}`,
    );
    verdict.dataset.tone = player.tone;
    verdict.setAttribute(
      "aria-label",
      `Listener guess: ${player.verdict.toLowerCase()}`,
    );
    text(
      this.querySelector(".listener-actual"),
      player.actual ? "In their collection" : "Not in their collection",
    );
  }
}
customElements.define("listener-result", ListenerResult);
