// Accessible combobox with cancellable search and selection requests.
const style = `
:host{display:block;position:relative;font-family:inherit;color:#151515}
*{box-sizing:border-box} .field{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #eeecec;border-radius:999px;padding:10px 12px 10px 22px;box-shadow:0 9px 35px #2f172004}
svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;color:#a9a6ae;flex:none}
input{width:100%;border:0;outline:0;background:transparent;font-family:inherit;font-size:19px;font-weight:700;line-height:1.4;color:inherit;min-width:0}input::placeholder{font-weight:600;color:#96949f}input:disabled{color:#706c7e}
.field:focus-within{outline:2px solid #9e4e45;border-color:#9e4e45}.locked{background:#f8f7f8}
.sr{position:absolute;width:1px;height:1px;padding:0;clip:rect(0,0,0,0);overflow:hidden;white-space:nowrap}
.panel{position:absolute;z-index:20;left:0;right:0;top:calc(100% + 9px);border:1px solid #eeecec;background:#fff;border-radius:23px;padding:9px;box-shadow:0 15px 55px #20202016;max-height:280px;overflow:auto;text-align:left}
[hidden]{display:none!important}.status{padding:14px 17px;font-size:14px;color:#777383}.result{display:flex;align-items:center;gap:13px;width:100%;padding:10px;border:0;border-radius:14px;background:transparent;text-align:left;color:inherit;font:inherit;cursor:pointer}.result:hover,.result.active{background:#fff0ee}.result:focus-visible{outline:2px solid #171717}.cover{width:42px;height:42px;flex:none;border-radius:9px;background:#f3edf7;display:grid;place-items:center;overflow:hidden}.cover>*{grid-area:1/1}.cover img{width:100%;height:100%;object-fit:cover}.clear{width:44px;height:44px;border:0;background:transparent;color:#777383;padding:0;display:grid;place-items:center;cursor:pointer;flex:none}.clear:focus-visible{outline:2px solid #151515;border-radius:5px}.copy{display:flex;flex-direction:column;min-width:0}.title{font-weight:800;font-size:16px;overflow-wrap:anywhere}.artist{color:#777383;font-size:13px}.search-button{border:0;border-radius:999px;padding:12px 18px;background:#ffe4e0;color:#38221e;font-size:15px;font-weight:800;font-family:inherit;min-height:44px;cursor:pointer;touch-action:manipulation;flex:none}.search-button:hover{background:#ffd5cf}.search-button:disabled{cursor:default;opacity:.65}.search-button:focus-visible,.retry:focus-visible{outline:2px solid #151515;outline-offset:3px}.retry{border:0;background:#fff0ee;border-radius:12px;padding:9px 14px;font-family:inherit;font-size:14px;font-weight:700;cursor:pointer}.hint{font-size:12px;line-height:1.4;color:#777383;margin:8px 25px 0;min-height:17px}
@media(max-width:600px){.field{padding:8px 9px 8px 14px;gap:4px}.field>svg{display:none}.search-button{padding:12px 14px}.hint{margin-inline:14px}input{font-size:16px}.panel{max-height:220px}}
`;
// Alternatives are a bounded, already-resolved response from this room's API.
// Reject the entire malformed list instead of hiding potentially relevant choices.
function resolvedAlternatives(error) {
  const songs = error.details?.alternatives;
  const text = (value, limit) => typeof value === "string" &&
    value.trim().length > 0 && value.length <= limit;
  if (error.status !== 409 || !Array.isArray(songs) ||
      !songs.length || songs.length > 20 || !songs.every((song) =>
        song && text(song.title, 500) && text(song.artist, 500) &&
        text(song.token, 4096) && !song.resolve_required &&
        (song.artwork_url == null || typeof song.artwork_url === "string")))
    return null;
  return songs;
}
let counter = 0;
export class SongSearch extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._selection = null;
    this._search = null;
    this._resolve = null;
    this._checking = false;
    this._retrySelection = null;
    this._generation = 0;
    this._results = [];
    this._active = -1;
    this._disabled = false;
    this._loading = false;
    this._resolvedQuery = null;
    const id = `song-search-${++counter}`;
    this.shadowRoot.innerHTML = `<style>${style}</style><label class="sr" for="${id}">Song name</label><div class="field"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg><input id="${id}" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${id}-list" aria-describedby="${id}-hint" enterkeyhint="search" placeholder="Guess the song name…" autocomplete="off" spellcheck="false" maxlength="100"><button class="clear" type="button" aria-label="Clear song guess" hidden><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg></button><button class="search-button" type="button">Search</button><svg class="lock" viewBox="0 0 24 24" aria-hidden="true" hidden><rect x="5" y="10" width="14" height="10" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg></div><div class="panel" hidden><div class="status" role="status"></div><div id="${id}-list" role="listbox" aria-label="Song suggestions"></div><button class="retry" type="button" hidden>Try again</button></div><div id="${id}-hint" class="hint" aria-live="polite">Type a title, then search.</div>`;
    this.input = this.shadowRoot.querySelector("input");
    this.panel = this.shadowRoot.querySelector(".panel");
    this.status = this.shadowRoot.querySelector(".status");
    this.list = this.shadowRoot.querySelector("[role=listbox]");
    this.hint = this.shadowRoot.querySelector(".hint");
    this.clearButton = this.shadowRoot.querySelector(".clear");
    this.searchButton = this.shadowRoot.querySelector(".search-button");
    this.retryButton = this.shadowRoot.querySelector(".retry");
    this.searchButton.addEventListener("click", () => {
      this.input.focus();
      void this.load();
    });
    this.retryButton.addEventListener("click", () => {
      this.input.focus();
      if (this._retrySelection !== null) void this.choose(this._retrySelection);
      else void this.load();
    });
    this.clearButton.addEventListener("click", () => {
      this.input.value = "";
      this.onInput();
      this.input.focus();
    });
    this.input.addEventListener("input", () => this.onInput());
    this.input.addEventListener("focus", () => {
      if (!this._selection && this._resolvedQuery === this.input.value.trim())
        this.open();
    });
    this.input.addEventListener("keydown", (event) => this.onKey(event));
    this.shadowRoot.addEventListener("focusout", () => {
      queueMicrotask(() => {
        if (!this.shadowRoot.activeElement) this.close();
      });
    });
  }
  get hasUnselectedQuery() {
    return Boolean(this.input.value.trim() && !this._selection);
  }
  reportSelectionRequired() {
    this.input.setCustomValidity(
      "Select a song from the search results, or clear the field.",
    );
    this.hint.textContent = this.input.validationMessage;
    this.input.reportValidity();
    this.input.focus();
  }
  set submitted(value) {
    if (value && !this._selection) {
      this.input.value = "";
      this.hint.textContent = "";
    }
    this.input.placeholder = value ? "No song guessed" : "Guess the song name…";
    this.updateClear();
  }
  updateClear() {
    this.clearButton.hidden = this._disabled || !this.input.value;
    this.searchButton.disabled = this._disabled || this._loading;
    this.searchButton.hidden = this._disabled || Boolean(this._selection);
    this.searchButton.setAttribute("aria-busy", String(this._loading));
  }
  set search(value) {
    this._search = value;
  }
  set resolve(value) {
    this._resolve = value;
  }
  get selection() {
    return this._selection;
  }
  set selection(value) {
    if (
      value === this._selection ||
      (value &&
        this._selection &&
        value.token === this._selection.token &&
        value.title === this._selection.title)
    )
      return;
    this._selection = value;
    if (value) {
      this.input.value = value.title;
      this.hint.textContent = value.artist || "";
      this.input.setCustomValidity("");
      this.close();
      this.updateClear();
    }
    // Null snapshots must not erase an in-progress query.
  }
  set disabled(value) {
    const next = Boolean(value);
    if (next === this._disabled) return;
    this._disabled = next;
    this.input.disabled = next;
    this.shadowRoot.querySelector(".field").classList.toggle("locked", next);
    this.shadowRoot.querySelector(".lock").hidden = !next;
    if (next) this.close();
    this.updateClear();
  }
  get disabled() {
    return this._disabled;
  }
  disconnectedCallback() {
    this.cancel();
  }
  cancel() {
    if (this._checking) {
      this.status.hidden = this._results.length > 0;
      this.retryButton.hidden = true;
      this._retrySelection = null;
    }
    this._controller?.abort();
    this._generation++;
    this._loading = false;
    this._checking = false;
    this.panel.setAttribute("aria-busy", "false");
    this.updateClear();
  }
  close() {
    this.cancel();
    this.panel.hidden = true;
    this.input.setAttribute("aria-expanded", "false");
    this.input.removeAttribute("aria-activedescendant");
  }
  open() {
    this.panel.hidden = false;
    this.input.setAttribute("aria-expanded", "true");
  }
  onInput() {
    this.cancel();
    this.input.setCustomValidity("");
    this.updateClear();
    if (this._selection) {
      this._selection = null;
      this.dispatchEvent(
        new CustomEvent("song-select", {
          bubbles: true,
          composed: true,
          detail: { song: null },
        }),
      );
    }
    this.hint.textContent = "Type a title, then search.";
    this._resolvedQuery = null;
    this._retrySelection = null;
    this._active = -1;
    this._results = [];
    this.list.replaceChildren();
    this.close();
  }
  showStatus(message) {
    this.status.textContent = message;
    this.status.hidden = false;
    this.open();
  }
  async load() {
    const query = this.input.value.trim();
    if (this._disabled || !this._search || this._selection) return;
    if (query.length < 2) {
      this.hint.textContent = "Enter at least two letters to search.";
      return;
    }
    if (this._loading) return;
    if (query === this._resolvedQuery) {
      this.open();
      return;
    }
    this._controller?.abort();
    const generation = ++this._generation;
    const controller = new AbortController();
    this._controller = controller;
    this._loading = true;
    this.retryButton.hidden = true;
    this._retrySelection = null;
    this.panel.setAttribute("aria-busy", "true");
    this.updateClear();
    this.input.removeAttribute("aria-activedescendant");
    this.showStatus("Searching…");
    this.list.replaceChildren();
    this._results = [];
    this._active = -1;
    try {
      const response = await this._search(query, { signal: controller.signal });
      if (generation !== this._generation || this._disabled) return;
      this._resolvedQuery = query;
      this._results = response.songs || [];
      this.hint.textContent = this._results.length
        ? "Choose a result. Use ↑ or ↓, then Enter."
        : "Try another title or add the artist.";
      this.status.hidden = this._results.length > 0;
      if (!this._results.length)
        this.showStatus("No songs found. Try a title and artist.");
      this.list.replaceChildren(
        ...this._results.map((song, index) => this.result(song, index)),
      );
    } catch (error) {
      if (generation !== this._generation || controller.signal.aborted) return;
      this.showStatus(
        error.status === 429
          ? "Search is busy. Give it a moment and try again."
          : "Couldn’t search right now. Check your connection and try again.",
      );
      this.retryButton.hidden = false;
    } finally {
      if (generation === this._generation) {
        this._loading = false;
        this.panel.setAttribute("aria-busy", "false");
        this.updateClear();
      }
    }
  }

  result(song, index) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result";
    button.id = `${this.input.id}-option-${index}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", "false");
    const cover = document.createElement("span");
    cover.className = "cover";
    cover.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 17V5l11-2v12M9 5l11-2"/><ellipse cx="5" cy="17" rx="4" ry="3"/><ellipse cx="16" cy="15" rx="4" ry="3"/></svg>';
    if (song.artwork_url) {
      const image = document.createElement("img");
      image.src = song.artwork_url;
      image.alt = "";
      image.loading = "lazy";
      image.addEventListener("error", () => image.remove(), { once: true });
      cover.append(image);
    }
    const copy = document.createElement("span");
    copy.className = "copy";
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = song.title;
    const artist = document.createElement("span");
    artist.className = "artist";
    artist.textContent = song.artist;
    copy.append(title, artist);
    button.append(cover, copy);
    button.addEventListener("click", () => this.choose(index));
    button.addEventListener("pointerdown", (event) => event.preventDefault());
    return button;
  }
  async choose(index) {
    if (this._disabled || this.panel.hidden || this._checking) return;
    let song = this._results[index];
    if (!song) return;
    if (song.resolve_required) {
      const generation = ++this._generation;
      const controller = new AbortController();
      this._controller?.abort();
      this._controller = controller;
      this._loading = this._checking = true;
      this.retryButton.hidden = true;
      this.panel.setAttribute("aria-busy", "true");
      this.updateClear();
      this.showStatus("Checking song…");
      try {
        if (!this._resolve) throw new Error("Song selection unavailable");
        song = await this._resolve(song, { signal: controller.signal });
        if (generation !== this._generation || this._disabled) return;
        if (!song?.token || song.resolve_required) throw new Error("Unresolved song");
      } catch (error) {
        if (generation !== this._generation || this._disabled || controller.signal.aborted) return;
        const alternatives = resolvedAlternatives(error);
        if (alternatives) {
          this._results = alternatives;
          this._active = -1;
          this.input.removeAttribute("aria-activedescendant");
          this._retrySelection = null;
          this.retryButton.hidden = true;
          this.list.replaceChildren(
            ...alternatives.map((alternative, position) => this.result(alternative, position)),
          );
          this.showStatus("Choose the song you mean.");
          return;
        }
        this._retrySelection = index;
        this.showStatus("Couldn’t check this song. Try again or choose another result.");
        this.retryButton.hidden = false;
        return;
      } finally {
        if (generation === this._generation) {
          this._loading = this._checking = false;
          this.panel.setAttribute("aria-busy", "false");
          this.updateClear();
        }
      }
    }
    this.selection = song;
    this.dispatchEvent(
      new CustomEvent("song-select", {
        bubbles: true,
        composed: true,
        detail: { song },
      }),
    );
  }
  onKey(event) {
    if (event.isComposing) return;
    if (event.key === "Escape") {
      this.close();
      return;
    }
    if (event.key === "Enter" && !this.panel.hidden && this._active >= 0) {
      event.preventDefault();
      this.choose(this._active);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      void this.load();
      return;
    }
    if (
      !["ArrowDown", "ArrowUp"].includes(event.key) ||
      !this._results.length ||
      this.panel.hidden
    )
      return;
    event.preventDefault();
    if (this._active === -1 && event.key === "ArrowUp") this._active = 0;
    this._active =
      (this._active +
        (event.key === "ArrowDown" ? 1 : -1) +
        this._results.length) %
      this._results.length;
    for (const [index, node] of [...this.list.children].entries()) {
      node.classList.toggle("active", index === this._active);
      node.setAttribute("aria-selected", String(index === this._active));
    }
    const current = this.list.children[this._active];
    if (!current) return;
    this.input.setAttribute("aria-activedescendant", current.id);
    current.scrollIntoView({ block: "nearest" });
  }
}
customElements.define("song-search", SongSearch);
