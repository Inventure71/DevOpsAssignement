// Replacing markup is deliberate: preserve focused entry fields and avoid
// rerendering identical polling snapshots. Timer updates never rebuild the DOM.
export function createRenderer({app, leaveButton, document}, markup, now, getState) {
  let lastMarkup = "";
  function render(force = false) {
    const html = markup();
    // Polls update clocks without replacing focused form fields or button nodes.
    // Timer values are already encoded as server timestamps, so the same state
    // produces the same markup until a meaningful update arrives.
    if (force || html !== lastMarkup) {
      const focused = document.activeElement;
      const inputName = focused?.tagName === "INPUT" ? focused.name : null;
      const selection = inputName ? [focused.selectionStart, focused.selectionEnd] : null;
      app.innerHTML = html;
      lastMarkup = html;
      if (inputName) {
        const field = app.querySelector(`input[name="${inputName}"]`);
        field?.focus();
        if (selection && field) field.setSelectionRange(...selection);
      }
      app.querySelectorAll("img[data-cover]").forEach(img => img.addEventListener("error", () => {
        if (!img.src.endsWith("cover-placeholder.svg")) img.src = "/static/images/cover-placeholder.svg";
      }, {once: true}));
    }
    app.setAttribute("aria-busy", "false");
    leaveButton.hidden = !getState();
    updateTimers();
  }

  function updateTimers() {
    app.querySelectorAll("[data-countdown]").forEach(el => {
      const end = Number(el.dataset.countdown);
      el.textContent = Number.isFinite(end) && end > 0 ? Math.max(0, Math.ceil((end - now()) / 1000)) : "…";
    });
    app.querySelectorAll("[data-progress-end]").forEach(el => {
      const start = Number(el.dataset.progressStart), end = Number(el.dataset.progressEnd);
      el.style.width = `${Math.max(0, Math.min(100, (end - now()) / (end - start) * 100))}%`;
    });
  }


  return {render, updateTimers};
}

export function createNotifier(notice) {
  let timer;
  return message => {
    clearTimeout(timer);
    notice.textContent = message;
    notice.hidden = false;
    timer = setTimeout(() => { notice.hidden = true; }, 6500);
  };
}
