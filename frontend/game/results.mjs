// Presentation uses frozen server classifications/points, never client scoring.
export function gamePlayers(state) {
  const standings = state.game?.leaderboard ?? [];
  if (!standings.length) return state.players ?? [];
  const frozen = new Map(
    standings.map((player) => [
      player.player_id,
      {
        id: player.player_id,
        nickname: player.nickname,
        character_id: player.character_id,
      },
    ]),
  );
  const ordered = (state.players ?? [])
    .filter((player) => frozen.has(player.id))
    .map((player) => frozen.get(player.id));
  const present = new Set(ordered.map((player) => player.id));
  return [
    ...ordered,
    ...[...frozen.values()].filter((player) => !present.has(player.id)),
  ];
}

export function roundResult(state) {
  const reveal = state.game?.round?.reveal;
  if (!reveal) return null;
  const answer = reveal.my_answer;
  const submitted = answer?.status === "submitted";
  const listeners = new Set(reveal.listener_ids);
  const selected = new Set(submitted ? answer.who_player_ids : []);
  const players = gamePlayers(state).map((player) => {
    const chosen = selected.has(player.id);
    const actual = listeners.has(player.id);
    const correct = submitted ? chosen === actual : null;
    return {
      ...player,
      selected: chosen,
      actual,
      correct,
      selection: submitted
        ? chosen
          ? "Selected"
          : "Not selected"
        : "No answer",
      verdict: !submitted ? "No answer" : correct ? "Correct" : "Wrong",
      tone: !submitted ? "neutral" : correct ? "correct" : "wrong",
      mood: !submitted ? "idle" : correct ? "celebrating" : "sad",
    };
  });
  const match =
    submitted && answer.song_guess ? answer.song_match : "unanswered";
  const verdict = (correct) => ({
    label:
      match === "unanswered"
        ? submitted
          ? "No guess"
          : "No answer"
        : correct
          ? "Correct"
          : "Wrong",
    tone: match === "unanswered" ? "neutral" : correct ? "correct" : "wrong",
  });
  const listenerCorrect = players.filter(
    (player) => player.correct === true,
  ).length;
  return {
    song: reveal.song,
    players,
    points: submitted ? (answer.points ?? 0) : 0,
    songVerdict: verdict(match === "correct"),
    artistVerdict: verdict(["correct", "artist"].includes(match)),
    listenerCorrect,
    listenerTotal: players.length,
    listenerVerdict: submitted
      ? {
          label: `${listenerCorrect} / ${players.length} correct`,
          tone: players.every((player) => player.correct)
            ? "correct"
            : "neutral",
        }
      : { label: "No answer", tone: "neutral" },
    guessLabel: !submitted
      ? "No answer submitted"
      : answer.song_guess
        ? `Your guess: ${answer.song_guess.title} · ${answer.song_guess.artist}`
        : "No song guess",
  };
}

export function standingsModel(standings = []) {
  const ordered = [...standings].sort((a, b) => a.rank - b.rank);
  return { podium: ordered.slice(0, 3), remaining: ordered.slice(3) };
}

export function phaseProgress(game, now) {
  if (
    ["completed", "aborted"].includes(game.status) ||
    !Number.isFinite(game.phase_ends_at_ms)
  )
    return null;
  // Both server result phases last five seconds. Catch up after late polling;
  // never reset the bar on each state update.
  const deadline = game.phase_ends_at_ms;
  const duration = 5000;
  const remaining = Math.max(0, Math.min(duration, deadline - now));
  return {
    seconds: Math.ceil(remaining / 1000),
    fraction: remaining / duration,
    label: game.phase === "reveal" ? "Leaderboard" : "Next round",
  };
}
