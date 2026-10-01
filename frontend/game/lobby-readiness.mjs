/** One readiness decision supplies both the button state and its explanation. */
export function startReadiness(state, ui, audio) {
  let reason;
  const shortage = state.players.filter((player) => player.song_count < 10);
  if (!state.me.is_host) reason = "Waiting for the host to start.";
  else if (state.players.length < 3)
    reason = "At least 3 players are needed to start.";
  else if (shortage.length)
    reason = `At least 10 songs per player are needed. ${shortage.map((player) => player.nickname).join(", ")} ${shortage.length === 1 ? "has" : "have"} fewer.`;
  else if (!audio.unlocked || !audio.leaseId)
    reason = "Enable shared audio before starting.";
  else if (ui.disconnected) reason = "Reconnecting to your room…";
  else if (ui.pending)
    reason = ui.pending === "start" ? "Starting…" : "Saving your changes…";
  return {
    canStart: !reason,
    reason: reason || "Everyone is here. Let’s play!",
  };
}
