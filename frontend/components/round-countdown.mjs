import { roundTiming } from "../game/timing.mjs";

// The upper 200-degree arc leaves room for the controls.
class RoundCountdown extends HTMLElement {
  #data = {};
  constructor() {
    super();
    this.attachShadow({ mode: "open" }).innerHTML = `
      <style>
        :host { display:block; }
        svg { display:block; width:100%; height:auto; overflow:visible; }
        path { fill:none; stroke-width:22; stroke-linecap:round; }
        .track { stroke:var(--arc-track,#f2f0ed); }
        .remaining { stroke:var(--arc-color,#ffb8b2); }
        :host([submitted]) .remaining { opacity:.2; }
        :host([submitted]) .track { stroke:#fcf1ee; }
      </style>
      <svg viewBox="0 0 440 278" aria-hidden="true">
        <path class="track" d="M19.10 255.42A204 204 0 1 1 420.90 255.42"/>
        <path class="remaining" d="M19.10 255.42A204 204 0 1 1 420.90 255.42" pathLength="100"/>
      </svg>`;
    this.arc = this.shadowRoot.querySelector(".remaining");
  }
  connectedCallback() {
    this.setAttribute("role", "progressbar");
    this.setAttribute("aria-label", "Time remaining");
    this.setAttribute("aria-valuemin", "0");
    this.tick(this.#data.now);
  }
  set data(value) {
    this.#data = value ?? {};
    this.toggleAttribute("submitted", Boolean(value?.submitted));
    this.tick(value?.now);
  }
  tick(now) {
    const timing = roundTiming({ ...this.#data, now });
    const preparing = ["ready", "countdown"].includes(this.#data.phase);
    const fraction = preparing
      ? 1
      : this.#data.phase === "answering"
        ? timing.remainingFraction
        : 0;
    this.arc.style.strokeDasharray = `${fraction * 100} 100`;
    this.arc.style.visibility = fraction > 0 ? "visible" : "hidden";
    const total = Math.max(1, Math.ceil(timing.duration / 1000));
    const remaining = Math.ceil(timing.remaining / 1000);
    for (const [attribute, value] of [
      ["aria-valuemax", String(total)],
      ["aria-valuenow", String(preparing ? total : remaining)],
      [
        "aria-valuetext",
        preparing ? "Getting ready" : `${remaining} seconds remaining`,
      ],
    ])
      if (this.getAttribute(attribute) !== value)
        this.setAttribute(attribute, value);
  }
}
customElements.define("round-countdown", RoundCountdown);
