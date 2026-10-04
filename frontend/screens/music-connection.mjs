import "../components/character.mjs";
import { syncKeyedChildren, text } from "../dom.mjs";

export function createMusicConnectionScreen(emit) {
  const element = document.createElement("section");
  element.className = "music-connection-screen surface-card";
  element.innerHTML = `<repeat-character mood="listening" aria-hidden="true"></repeat-character>
    <h1>Connect your music</h1><p class="connection-intro">Bring your favorites to the game.</p>
    <div class="music-provider-list" aria-label="Music providers"></div>
    <p class="connection-status" role="status" aria-live="polite"></p>
    <p class="form-error" role="alert"></p>
    <a class="canonical-address" hidden>Open configured game address →</a>
    <button class="button button-outline config-retry" type="button" hidden>Try again</button>
    <button class="button button-outline connection-back" type="button">← Back</button>`;
  const find = (selector) => element.querySelector(selector);
  const providerNodes = new Map();
  find(".connection-back").addEventListener("click", () => emit("music-back"));
  find(".config-retry").addEventListener("click", () => emit("retry-music-config"));
  return {
    element,
    update({ ui }) {
      const connection = ui.musicConnection;
      const busy = Boolean(ui.pending);
      find("repeat-character").setAttribute("color", connection.fields.character_id || "coral");
      syncKeyedChildren(find(".music-provider-list"), Object.values(connection.providers || {}), providerNodes, {
        key: (provider) => provider.id,
        create(provider) {
          const button = document.createElement("button");
          button.className = "music-provider";
          button.type = "button";
          button.dataset.provider = provider.id;
          button.innerHTML = '<span class="provider-mark" aria-hidden="true"></span><span><strong></strong><small></small></span><span class="provider-arrow" aria-hidden="true">→</span>';
          button.addEventListener("click", () => emit("connect-music", provider.id));
          return button;
        },
        update(button, provider) {
          button.disabled = busy || connection.loading || !provider.enabled;
          text(button.querySelector(".provider-mark"), provider.id === "apple" ? "♫" : "♪");
          text(button.querySelector("strong"), provider.label);
          text(button.querySelector("small"), provider.enabled ? "Connect your account" : provider.reason || "Unavailable in this session.");
          button.querySelector(".provider-arrow").hidden = !provider.enabled;
        },
      });
      find(".connection-status").textContent = connection.loading ? "Checking music providers…" : ui.pending === "connect-music" ? "Opening music sign-in…" : ui.pending === "music-back" ? "Returning…" : "";
      find(".form-error").textContent = connection.error || ui.error?.message || connection.configError || "";
      find(".config-retry").hidden = !connection.configError;
      find(".config-retry").disabled = busy;
      find(".connection-back").disabled = busy;
      const canonical = find(".canonical-address");
      canonical.hidden = !ui.canonicalUrl;
      if (ui.canonicalUrl) canonical.href = ui.canonicalUrl;
      else canonical.removeAttribute("href");
    },
    destroy() {},
  };
}
