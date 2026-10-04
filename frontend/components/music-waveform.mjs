import {
  normalizedAppearance,
  normalizeLevels,
  waveformGeometry,
  waveformProgress,
} from "./waveform-drawing.mjs";

const SVG = "http://www.w3.org/2000/svg";
let serial = 0;
const format = (milliseconds) =>
  `${Math.floor(milliseconds / 60000)}:${String(Math.floor(milliseconds / 1000) % 60).padStart(2, "0")}`;
// Audio decoding and scheduling belong to the caller; this element only draws
// measured samples and the authoritative timeline. No private clocks or fetches.
class MusicWaveform extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = {};
    this._levels = [];
    this._appearance = normalizedAppearance();
    this._draw = null;
    this._width = 0;
    this._geometryKey = "";
    this._progress = -1;
    const clipId = `waveform-played-${++serial}`;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;font:700 14px Nunito,system-ui;color:#777383}*{box-sizing:border-box}
      .player{display:flex;align-items:center;gap:25px;border:1px solid #eeecec;border-radius:999px;padding:20px 26px;background:#fff;box-shadow:0 8px 35px #25252504}
      .wave{flex:1;min-width:0;height:46px;position:relative}.drawing{display:block;width:100%;height:100%;overflow:visible}
      .line{position:absolute;left:0;right:0;top:calc(50% - 3px);height:6px;background:var(--wave-unplayed);border-radius:8px;overflow:hidden}.fill{height:100%;width:0;background:var(--wave-played)}
      .time{white-space:nowrap;font-variant-numeric:tabular-nums}[hidden]{display:none!important}
      @media(max-width:600px){.player{padding:14px 17px;gap:13px}.time{font-size:12px}}
    </style><div class="player"><div class="wave" aria-hidden="true"><svg class="drawing" preserveAspectRatio="none"><defs><clipPath id="${clipId}"><rect class="clip" x="0" y="0" width="0"/></clipPath></defs><g class="unplayed"></g><g class="played" clip-path="url(#${clipId})"></g></svg><div class="line"><div class="fill"></div></div></div><span class="time"></span></div>`;
    this._player = this.shadowRoot.querySelector(".player");
    this._wave = this.shadowRoot.querySelector(".wave");
    this._drawing = this.shadowRoot.querySelector(".drawing");
    this._unplayed = this.shadowRoot.querySelector(".unplayed");
    this._played = this.shadowRoot.querySelector(".played");
    this._clip = this.shadowRoot.querySelector(".clip");
    this._line = this.shadowRoot.querySelector(".line");
    this._fill = this.shadowRoot.querySelector(".fill");
    this._time = this.shadowRoot.querySelector(".time");
    this._resize = new ResizeObserver((entries) => {
      const width = entries[0].contentRect.width;
      if (Math.abs(width - this._width) < 0.5) return;
      this._width = width;
      this._renderGeometry();
    });
    this._applyAppearance();
  }

  connectedCallback() {
    this._resize.observe(this._wave);
  }
  disconnectedCallback() {
    this._resize.disconnect();
  }

  set data(value) {
    this._data = value || {};
    const levels = normalizeLevels(value?.levels);
    if (
      levels.length !== this._levels.length ||
      levels.some((level, index) => level !== this._levels[index])
    ) {
      this._levels = levels;
      this._renderGeometry();
    }
    this.tick(value?.now ?? Date.now());
  }
  get data() {
    return this._data;
  }

  set appearance(value) {
    const next = normalizedAppearance(value || {});
    if (JSON.stringify(next) === JSON.stringify(this._appearance)) return;
    this._appearance = next;
    this._applyAppearance();
    this._renderGeometry();
  }
  get appearance() {
    return { ...this._appearance };
  }

  set draw(value) {
    if (value !== null && value !== undefined && typeof value !== "function")
      throw new TypeError("Waveform draw must be a function or null.");
    if ((value || null) === this._draw) return;
    this._draw = value || null;
    this._geometryKey = "";
    this._renderGeometry();
  }
  get draw() {
    return this._draw;
  }

  _applyAppearance() {
    const config = this._appearance;
    this._wave.style.height = `${config.height}px`;
    this._player.style.setProperty("--wave-played", config.playedColor);
    this._player.style.setProperty("--wave-unplayed", config.unplayedColor);
    this._played.setAttribute("color", config.playedColor);
    this._unplayed.setAttribute("color", config.unplayedColor);
  }

  _renderGeometry() {
    if (!this._width) return;
    const { mode, barCount, height, gap, barWidth, lineWidth } =
      this._appearance;
    const key = JSON.stringify([
      this._levels,
      this._width,
      mode,
      barCount,
      height,
      gap,
      barWidth,
      lineWidth,
    ]);
    if (key === this._geometryKey) return;
    const geometry = waveformGeometry(
      this._levels,
      this._width,
      this._appearance,
      this._draw,
    );
    this._geometryKey = key;
    this._drawing.setAttribute(
      "viewBox",
      `0 0 ${geometry.width} ${geometry.height}`,
    );
    this._clip.setAttribute("height", geometry.height);
    this._drawing.toggleAttribute("hidden", geometry.empty);
    this._line.hidden = !geometry.empty;
    for (const layer of [this._unplayed, this._played]) {
      const paths = geometry.paths.map(({ d, fill }) => {
        const path = document.createElementNS(SVG, "path");
        path.setAttribute("d", d);
        path.setAttribute("fill", fill ? "currentColor" : "none");
        path.setAttribute("stroke", "currentColor");
        path.setAttribute("stroke-width", geometry.strokeWidth);
        path.setAttribute("stroke-linecap", "round");
        path.setAttribute("stroke-linejoin", "round");
        return path;
      });
      layer.replaceChildren(...paths);
    }
    this._clip.setAttribute(
      "width",
      Math.max(0, this._progress) * geometry.width,
    );
  }

  tick(now) {
    const { duration, elapsed, progress } = waveformProgress(this._data, now);
    if (progress !== this._progress) {
      this._progress = progress;
      this._clip.setAttribute("width", progress * this._width);
      this._fill.style.width = `${progress * 100}%`;
    }
    const label = `${format(elapsed)} / ${format(duration)}`;
    if (this._time.textContent !== label) {
      this._time.textContent = label;
      this.setAttribute(
        "aria-label",
        `Shared audio: ${format(elapsed)} of ${format(duration)}`,
      );
    }
  }
}
customElements.define("music-waveform", MusicWaveform);
