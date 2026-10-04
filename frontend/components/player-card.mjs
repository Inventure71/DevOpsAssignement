import "./character.mjs";
import { getBlobColor } from "./blob-palette.mjs";

const STATUS_LABELS = {
  listening: "Listening…",
  submitted: "Submitted!",
  ready: "Ready",
  "not-ready": "Not ready",
  joining: "Joining…",
};

const style = `
  :host { display: block; width: 148px; max-width: 100%; color: var(--ink, #161616); font-family: inherit; --selection-color: #a173ed; container-type: inline-size; }
  button { box-sizing: border-box; position: relative; display: flex; flex-direction: column; align-items: center; width: 100%; padding: 7px 10px 10px; border: 0; border-radius: 24px; color: inherit; background: transparent; font: inherit; -webkit-tap-highlight-color: transparent; -webkit-user-select: none; user-select: none; }
  button:not(:disabled) { cursor: pointer; }
  button:disabled { opacity: 1; }
  button:focus-visible { outline: 3px solid var(--selection-color); outline-offset: 5px; }
  .portrait { box-sizing: border-box; width: min(108px, 100%); aspect-ratio: 1; display: grid; place-items: center; position: relative; border: 4px solid transparent; border-radius: 50%; transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease; }
  repeat-character { width: 114%; margin-top: -6px; }
  button:not(:disabled):hover .portrait { transform: translateY(-3px); }
  :host([selected]) .portrait { border-color: color-mix(in srgb, var(--selection-color) 44%, white); background: color-mix(in srgb, var(--selection-color) 5%, transparent); }
  .selection { position: absolute; top: 5px; left: 5px; width: 19px; height: 19px; border-radius: 50%; background: #c9c9c5; box-shadow: 0 0 0 4px white, 0 0 0 6px #eeede9; transition: background-color 180ms ease, box-shadow 180ms ease; }
  :host([selected]) .selection { background: var(--selection-color); box-shadow: 0 0 0 4px white, 0 0 0 6px color-mix(in srgb, var(--selection-color) 25%, white); }
  :host(:not([selectable])) .selection { display: none; }
  .name { display: block; width: 100%; margin: 3px 0 6px; font-size: 16px; font-weight: 800; line-height: 1.2; overflow-wrap: anywhere; text-align: center; }
  .status { box-sizing: border-box; display: inline-flex; align-items: center; justify-content: center; gap: 6px; max-width: 100%; min-height: 29px; padding: 3px 12px; border-radius: 30px; background: #f2f1ee; color: #797874; font-size: 12px; line-height: 1.25; font-weight: 500; }
  .status-label { min-width: 0; overflow-wrap: anywhere; }
  .status svg { width: 14px; height: 14px; flex: none; }
  .check, .unready, .joining, .host-icon { display: none; }
  :host([status="submitted"]) .status, :host([status="ready"]) .status { color: #226327; background: #ecf5e5; font-weight: 650; }
  :host([status="submitted"]) .check, :host([status="ready"]) .check { display: block; }
  :host([status="not-ready"]) .unready { display: block; }
  :host([status="joining"]) .joining { display: block; animation: spin 2s linear infinite; }
  .crown { width: 24px; height: 20px; position: absolute; top: -7px; left: calc(50% - 12px); display: none; z-index: 1; color: #e9b247; }
  :host([host-player]) .crown { display: block; }
  :host([variant="lobby"]) { width: 136px; }
  :host([variant="lobby"]) button { padding: 17px 8px 12px; min-height: 162px; border: 1px solid rgba(44,35,20,.035); border-radius: 21px; background: rgba(255,255,255,.82); box-shadow: 0 8px 28px rgba(50,38,20,.035); }
  :host([variant="lobby"]) .portrait { width: min(92px, 100%); border-width: 3px; }
  :host([variant="lobby"]) repeat-character { width: 114%; }
  :host([variant="lobby"][host-player]) .status { color: #98711e; background: #fff6df; }
  :host([variant="lobby"][host-player]) .status svg { display: none; }
  :host([variant="lobby"][host-player]) .status .host-icon { display: block; }
  :host([disconnected]) .status { background: #f2f1ee; color: #797874; }
  :host([disconnected]) .status svg { display: none; }
  :host([disconnected]) .portrait { opacity: .65; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @container (max-width: 112px) {
    button { padding-inline: 4px; }
    .name { font-size: 14px; }
    .status { padding-inline: 5px; gap: 4px; font-size: 10px; }
    .status svg { width: 12px; height: 12px; }
    .selection { width: 15px; height: 15px; top: 6px; left: 3px; }
  }
  @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
`;

class PlayerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${style}</style>
      <button type="button" disabled>
        <svg class="crown" viewBox="0 0 24 20" fill="currentColor" aria-hidden="true"><path d="M3 15 1 4l6 4 5-7 5 7 6-4-2 11Z"/><rect x="3" y="16" width="18" height="3" rx="1"/></svg>
        <span class="selection" aria-hidden="true"></span>
        <span class="portrait"><repeat-character></repeat-character></span>
        <span class="name"></span>
        <span class="status">
          <svg class="check" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="8" fill="currentColor"/><path d="m4.6 8 2.1 2.1 4.7-4.6" fill="none" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <svg class="unready" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
          <svg class="joining" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="1 3" stroke-linecap="round"/></svg>
          <svg class="host-icon" viewBox="0 0 24 20" fill="currentColor" aria-hidden="true"><path d="M3 15 1 4l6 4 5-7 5 7 6-4-2 11Z"/></svg>
          <span class="status-label"></span>
        </span>
      </button>`;
    this._button = this.shadowRoot.querySelector("button");
    this._character = this.shadowRoot.querySelector("repeat-character");
    this._name = this.shadowRoot.querySelector(".name");
    this._status = this.shadowRoot.querySelector(".status-label");
    this._button.addEventListener("click", () => {
      if (!this._data?.selectable || this._data.disabled) return;
      this.dispatchEvent(
        new CustomEvent("player-select", {
          bubbles: true,
          composed: true,
          detail: { id: this._data.id },
        }),
      );
    });
  }

  set data(value) {
    this._data = value ?? {};
    const {
      nickname = "",
      character_id = "coral",
      status = "not-ready",
      is_host = false,
      connected = true,
      selected = false,
      selectable = false,
      disabled = false,
      variant = "round",
    } = this._data;
    const color = getBlobColor(character_id);
    this._setAttribute("variant", variant);
    this._setAttribute("status", status);
    this.toggleAttribute("selected", Boolean(selected));
    this.toggleAttribute("selectable", Boolean(selectable));
    this.toggleAttribute("host-player", Boolean(is_host));
    this.toggleAttribute("disconnected", !connected);
    this.style.setProperty("--selection-color", color.accent);
    if (this._name.textContent !== nickname) this._name.textContent = nickname;
    const label = !connected
      ? "Disconnected"
      : variant === "lobby" && is_host
        ? "Host"
        : (STATUS_LABELS[status] ?? "Not ready");
    if (this._status.textContent !== label) this._status.textContent = label;
    if (this._character.getAttribute("color") !== color.id)
      this._character.setAttribute("color", color.id);
    const mood =
      connected && status === "listening"
        ? "listening"
        : status === "submitted"
          ? "submitted"
          : "idle";
    if (this._character.getAttribute("mood") !== mood)
      this._character.setAttribute("mood", mood);
    this._button.disabled = Boolean(disabled || !selectable);
    this._button.setAttribute(
      "aria-label",
      `${nickname}, ${label}${selectable ? ", select listener" : ""}`,
    );
    if (selectable)
      this._button.setAttribute("aria-pressed", String(Boolean(selected)));
    else this._button.removeAttribute("aria-pressed");
  }

  get data() {
    return this._data;
  }

  _setAttribute(name, value) {
    if (this.getAttribute(name) !== value) this.setAttribute(name, value);
  }
}

if (!customElements.get("player-card"))
  customElements.define("player-card", PlayerCard);
