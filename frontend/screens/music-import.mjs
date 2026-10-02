import "../components/character.mjs";

export function createMusicImportScreen(retry) {
  const element = document.createElement("section");
  element.className = "music-import-screen surface-card";
  element.innerHTML = `<repeat-character mood="listening" aria-hidden="true"></repeat-character>
    <h1>Getting your music ready</h1><p role="status" aria-live="polite"></p>
    <button class="button button-primary" type="button" hidden>Retry connection →</button>`;
  const status = element.querySelector("p");
  const button = element.querySelector("button");
  button.addEventListener("click", retry);
  return {
    element,
    update({ ui }) {
      const progress = ui.musicImport;
      element.querySelector("repeat-character").setAttribute(
        "color",
        ui.character || "coral",
      );
      element.setAttribute("aria-busy", String(progress.status !== "interrupted"));
      button.hidden = progress.status !== "interrupted";
      status.textContent = progress.message ||
        (progress.reconnecting
          ? "Reconnecting… Your music import is still running."
          : progress.status === "pending"
            ? "Waiting for Spotify authorization…"
            : "Importing your songs and checking audio previews…");
    },
    destroy() {},
  };
}
