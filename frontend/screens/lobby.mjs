import "../components/color-picker.mjs";
import "../components/player-card.mjs";
import { startReadiness } from "../game/lobby-readiness.mjs";
import { syncKeyedChildren } from "../dom.mjs";

export function createLobbyScreen(emit) {
  const element = document.createElement("section");
  element.className = "lobby-screen";
  element.innerHTML = `
    <div class="lobby-intro"><h1>Your room is ready!<span class="heading-spark" aria-hidden="true">✦</span></h1>
      <p>Share the code with your friends and get ready to play.</p>
      <p class="playtest-note" hidden>Playtest mode: two players can start, and a Spotify account can join more than once.</p></div>
    <div class="lobby-top">
      <div class="character-gathering" aria-hidden="true">
        <span class="floating-note note-one">♪</span><span class="floating-note note-two">♫</span>
        <repeat-character color="lavender" mood="listening" class="gathering-small"></repeat-character>
        <repeat-character color="coral" mood="listening" class="gathering-large"></repeat-character>
        <repeat-character color="lemon" mood="celebrating" class="gathering-small"></repeat-character>
      </div>
      <div class="room-code-card surface-card"><span class="eyebrow">Room code</span>
        <div class="room-code-line"><strong class="room-code"></strong><button class="icon-button copy-code" type="button" aria-label="Copy room code"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7V3h7l5 5v13H9zM16 3v5h5M5 7H3v14h2"/></svg></button></div>
        <button class="button button-soft share-room" type="button"><span aria-hidden="true">↗</span> Share link</button>
      </div>
      <div class="color-picker-card surface-card"><h2>Your color</h2><blob-color-picker preview></blob-color-picker></div>
    </div>
    <div class="lobby-roster"><h2 class="roster-title">Players</h2><div class="lobby-player-row"></div>
      <button class="invite-tile" type="button"><span aria-hidden="true">+</span>Invite a friend</button></div>
    <div class="lobby-footer"><div class="settings-bar">
      <label><span aria-hidden="true">♫</span> Rounds <select name="round_count" aria-label="Rounds"><option value="5">5</option><option value="10">10</option><option value="15">15</option></select></label>
      <label><span aria-hidden="true">◷</span> Song length <select name="answer_seconds" aria-label="Song length"><option value="10">10 seconds</option><option value="20">20 seconds</option><option value="30">30 seconds</option></select></label>
      <details class="extra-settings"><summary>Game settings <span aria-hidden="true">⌄</span></summary><div class="extra-settings-panel surface-card">
        <label>Difficulty <select name="difficulty"><option value="easy">Easy</option><option value="mixed">Mixed</option><option value="hard">Hard</option></select></label>
        <label class="checkbox-label"><input type="checkbox" name="decoys_enabled"> Include songs nobody knows</label>
      </div></details>
    </div><div class="lobby-buttons"><button class="button button-primary start-game" type="button">Start game <span aria-hidden="true">→</span></button>
      <button class="button button-outline invite-friends" type="button">Invite friends <span aria-hidden="true">↗</span></button></div>
      <p class="start-hint" id="start-hint" role="status"></p><div class="host-audio-controls"></div>
    </div>`;
  const find = (selector) => element.querySelector(selector);
  const cards = new Map();
  const picker = find("blob-color-picker");
  picker.addEventListener("color-select", (event) =>
    emit("character", event.detail.color),
  );
  for (const [selector, action] of [
    [".copy-code", "copy-code"],
    [".share-room", "share-room"],
    [".invite-tile", "invite"],
    [".invite-friends", "invite"],
    [".start-game", "start"],
  ]) {
    find(selector).addEventListener("click", () => emit(action));
  }
  find(".settings-bar").addEventListener("change", (event) => {
    if (!event.target.name) return;
    const { name, value, checked, type } = event.target;
    emit("setting", {
      name,
      value:
        type === "checkbox"
          ? checked
          : ["round_count", "answer_seconds"].includes(name)
            ? Number(value)
            : value,
    });
  });
  function update(vm) {
    const { state, ui, audio } = vm;
    if (!state) return;
    const players = state.players;
    find(".playtest-note").hidden = !state.room.playtest;
    find(".room-code").textContent = state.room.code;
    picker.value = ui.character || state.me.character_id;
    picker.disabled = Boolean(ui.pending);
    const capacity = state.room.maximum_players ?? (state.room.mode === "normal" ? 5 : 10);
    find(".roster-title").textContent = `Players (${players.length}/${capacity})`;
    syncKeyedChildren(find(".lobby-player-row"), players, cards, {
      key: (player) => player.id,
      create: () => document.createElement("player-card"),
      update: (card, player) => {
        card.data = {
          ...player,
          status: !player.connected
            ? "joining"
            : player.song_count >= 10
              ? "ready"
              : "not-ready",
          variant: "lobby",
          selectable: false,
        };
      },
    });
    for (const input of find(".settings-bar").querySelectorAll(
      "select, input",
    )) {
      if (input.type === "checkbox") input.checked = state.settings[input.name];
      else input.value = state.settings[input.name];
      input.disabled = !state.me.is_host || Boolean(ui.pending);
    }
    const readiness = startReadiness(state, ui, audio);
    const start = find(".start-game");
    start.disabled = !readiness.canStart;
    start.setAttribute("aria-describedby", "start-hint");
    start.textContent =
      ui.pending === "start"
        ? "Starting…"
        : state.me.is_host
          ? "Start game →"
          : "Waiting for host";
    find(".start-hint").textContent = readiness.reason;
    const audioControls = find(".host-audio-controls");
    const audioAction =
      state.me.is_host && (!audio.unlocked || !audio.leaseId)
        ? audio.conflict
          ? "takeover-audio"
          : "enable-audio"
        : null;
    if (audioControls.dataset.action !== String(audioAction)) {
      audioControls.replaceChildren();
      audioControls.dataset.action = String(audioAction);
      if (audioAction) {
        const button = document.createElement("button");
        button.className = "button button-outline";
        button.type = "button";
        button.textContent =
          audioAction === "takeover-audio"
            ? "Use audio in this tab"
            : "Enable shared audio";
        button.addEventListener("click", () => emit(audioAction));
        audioControls.append(button);
      }
    }
    const audioButton = audioControls.querySelector("button");
    if (audioButton) audioButton.disabled = Boolean(ui.pending);
  }
  return {
    element,
    update,
    destroy() {
      cards.clear();
    },
  };
}
