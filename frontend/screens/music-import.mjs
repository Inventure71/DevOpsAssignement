import "../components/character.mjs";

export function createMusicImportScreen(retry, back) {
  const element = document.createElement("section");
  element.className = "music-import-screen surface-card";
  element.innerHTML = `<repeat-character mood="listening" aria-hidden="true"></repeat-character>
    <h1>Getting your music ready</h1><p role="status" aria-live="polite"></p>
    <p class="import-counts" hidden></p>
    <button class="button button-primary" type="button" hidden>Retry connection →</button>
    <button class="button button-outline import-back" type="button" hidden>Back to Spotify sign-in →</button>`;
  const heading = element.querySelector("h1");
  const character = element.querySelector("repeat-character");
  const status = element.querySelector("p");
  const counts = element.querySelector(".import-counts");
  const button = element.querySelector("button");
  const backButton = element.querySelector(".import-back");
  button.addEventListener("click", retry);
  backButton.addEventListener("click", back);
  return {
    element,
    update({ ui }) {
      const progress = ui.musicImport;
      const failed = progress.status === "failed";
      heading.textContent = failed
        ? "Couldn't get your music ready"
        : "Getting your music ready";
      character.setAttribute("mood", failed ? "sad" : "listening");
      character.setAttribute("color", ui.character || "coral");
      element.dataset.status = progress.status;
      element.setAttribute("aria-busy", String(!failed && progress.status !== "interrupted"));
      button.hidden = progress.status !== "interrupted";
      backButton.hidden = !failed;
      const details = progress.error?.details;
      const hasCounts = failed &&
        Number.isInteger(details?.candidate_count) &&
        Number.isInteger(details?.playable_count);
      counts.hidden = !hasCounts;
      counts.textContent = hasCounts
        ? `${details.playable_count} of ${details.candidate_count} imported songs have a usable preview. At least 10 are needed.`
        : "";
      status.textContent = progress.error?.message || progress.message ||
        (progress.reconnecting
          ? "Reconnecting… Your music import is still running."
          : progress.status === "pending"
            ? "Waiting for Spotify authorization…"
            : "Importing your songs and checking audio previews…");
    },
    destroy() {},
  };
}
