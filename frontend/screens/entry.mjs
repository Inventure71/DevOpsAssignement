import "../components/color-picker.mjs";

export function createEntryScreen(emit) {
  const element = document.createElement("section");
  element.className = "entry-screen";
  element.innerHTML = `<div class="entry-welcome"><h1>Your music.<br>Your friends.<br>Who’s listening?</h1>
    <p>Guess the song, then guess who has it on repeat.</p>
    <div class="entry-art" aria-hidden="true"><repeat-character color="lavender" mood="listening"></repeat-character><repeat-character color="coral" mood="listening"></repeat-character><repeat-character color="lemon" mood="celebrating"></repeat-character></div>
    </div><div class="surface-card"><div class="entry-tabs" role="group" aria-label="Create or join a room"><button type="button" data-tab="create">Create a room</button><button type="button" data-tab="join">Join a room</button></div>
    <form class="entry-form"><div class="field-group"><label for="player-nickname">Your nickname</label><input id="player-nickname" name="nickname" type="text" placeholder="Your friends know you as…" autocomplete="nickname" maxlength="24" required></div>
      <div class="field-group entry-code-field"><label for="join-room-code">Room code</label><input id="join-room-code" name="code" type="text" placeholder="ABC123" inputmode="text" autocomplete="off" spellcheck="false" autocapitalize="characters" maxlength="6" minlength="6" pattern="[A-Za-z0-9]{6}"></div>
      <div class="field-group"><span class="entry-color-label" id="entry-color-label">Your color</span><blob-color-picker aria-labelledby="entry-color-label"></blob-color-picker></div>
      <fieldset class="entry-mode-field"><legend>Music source</legend><div class="entry-mode-options">
        <label><input type="radio" name="mode" value="normal" checked>Spotify</label><label><input type="radio" name="mode" value="demo">Demo</label>
      </div></fieldset>
      <p class="mode-label" id="entry-mode-help"></p><button class="button button-primary entry-submit" type="submit" aria-describedby="entry-mode-help">Connect Spotify →</button>
      <p class="form-error" role="status" aria-live="polite"></p><a class="canonical-address" hidden>Open configured game address →</a>
    </form></div>`;
  const nickname = element.querySelector("[name=nickname]");
  const code = element.querySelector("[name=code]");
  const form = element.querySelector("form");
  const submit = element.querySelector(".entry-submit");
  const picker = element.querySelector("blob-color-picker");
  const tabs = element.querySelector(".entry-tabs");
  const modes = element.querySelector(".entry-mode-field");
  modes.addEventListener("change", (event) => {
    if (event.target.name === "mode") emit("entry-mode", event.target.value);
  });
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) emit("entry-tab", button.dataset.tab);
  });
  picker.addEventListener("color-select", (event) =>
    emit("character", event.detail.color),
  );
  nickname.addEventListener("input", () =>
    emit("draft", { name: "nickname", value: nickname.value }),
  );
  code.addEventListener("input", () => {
    code.value = code.value.toUpperCase();
    emit("draft", { name: "code", value: code.value });
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (form.reportValidity()) {
      // Autofill can change a field without delivering an input event.
      emit("draft", { name: "nickname", value: nickname.value });
      emit("draft", { name: "code", value: code.value });
      emit("admit");
    }
  });
  function update(vm) {
    const { ui } = vm;
    const joining = ui.screen === "join";
    if (document.activeElement !== nickname)
      nickname.value = ui.draftNickname ?? "";
    if (document.activeElement !== code) code.value = ui.draftCode ?? "";
    code.required = joining;
    modes.hidden = joining;
    modes.disabled = Boolean(ui.pending);
    for (const input of modes.querySelectorAll("input"))
      input.checked = input.value === (ui.mode || "normal");
    const modeHelp = element.querySelector(".mode-label");
    modeHelp.textContent = joining
      ? "Spotify rooms require sign-in. Demo rooms do not."
      : ui.mode === "demo"
        ? "Demo uses the demo catalog. No music account needed."
        : "Connect an approved Spotify account. Up to 5 accounts, including the host.";
    element.querySelector(".entry-code-field").hidden = !joining;
    for (const button of tabs.children) {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.tab === (joining ? "join" : "create")),
      );
      button.disabled = Boolean(ui.pending);
    }
    picker.value = ui.character || "coral";
    picker.disabled = Boolean(ui.pending);
    nickname.disabled = Boolean(ui.pending);
    code.disabled = !joining || Boolean(ui.pending);
    submit.disabled = Boolean(ui.pending);
    submit.textContent = ui.pending
      ? joining
        ? "Joining…"
        : "Creating…"
      : joining
        ? "Join room →"
        : ui.mode === "demo"
          ? "Create demo room →"
          : "Connect Spotify →";
    element.querySelector(".form-error").textContent = ui.error?.message ?? "";
    const canonical = element.querySelector(".canonical-address");
    canonical.hidden = !ui.canonicalUrl;
    if (ui.canonicalUrl) canonical.href = ui.canonicalUrl;
    else canonical.removeAttribute("href");
  }
  return { element, update, destroy() {} };
}
