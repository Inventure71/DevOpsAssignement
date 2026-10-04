import { requestId } from "../transport/client.mjs";

// Results polling renews preparation acknowledgements; current-round check-in
// remains the fallback.
export function createUpcomingReadiness(
  transport,
  getState,
  hostReadiness,
  notice,
  {
    now = transport.now ?? Date.now,
    browserId = requestId(),
    renewAfterMs = 2000,
    isVisible = () => !globalThis.document?.hidden,
  } = {},
) {
  let active = null;

  function target() {
    const state = getState();
    const preparation = state?.game?.upcoming_round;
    if (
      !isVisible() ||
      !["reveal", "leaderboard"].includes(state?.game?.phase) ||
      ["completed", "aborted"].includes(state?.game?.status) ||
      !state?.room?.id || !state?.me?.id || !state?.game?.id ||
      !preparation?.id
    ) return null;
    const host = Boolean(state.me.is_host);
    const playback = host
      ? hostReadiness(preparation)
      : { ready: true, leaseId: null };
    if (!playback.ready || (host && !playback.leaseId)) return null;
    return {
      key: JSON.stringify([
        state.room.id, state.me.id, state.game.id, preparation.id,
        preparation.readiness_generation, host, playback.leaseId,
        host ? preparation.audio_candidate_id : null,
      ]),
      gameId: state.game.id,
      preparationId: preparation.id,
      generation: preparation.readiness_generation,
      leaseId: host ? playback.leaseId : null,
    };
  }

  function reset() {
    active?.controller.abort();
    active = null;
  }

  async function synchronize() {
    const next = target();
    if (!next) {
      reset();
      return;
    }
    if (active?.key !== next.key) {
      reset();
      active = {
        ...next,
        controller: new AbortController(),
        inflight: false,
        nextAt: -Infinity,
        warned: false,
      };
    }
    const operation = active;
    const sentAt = now();
    if (operation.inflight || sentAt < operation.nextAt) return;
    operation.inflight = true;
    const current = () => active === operation &&
      !operation.controller.signal.aborted && target()?.key === operation.key;
    try {
      await transport.api(transport.path(
        `/games/${operation.gameId}/preparations/${operation.preparationId}/ready`,
      ), {
        method: "POST",
        signal: operation.controller.signal,
        body: {
          readiness_generation: operation.generation,
          browser_id: browserId,
          lease_id: operation.leaseId,
        },
      });
      // A slow response must not extend an acknowledgement's real lifetime.
      if (current()) operation.nextAt = sentAt + renewAfterMs;
    } catch (error) {
      if (!current()) return;
      if (![409, 410].includes(error.status) && !operation.warned) {
        operation.warned = true;
        notice(error.message);
      }
      // Polling supplies the retry cadence; failed requests never mark readiness.
    } finally {
      operation.inflight = false;
    }
  }

  return { synchronize, reset };
}
