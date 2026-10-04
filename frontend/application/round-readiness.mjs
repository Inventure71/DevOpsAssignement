import { createUpcomingReadiness } from "./upcoming-readiness.mjs";

// Every participant acknowledges a ready round. Only the host needs a clip.
export function createRoundReadiness(
  transport,
  getState,
  readySent,
  hostReadiness,
  notice,
) {
  let generation = 0;
  let controller = new AbortController();
  const upcoming = createUpcomingReadiness(
    transport, getState, hostReadiness, notice,
  );

  async function synchronize() {
    const state = getState();
    if (["reveal", "leaderboard"].includes(state?.game?.phase)) {
      return upcoming.synchronize();
    }
    upcoming.reset();
    const round = state?.game?.round;
    if (state?.game?.phase !== "ready" || !round) return;
    const host = state.me.is_host;
    const playback = host ? hostReadiness(round) : { ready: true, leaseId: null };
    const key = `${round.id}:${round.readiness_generation}`;
    if (!playback.ready || readySent.has(key)) return;
    const epoch = generation;
    const roomId = state.room?.id;
    const playerId = state.me.id;
    const gameId = state.game.id;
    const current = () => {
      const latest = getState();
      const latestRound = latest?.game?.round;
      return (
        epoch === generation &&
        latest?.room?.id === roomId &&
        latest?.me?.id === playerId &&
        latest?.me?.is_host === host &&
        latest?.game?.id === gameId &&
        latest?.game?.phase === "ready" &&
        `${latestRound?.id}:${latestRound?.readiness_generation}` === key &&
        (!host || hostReadiness(round).leaseId === playback.leaseId)
      );
    };
    readySent.add(key);
    try {
      await transport.api(transport.roundPath("/ready"), {
        method: "POST",
        signal: controller.signal,
        body: {
          readiness_generation: round.readiness_generation,
          lease_id: playback.leaseId,
        },
      });
    } catch (error) {
      if (!current()) return;
      readySent.delete(key);
      if (![409, 410].includes(error.status)) notice(error.message);
    }
  }

  return {
    synchronize,
    reset() {
      upcoming.reset();
      generation++;
      controller.abort();
      controller = new AbortController();
      readySent.clear();
    },
  };
}
