/** Screen identity and mounting. Factories own markup; the host owns lifecycle. */
export function screenKey({ ui, state }) {
  if (ui.page !== "play") return `info:${ui.page}`;
  if (ui.historyOpen) return "history";
  if (!state) return ui.roomId ? "restoring" : "entry";
  const game = state.game;
  if (game && ui.dismissedGame !== game.id) {
    if (
      ["completed", "aborted"].includes(game.status) ||
      ["reveal", "leaderboard"].includes(game.phase)
    )
      return `results:${game.id}`;
    return `round:${game.id}:${game.round?.id || "setup"}`;
  }
  return `lobby:${state.room.id}`;
}

export function createScreenHost(root, factories) {
  let current, key;
  return {
    update(model) {
      const nextKey = screenKey(model);
      if (nextKey !== key) {
        const next = factories[nextKey.split(":")[0]](model);
        current?.destroy?.();
        current = next;
        key = nextKey;
        root.replaceChildren(current.element);
      }
      current.update(model);
    },
    get animated() {
      return Boolean(current?.tick);
    },
    tick(now) {
      current?.tick?.(now);
    },
    destroy() {
      current?.destroy?.();
      current = null;
      key = null;
      root.replaceChildren();
    },
  };
}
