import "../components/character.mjs";
import { musicPreparation } from "../game/preparation.mjs";

export function createMusicImportScreen(retry, back) {
  const element = document.createElement("section");
  element.className = "music-import-screen surface-card";
  element.innerHTML = `<repeat-character mood="listening" aria-hidden="true"></repeat-character>
    <h1>Getting your music ready</h1><p role="status" aria-live="polite"></p>
    <button class="button button-primary" type="button" hidden>Retry connection →</button>
    <button class="button button-outline import-back" type="button" hidden>Back to Spotify sign-in →</button>`;
  const heading = element.querySelector("h1");
  const character = element.querySelector("repeat-character");
  const status = element.querySelector("p");
  const button = element.querySelector("button");
  const backButton = element.querySelector(".import-back");
  button.addEventListener("click", retry);
  backButton.addEventListener("click", back);
  return {
    element,
    update({ ui }) {
      const progress = ui.musicImport;
      const failed = progress.status === "failed";
      const preparation = musicPreparation(progress);
      heading.textContent = preparation.title;
      character.setAttribute("mood", failed ? "sad" : "listening");
      character.setAttribute("color", ui.character || "coral");
      element.dataset.status = progress.status;
      element.setAttribute("aria-busy", String(preparation.busy));
      button.hidden = !preparation.retry;
      backButton.hidden = !preparation.back;
      status.textContent = preparation.message;
    },
    destroy() {},
  };
}
