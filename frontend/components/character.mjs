import { getBlobColor } from "./blob-palette.mjs";
import { sampleBlobMotion, deformBlob, springStep } from "./blob-rig.mjs";
import { createBlobMotionHub } from "./blob-motion.mjs";
import { sampleHeadphones } from "./blob-headphones.mjs";

// Geometry is shared. Each instance owns only its pose, face/gear springs and color.
const sprites = new Set();
const preference = matchMedia("(prefers-reduced-motion: reduce)");
const hub = createBlobMotionHub({
  requestFrame: (callback) => requestAnimationFrame(callback),
  cancelFrame: (frame) => cancelAnimationFrame(frame),
});
const clock = () => performance.now();
let serial = 0;
const visibility = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    entry.target._visible = entry.isIntersecting;
    entry.target._syncMotion();
  }
});
const sizes = new ResizeObserver((entries) => {
  for (const entry of entries) {
    entry.target._small = entry.contentRect.width <= 56;
    entry.target._syncMotion();
  }
});
function motionPreferenceChanged() {
  hub.setEnabled(!document.hidden && !preference.matches);
  for (const sprite of sprites) {
    sprite._syncMotion();
    if (preference.matches) sprite._paint(clock(), 0, true);
  }
}
document.addEventListener("visibilitychange", motionPreferenceChanged);
preference.addEventListener("change", motionPreferenceChanged);
motionPreferenceChanged();
export const blobMotionStats = () => hub.stats;

const style = `
  :host{display:inline-block;width:120px;flex:none;vertical-align:middle;contain:layout style}
  svg{display:block;width:100%;height:auto;overflow:visible;pointer-events:none}
  .eye-glint{opacity:0}
  :host([mood=idle]) .eye-glint,:host([mood=submitted]) .eye-glint,:host(:not([mood])) .eye-glint{opacity:.9}
  .eyes-closed,.eyes-happy,.sad-brows{opacity:0}
  :host([mood=listening]) .eyes-open{opacity:0}
  :host([mood=listening]) .eyes-closed{opacity:1}
  :host([mood=celebrating]) .eyes-open{opacity:0}
  :host([mood=celebrating]) .eyes-happy{opacity:1}
  :host([mood=sad]) .sad-brows{opacity:1}
  .color-light,.color-main,.color-dark{transition:stop-color 200ms ease}
  @media(prefers-reduced-motion:reduce){*{transition:none!important}}
`;
const spring = () => ({ value: 0, velocity: 0 });
export class RepeatCharacter extends HTMLElement {
  static observedAttributes = ["color", "mood"];
  constructor() {
    super();
    const uid = `repeat-blob-${++serial}`;
    this._phase = (serial * 0.43) % 7.2;
    this._moodStarted = clock();
    this._reactionStarted = -Infinity;
    this._reaction = "poke";
    this._departingHeadphones = false;
    this._visible = false;
    this._small = false;
    this._look = { x: 0, y: 0 };
    this._faceX = spring();
    this._faceY = spring();
    this._gearX = spring();
    this._gearY = spring();
    this._frame = (time, elapsed) => this._paint(time, elapsed);
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${style}</style>
      <svg viewBox="0 0 240 240" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="${uid}-paint" x1=".12" y1="0" x2=".85" y2="1"><stop class="color-light" offset="0"/><stop class="color-main" offset=".6"/><stop class="color-dark" offset="1"/></linearGradient>
          <radialGradient id="${uid}-shine"><stop offset="0" stop-color="white" stop-opacity=".36"/><stop offset="1" stop-color="white" stop-opacity="0"/></radialGradient>
          <clipPath id="${uid}-clip"><use href="#${uid}-body"/></clipPath>
        </defs>
        <ellipse class="shadow" cx="120" cy="218" rx="62" ry="6" fill="#706964" opacity=".1"/>
        <path class="body" id="${uid}-body" fill="url(#${uid}-paint)" stroke="#fff" stroke-opacity=".42" stroke-width="1.2"/>
        <g clip-path="url(#${uid}-clip)"><ellipse class="shine" cx="91" cy="101" rx="46" ry="65" fill="url(#${uid}-shine)"/></g>
        <g class="face">
          <ellipse cx="89" cy="143" rx="9" ry="4.2" fill="#df858b" opacity=".18"/>
          <ellipse cx="151" cy="143" rx="9" ry="4.2" fill="#df858b" opacity=".18"/>
          <g class="eyes-open" fill="#30252a"><g class="eye-left"><ellipse class="pupil" cx="102" cy="125" rx="5.8" ry="6.1"/><circle class="eye-glint" cx="100" cy="122.8" r="1.6" fill="#fff"/></g><g class="eye-right"><ellipse class="pupil" cx="138" cy="125" rx="5.8" ry="6.1"/><circle class="eye-glint" cx="136" cy="122.8" r="1.6" fill="#fff"/></g></g>
          <g class="sad-brows" fill="none" stroke="#59424a" stroke-width="2.6" stroke-linecap="round"><path d="M95 117Q101 117 105 112"/><path d="M135 112Q139 117 145 117"/></g>
          <g class="eyes-closed" fill="none" stroke="#231d22" stroke-width="4.5" stroke-linecap="round"><path d="M93 123Q99 133 105 123"/><path d="M135 123Q141 133 147 123"/></g>
          <g class="eyes-happy" fill="none" stroke="#231d22" stroke-width="4.5" stroke-linecap="round"><path d="M93 128Q99 118 105 128"/><path d="M135 128Q141 118 147 128"/></g>
          <path class="mouth" d="M113 139Q120 150 128 139" fill="none" stroke="#30252a" stroke-width="4.5" stroke-linecap="round"/>
        </g>
        <g class="headphones" opacity="0"><g class="gear">
          <path d="M61 119C56 12 184 12 179 119" fill="none" stroke="#211f21" stroke-width="8" stroke-linecap="round"/>
          <path d="M64 91C67 30 174 30 176 91" fill="none" stroke="#625d60" stroke-width="2" opacity=".7"/>
          <g class="ear-left"><g transform="rotate(7 60 124)"><rect x="48" y="99" width="21" height="47" rx="11" fill="#222022"/><rect x="48" y="103" width="13" height="39" rx="7" fill="#343034" stroke="#eee7e4" stroke-width="1"/></g></g>
          <g class="ear-right"><g transform="rotate(-7 180 124)"><rect x="171" y="99" width="21" height="47" rx="11" fill="#222022"/><rect x="179" y="103" width="13" height="39" rx="7" fill="#343034" stroke="#eee7e4" stroke-width="1"/></g></g>
        </g></g>
      </svg>`;
    const find = (selector) => this.shadowRoot.querySelector(selector);
    this._body = find(".body");
    this._shadow = find(".shadow");
    this._face = find(".face");
    this._gear = find(".gear");
    this._headphones = find(".headphones");
    this._earLeft = find(".ear-left");
    this._earRight = find(".ear-right");
    this._shine = find(".shine");
    this._mouth = find(".mouth");
    this._leftEye = find(".eye-left");
    this._rightEye = find(".eye-right");
    this._pupils = [...this.shadowRoot.querySelectorAll(".pupil")];
    this._stops = [".color-main", ".color-light", ".color-dark"].map(find);
    this.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch") return;
      const bounds = this.getBoundingClientRect();
      this._look.x = Math.max(
        -1,
        Math.min(1, ((event.clientX - bounds.left) / bounds.width) * 2 - 1),
      );
      this._look.y = Math.max(
        -1,
        Math.min(1, ((event.clientY - bounds.top) / bounds.height) * 2 - 1),
      );
    });
    this.addEventListener("pointerleave", () => {
      this._look.x = 0;
      this._look.y = 0;
    });
    this.addEventListener("pointerdown", () => this.react("poke"));
    this._updateColor();
    this._paint(clock(), 0, true);
  }
  connectedCallback() {
    this.setAttribute("aria-hidden", "true");
    sprites.add(this);
    visibility.observe(this);
    sizes.observe(this);
    this._updateColor();
    this._paint(clock(), 0, true);
  }
  disconnectedCallback() {
    this._unsubscribe?.();
    this._unsubscribe = null;
    visibility.unobserve(this);
    sizes.unobserve(this);
    sprites.delete(this);
  }
  attributeChangedCallback(name, previous, current) {
    if (previous === current) return;
    if (name === "color") this._updateColor();
    if (name === "mood") {
      this._departingHeadphones =
        previous === "listening" &&
        current === "submitted" &&
        Boolean(this._unsubscribe);
      this._transitionFrom = this._lastMotion;
      this._moodStarted = clock();
      if (this._body && !this._unsubscribe) this._paint(clock(), 0, true);
    }
  }
  react(kind = "poke") {
    if (preference.matches) return;
    this._reaction = kind === "greet" ? "greet" : "poke";
    this._reactionStarted = clock();
    this._syncMotion();
  }
  _updateColor() {
    if (!this._stops) return;
    const color = getBlobColor(this.getAttribute("color"));
    [color.main, color.light, color.dark].forEach((value, index) =>
      this._stops[index].setAttribute("stop-color", value),
    );
  }
  _syncMotion() {
    const moving =
      this.isConnected &&
      this._visible &&
      !document.hidden &&
      !preference.matches &&
      !this._small;
    this.toggleAttribute("data-paused", !moving);
    if (moving && !this._unsubscribe) this._unsubscribe = hub.add(this._frame);
    if (!moving && this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }
  _paint(time, elapsed, staticPose = false) {
    const reduced = preference.matches || this._small || staticPose;
    const mood = this.getAttribute("mood") || "idle";
    const seconds = time / 1000 + this._phase;
    const motion = sampleBlobMotion(mood, seconds, {
      moodAge: (time - this._moodStarted) / 1000,
      reactionAge: (time - this._reactionStarted) / 1000,
      reaction: this._reaction,
      reduced,
    });
    // Blend the body from its actual last pose; face/gear retain their momentum.
    if (!reduced && this._transitionFrom) {
      const age = Math.min(1, Math.max(0, (time - this._moodStarted) / 250));
      const blend = age * age * (3 - 2 * age);
      for (const key of [
        "squash",
        "lean",
        "headDrop",
        "jump",
        "reach",
        "energy",
      ])
        motion[key] =
          this._transitionFrom[key] * (1 - blend) + motion[key] * blend;
      if (age === 1) this._transitionFrom = null;
    }
    this._lastMotion = motion;
    const pose = deformBlob(motion, seconds);
    this._body.setAttribute("d", pose.path);
    const follow = (state, target, stiffness) => {
      if (reduced) {
        state.value = target;
        state.velocity = 0;
        return target;
      }
      return springStep(
        state,
        target,
        elapsed,
        stiffness,
        stiffness === 150 ? 20 : 24,
      );
    };
    const faceX = follow(
      this._faceX,
      pose.headX + this._look.x * 3 + motion.gaze,
      190,
    );
    const faceY = follow(this._faceY, pose.headY + this._look.y * 1.6, 190);
    const gearX = follow(this._gearX, pose.headX, 150);
    const gearY = follow(this._gearY, pose.headY, 150);
    this._face.setAttribute(
      "transform",
      `translate(${faceX.toFixed(2)} ${faceY.toFixed(2)}) rotate(${pose.headAngle.toFixed(2)} 120 125)`,
    );
    this._gear.setAttribute(
      "transform",
      `translate(${gearX.toFixed(2)} ${gearY.toFixed(2)}) rotate(${pose.headAngle.toFixed(2)} 120 120) translate(120 0) scale(${pose.headphoneWidth.toFixed(3)} 1) translate(-120 0)`,
    );
    const headphones = sampleHeadphones(
      mood,
      (time - this._moodStarted) / 1000,
      {
        departing: this._departingHeadphones,
        reduced,
      },
    );
    this._headphones.setAttribute("opacity", headphones.opacity.toFixed(3));
    this._headphones.setAttribute(
      "transform",
      `translate(0 ${headphones.lift.toFixed(2)}) rotate(${headphones.angle.toFixed(2)} 120 90) translate(120 90) scale(${headphones.scale.toFixed(3)}) translate(-120 -90)`,
    );
    this._earLeft.setAttribute(
      "transform",
      `translate(${-headphones.spread} 0)`,
    );
    this._earRight.setAttribute(
      "transform",
      `translate(${headphones.spread} 0)`,
    );
    const openness = 1 - motion.blink * 0.95;
    this._leftEye.setAttribute(
      "transform",
      `translate(0 125) scale(1 ${openness.toFixed(3)}) translate(0 -125)`,
    );
    this._rightEye.setAttribute(
      "transform",
      `translate(0 125) scale(1 ${openness.toFixed(3)}) translate(0 -125)`,
    );
    const warmEyes = mood === "idle" || mood === "submitted";
    for (const pupil of this._pupils) {
      pupil.setAttribute("rx", warmEyes ? "5.8" : "4.5");
      pupil.setAttribute("ry", warmEyes ? "6.1" : "4");
    }
    const smile = mood === "submitted" || mood === "celebrating" ? 153 : 150;
    this._mouth.setAttribute(
      "d",
      mood === "sad"
        ? "M114 146Q120 139 127 146"
        : mood === "idle"
          ? "M110 139Q115 149 120 143Q125 149 130 139"
          : `M113 139Q120 ${smile} 128 139`,
    );
    this._shine.setAttribute("cx", String(91 + pose.headX * 0.65));
    this._shine.setAttribute("cy", String(101 + pose.headY));
    this._shadow.setAttribute("rx", pose.shadowWidth.toFixed(2));
    this._shadow.setAttribute(
      "opacity",
      Math.max(0.035, pose.shadowOpacity).toFixed(3),
    );
  }
}
if (!customElements.get("repeat-character"))
  customElements.define("repeat-character", RepeatCharacter);
