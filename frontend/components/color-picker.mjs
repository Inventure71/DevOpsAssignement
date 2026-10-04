import "./character.mjs";
import { BLOB_COLORS, getBlobColor } from "./blob-palette.mjs";

const styles = `
  :host { display:block; font-family:inherit; color:var(--ink,#171717); }
  * { box-sizing:border-box; }
  .preview { display:flex; align-items:center; justify-content:center; gap:9px; margin:10px 0 12px; -webkit-user-select:none; user-select:none; }
  .preview[hidden] { display:none; }
  repeat-character { display:block; width:172px; height:157px; max-width:calc(100% - 92px); }
  .step { display:grid; place-items:center; flex:none; width:40px; height:40px; border:1px solid #eeedf0; border-radius:50%; background:white; color:inherit; font:inherit; font-size:30px; box-shadow:0 3px 10px #17171706; cursor:pointer; }
  .swatches { display:flex; justify-content:center; flex-wrap:wrap; gap:8px; }
  .swatch { display:grid; place-items:center; width:30px; height:30px; padding:0; border:2px solid transparent; border-radius:50%; background:transparent; cursor:pointer; transition:transform 150ms ease,border-color 150ms ease; }
  .swatch:hover:not(:disabled) { transform:translateY(-2px); }
  .swatch[aria-pressed=true] { border-color:#1b1b1b; }
  .chip { display:grid; place-items:center; width:22px; height:22px; border-radius:50%; background:var(--chip); }
  .check { width:15px; height:15px; fill:none; stroke:#1b1b1b; stroke-width:2.3; stroke-linecap:round; stroke-linejoin:round; visibility:hidden; }
  .swatch[aria-pressed=true] .check { visibility:visible; }
  .label { margin:9px 0 0; text-align:center; color:var(--muted,#727383); font-size:13px; font-weight:750; line-height:1.35; }
  button:disabled { cursor:default; opacity:.6; }
  button { -webkit-user-select:none; user-select:none; }
  button:focus-visible { outline:3px solid #8f67c5; outline-offset:4px; }
  @media(prefers-reduced-motion:reduce) { button { transition:none; } }
`;

/** One palette control shared by admission, lobby and standalone design fixtures. */
class BlobColorPicker extends HTMLElement {
  static observedAttributes = ["preview", "disabled", "value"];

  constructor() {
    super();
    this._value = BLOB_COLORS[0].id;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${styles}</style>
      <div class="preview" hidden><button class="step previous" type="button" aria-label="Previous color">‹</button><button class="step next" type="button" aria-label="Next color">›</button></div>
      <div class="swatches" role="group" aria-label="Choose your color"></div><p class="label"></p>`;
    this._preview = this.shadowRoot.querySelector(".preview");
    this._character = null;
    this._swatches = this.shadowRoot.querySelector(".swatches");
    this._label = this.shadowRoot.querySelector(".label");
    for (const color of BLOB_COLORS) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "swatch";
      button.dataset.color = color.id;
      button.setAttribute("aria-label", `Choose ${color.label}`);
      button.style.setProperty("--chip", color.main);
      button.innerHTML =
        '<span class="chip" aria-hidden="true"><svg class="check" viewBox="0 0 18 18"><path d="m4 9 3 3 7-7"/></svg></span>';
      this._swatches.append(button);
    }
    this._swatches.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-color]");
      if (button) this._select(button.dataset.color);
    });
    this._swatches.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
      event.preventDefault();
      const buttons = [...this._swatches.children];
      const current = Math.max(0, buttons.indexOf(event.target));
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : (current +
                (event.key === "ArrowRight" ? 1 : -1) +
                buttons.length) %
              buttons.length;
      if (!this.disabled) {
        buttons[next].focus();
        this._select(buttons[next].dataset.color);
      }
    });
    this.shadowRoot
      .querySelector(".previous")
      .addEventListener("click", () => this._step(-1));
    this.shadowRoot
      .querySelector(".next")
      .addEventListener("click", () => this._step(1));
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue) return;
    if (name === "value") {
      const color = getBlobColor(newValue).id;
      const changed = this._value !== color;
      this._value = color;
      this._render();
      if (changed && this.hasAttribute("preview"))
        this._character?.react?.("greet");
    } else this._render();
  }

  set value(value) {
    const color = getBlobColor(value).id;
    if (this.getAttribute("value") !== color) this.setAttribute("value", color);
  }
  get value() {
    return this._value;
  }
  set disabled(value) {
    this.toggleAttribute("disabled", Boolean(value));
  }
  get disabled() {
    return this.hasAttribute("disabled");
  }

  _step(direction) {
    const index = BLOB_COLORS.findIndex((color) => color.id === this._value);
    this._select(
      BLOB_COLORS[(index + direction + BLOB_COLORS.length) % BLOB_COLORS.length]
        .id,
    );
  }

  _select(color) {
    if (this.disabled || color === this._value) return;
    this.value = color;
    this.dispatchEvent(
      new CustomEvent("color-select", {
        bubbles: true,
        composed: true,
        detail: { color: this._value },
      }),
    );
  }

  _render() {
    if (!this._swatches) return;
    const color = getBlobColor(this._value);
    this._preview.hidden = !this.hasAttribute("preview");
    if (this.hasAttribute("preview") && !this._character) {
      this._character = document.createElement("repeat-character");
      this._character.setAttribute("mood", "listening");
      this._character.setAttribute("aria-hidden", "true");
      this._preview.insertBefore(
        this._character,
        this._preview.querySelector(".next"),
      );
    } else if (!this.hasAttribute("preview") && this._character) {
      this._character.remove();
      this._character = null;
    }
    if (this._character && this._character.getAttribute("color") !== color.id)
      this._character.setAttribute("color", color.id);
    for (const button of this._swatches.children) {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.color === color.id),
      );
      button.disabled = this.disabled;
    }
    for (const button of this._preview.querySelectorAll("button"))
      button.disabled = this.disabled;
    if (this._label.textContent !== color.label)
      this._label.textContent = color.label;
  }
}

if (!customElements.get("blob-color-picker"))
  customElements.define("blob-color-picker", BlobColorPicker);
