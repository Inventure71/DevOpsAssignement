import "./character.mjs";
import { text } from "../dom.mjs";

/** Binds the static header without coupling navigation to game transport. */
export function createSiteHeader(document, { navigate, emit }) {
  const find = (selector) => document.querySelector(selector);
  const profile = find("#profile");
  const name = find("#profile-name");
  const sprite = find("#profile-character");
  const toggle = find("#profile-toggle");
  const menu = find("#profile-actions");
  const endGame = find("#end-game-button");
  const links = [...document.querySelectorAll("[data-page]")];
  const listeners = new AbortController();
  const options = { signal: listeners.signal };
  function closeMenu() {
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }
  find(".site-nav").addEventListener(
    "click",
    (event) => {
      const link = event.target.closest("[data-page]");
      if (!link) return;
      event.preventDefault();
      navigate(link.dataset.page);
    },
    options,
  );
  toggle.addEventListener(
    "click",
    () => {
      menu.hidden = !menu.hidden;
      toggle.setAttribute("aria-expanded", String(!menu.hidden));
    },
    options,
  );
  menu.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      closeMenu();
      emit(button.dataset.action);
    },
    options,
  );
  document.addEventListener(
    "click",
    (event) => {
      if (!event.target.closest("#profile")) closeMenu();
    },
    options,
  );
  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Escape" && !menu.hidden) {
        closeMenu();
        toggle.focus();
      }
    },
    options,
  );
  return {
    update(state, page) {
      profile.hidden = !state;
      if (state) {
        text(name, state.me.nickname);
        if (sprite.getAttribute("color") !== state.me.character_id)
          sprite.setAttribute("color", state.me.character_id);
        endGame.hidden =
          !state.me.is_host ||
          !["preparing", "playing"].includes(state.game?.status);
      } else closeMenu();
      for (const link of links) {
        if (link.dataset.page === page)
          link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      }
    },
    destroy() {
      listeners.abort();
    },
  };
}
