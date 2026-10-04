/** Lobby eligibility; the Start game gesture activates audio before starting. */
export function startReadiness(state, ui) {
  const blocked = (blocker, reason) => ({ canStart: false, blocker, reason });
  if (!state?.me?.is_host) return blocked("host", "Waiting for the host to start.");
  const shortage = state.players.filter((player) => player.song_count < 10);
  const minimum = state.room?.minimum_players ?? 3;
  if (state.players.length < minimum)
    return blocked("players", `At least ${minimum} players are needed to start.`);
  if (shortage.length)
    return blocked(
      "songs",
      `At least 10 songs per player are needed. ${shortage.map((player) => player.nickname).join(", ")} ${shortage.length === 1 ? "has" : "have"} fewer.`,
    );
  if (ui.disconnected)
    return blocked("connection", "Reconnecting to your room…");
  if (ui.pending)
    return blocked(
      "pending",
      ui.pending === "start" ? "Starting…" : "Saving your changes…",
    );
  return {
    canStart: true,
    blocker: null,
    reason: "Everyone is here. Let’s play!",
  };
}
