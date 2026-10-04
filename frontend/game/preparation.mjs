// Product copy belongs here, separate from provider diagnostics and transport.
export function musicPreparation(progress = {}) {
  if (progress.status === "interrupted") return {
    title: "Let’s reconnect",
    message: "Check your connection, then try again. Your sign-in may still be ready.",
    busy: false,
    retry: true,
    back: false,
  };
  if (progress.status === "failed") {
    const code = progress.error?.code;
    let message = "We couldn’t get your music ready. Try signing in again.";
    if (code === "insufficient_playable_songs")
      message = "We need at least 10 songs with available previews from your listening history. Try another music account or play the demo.";
    else if (code === "insufficient_decoy_songs")
      message = "Some songs aren’t available right now. Try signing in again in a moment.";
    else if (code === "music_authorization_denied")
      message = "Spotify sign-in was cancelled. Sign in again when you’re ready.";
    else if (["invalid_music_state", "music_callback_used", "music_admission_expired", "spotify_authorization_expired"].includes(code))
      message = "Your sign-in has expired. Sign in again to continue.";
    else if (progress.error?.retryable || ["music_admission_busy", "preview_provider_busy", "preview_provider_unavailable"].includes(code))
      message = "Music isn’t available right now. Wait a moment, then sign in again.";
    else if (code === "spotify_access_denied")
      message = "Spotify hasn’t allowed this account to join yet. Ask the host to check account access, or play the demo.";
    else if (code === "nickname_taken")
      message = "That name is already in the room. Choose another name and sign in again.";
    else if (code === "room_full")
      message = "This room is full. Ask your friends to create another room.";
    else if (code === "music_account_taken")
      message = "This music account is already in the room. Use another account to join.";
    return { title: "Couldn’t get your music ready", message, busy: false, retry: false, back: true };
  }
  return {
    title: "Getting your music ready",
    message: progress.reconnecting
      ? "Reconnecting… We’ll continue as soon as you’re back online."
      : progress.status === "pending"
        ? "Finishing your music sign-in…"
        : "Finding your favorites for the game…",
    busy: true,
    retry: false,
    back: false,
  };
}

export function roundPreparation(game, players, now, isHost) {
  if (game.phase === "setup") return {
    title: "Getting ready",
    message: isHost
      ? "Keep this screen open."
      : "Your host is preparing the music.",
  };
  if (game.phase !== "ready") return null;
  const names = players
    .filter((player) => (game.missing_player_ids ?? []).includes(player.id))
    .map((player) => player.nickname);
  const timedOut = now >= game.round.readiness_deadline_at_ms;
  return {
    title: timedOut ? "Waiting for players" : "Almost ready",
    message: timedOut
      ? isHost ? "Retry or continue without them." : "Waiting for your host."
      : names.length > 2
        ? `Waiting for ${names.length} players…`
        : names.length ? `Waiting for ${names.join(" and ")}…` : "Starting soon…",
  };
}
