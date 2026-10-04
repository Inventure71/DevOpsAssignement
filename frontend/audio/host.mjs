import { requestId } from "../transport/client.mjs";
import { waveformLevels } from "./levels.mjs";

// One controller owns the lease, decoded buffers, preload workers and sources.
// The rest of the UI sees only a status snapshot and narrow operations.
export function createAudioController(
  transport,
  getState,
  now,
  tabId,
  render,
  showNotice,
  environment = globalThis,
) {
  const { api, path, roundPath } = transport;
  const { fetch, AbortController, setTimeout, clearTimeout } = environment;
  const window = environment;
  const playback = {
    unlocked: false,
    leaseId: null,
    context: null,
    clips: new Map(),
    preloadingGame: null,
    preloadComplete: false,
    preloadRetryAt: 0,
    interruptedRounds: new Set(),
    playedRounds: new Set(),
    failedRounds: new Set(),
    current: null,
    conflict: false,
  };
  const decodedByUrl = new Map();
  let cachedGame = null;
  let leasedSession = null;
  let generation = 0;
  let sessionController = new AbortController();

  function audioRunning() {
    return playback.unlocked && playback.context?.state === "running";
  }

  function audioStateChanged(event) {
    if (event.target === playback.context && getState()?.me?.is_host) render();
  }

  function session() {
    const state = getState();
    return {
      generation,
      roomId: state?.room?.id,
      playerId: state?.me?.id,
      signal: sessionController.signal,
    };
  }

  function current(operation) {
    const state = getState();
    return (
      operation &&
      operation.generation === generation &&
      state?.me?.is_host &&
      state.room?.id === operation.roomId &&
      state.me.id === operation.playerId
    );
  }

  function invalidateWork() {
    generation++;
    sessionController.abort();
    sessionController = new AbortController();
    stopAudio();
    playback.leaseId = null;
    leasedSession = null;
    playback.preloadingGame = null;
    playback.preloadComplete = false;
    playback.clips.clear();
    decodedByUrl.clear();
    cachedGame = null;
    playback.preloadRetryAt = 0;
  }

  async function enable(takeover = false) {
    // A new lease attempt replaces pending work, retaining the gesture unlock.
    suspend();
    invalidateWork();
    const operation = session();
    if (!current(operation)) return;
    const leasePath = path("/audio-controller");
    try {
      // This runs directly from a user gesture before the first network await.
      const Context = window.AudioContext || window.webkitAudioContext;
      if (!Context)
        throw new Error(
          "This browser does not support host speaker playback. Try a current browser.",
        );
      if (!playback.context || playback.context.state === "closed") {
        playback.context?.removeEventListener("statechange", audioStateChanged);
        playback.context = new Context();
        playback.context.addEventListener("statechange", audioStateChanged);
      }
      await playback.context.resume();
      if (!current(operation)) return;
      if (playback.context.state !== "running")
        throw new Error("Host speaker couldn’t start. Try again to continue.");
      const silent = playback.context.createBufferSource();
      silent.buffer = playback.context.createBuffer(
        1,
        1,
        playback.context.sampleRate,
      );
      silent.connect(playback.context.destination);
      silent.start();
      playback.unlocked = playback.context.state === "running";
      const lease = await api(leasePath, {
        method: "POST",
        body: { tab_id: tabId, takeover },
        signal: operation.signal,
      });
      if (!current(operation)) return;
      playback.leaseId = lease.lease_id;
      leasedSession = operation;
      playback.conflict = false;
      render();
    } catch (error) {
      if (!current(operation)) return;
      if (error.status === 409) playback.conflict = true;
      render();
      throw error;
    }
  }

  async function preloadClip(candidate, operation) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    operation.signal.addEventListener("abort", cancel, { once: true });
    const timeout = setTimeout(cancel, 10000);
    try {
      if (!decodedByUrl.has(candidate.preview_url)) {
        const decode = async () => {
          const response = await fetch(candidate.preview_url, {
            credentials: "same-origin",
            cache: "force-cache",
            signal: controller.signal,
          });
          if (!response.ok) throw new Error("Clip unavailable");
          const bytes = await response.arrayBuffer();
          if (!currentPreload(operation)) throw new Error("Preparation cancelled");
          return playback.context.decodeAudioData(bytes);
        };
        const pending = decode().catch((error) => {
          if (decodedByUrl.get(candidate.preview_url) === pending)
            decodedByUrl.delete(candidate.preview_url);
          throw error;
        });
        decodedByUrl.set(candidate.preview_url, pending);
      }
      const buffer = await decodedByUrl.get(candidate.preview_url);
      if (!buffer.duration || buffer.duration < 1)
        throw new Error("Clip is too short");
      if (currentPreload(operation))
        playback.clips.set(candidate.candidate_id, buffer);
    } finally {
      clearTimeout(timeout);
      operation.signal.removeEventListener("abort", cancel);
    }
  }

  function currentPreload(operation) {
    return (
      current(operation) &&
      getState()?.game?.id === operation.gameId &&
      !["completed", "aborted"].includes(getState()?.game?.status) &&
      playback.preloadingGame === operation.gameId &&
      playback.leaseId === operation.leaseId
    );
  }

  async function preload(gameId, reportChecks) {
    const operation = { ...session(), gameId, leaseId: playback.leaseId };
    const answerSeconds = getState()?.settings?.answer_seconds;
    if (cachedGame !== gameId) {
      decodedByUrl.clear();
      cachedGame = gameId;
    }
    playback.preloadingGame = gameId;
    playback.preloadComplete = false;
    playback.clips.clear();
    try {
      const manifest = await api(path(`/games/${gameId}/audio`), {
        headers: { "X-Audio-Lease": operation.leaseId },
        signal: operation.signal,
      });
      if (!currentPreload(operation)) return;
      const candidates = manifest.candidates || [];
      let position = 0;
      // Limit parallel fetch/decode work so phones stay responsive during setup.
      const worker = async () => {
        while (currentPreload(operation) && position < candidates.length) {
          const candidate = candidates[position++];
          let ok = false;
          try {
            await preloadClip(candidate, operation);
            ok = true;
          } catch (_) {
            /* Report failure and let the server substitute. */
          }
          if (!currentPreload(operation)) return;
          if (reportChecks)
            await api(path(`/games/${gameId}/preload-check`), {
              method: "POST",
              signal: operation.signal,
              body: {
                request_id: requestId(),
                lease_id: operation.leaseId,
                candidate_id: candidate.candidate_id,
                ok,
                ...(ok
                  ? {
                      waveform: waveformLevels(
                        playback.clips.get(candidate.candidate_id),
                        48,
                        answerSeconds,
                      ),
                    }
                  : {}),
              },
            });
        }
      };
      const outcomes = await Promise.allSettled(
        Array.from({ length: Math.min(4, candidates.length) }, worker),
      );
      const failed = outcomes.find((outcome) => outcome.status === "rejected");
      if (failed) throw failed.reason;
      if (currentPreload(operation)) playback.preloadComplete = true;
    } catch (error) {
      if (currentPreload(operation)) {
        playback.preloadingGame = null;
        playback.preloadRetryAt = now() + 2000;
        showNotice(
          "The music couldn’t load. We’ll try again automatically. Keep this screen open.",
        );
      }
    }
  }

  function currentRound(operation) {
    const game = getState()?.game;
    return (
      current(operation) &&
      playback.leaseId === operation.leaseId &&
      game?.id === operation.gameId &&
      game.round?.id === operation.roundId &&
      game.round.readiness_generation === operation.readinessGeneration &&
      ["ready", "countdown", "answering"].includes(game.phase)
    );
  }

  async function reportAudioFailure(operation, reason) {
    if (
      !currentRound(operation) ||
      playback.failedRounds.has(operation.roundId) ||
      !operation.leaseId
    ) return;
    playback.failedRounds.add(operation.roundId);
    playback.interruptedRounds.add(operation.roundId);
    stopAudio();
    try {
      await api(operation.failurePath, {
        method: "POST",
        signal: operation.signal,
        body: {
          request_id: requestId(),
          readiness_generation: operation.readinessGeneration,
          lease_id: operation.leaseId,
          reason,
        },
      });
    } catch (error) {
      if (!currentRound(operation)) return;
      if (![409, 410].includes(error.status))
        playback.failedRounds.delete(operation.roundId);
      showNotice(error.message);
    }
  }

  function suspend() {
    const round = getState()?.game?.round;
    if (playback.current && round) playback.interruptedRounds.add(round.id);
    stopAudio();
  }

  function stopAudio() {
    if (playback.current) {
      try {
        playback.current.stop();
      } catch (_) {
        /* Source may already have ended. */
      }
      playback.current = null;
    }
  }

  async function synchronizePlayback() {
    if (playback.leaseId && !current(leasedSession)) {
      invalidateWork();
      return;
    }
    const game = getState()?.game;
    if (!game || ["completed", "aborted"].includes(game.status)) {
      stopAudio();
      return;
    }
    if (
      getState().me.is_host &&
      playback.leaseId &&
      playback.unlocked &&
      playback.preloadingGame !== game.id &&
      now() >= playback.preloadRetryAt
    ) {
      // Preparation is deliberately not awaited by the polling loop.
      // A recovered host tab reloads the frozen manifest without changing checks.
      void preload(game.id, game.phase === "setup");
    }
    if (["reveal", "leaderboard", "finished"].includes(game.phase)) {
      stopAudio();
      return;
    }
    const round = game.round;
    if (!round) return;
    const host = getState().me.is_host;
    const operation = {
      ...session(),
      gameId: game.id,
      roundId: round.id,
      readinessGeneration: round.readiness_generation,
      leaseId: playback.leaseId,
      failurePath: roundPath("/audio-failure"),
    };
    if (
      host &&
      playback.interruptedRounds.has(round.id) &&
      ["ready", "countdown", "answering"].includes(game.phase)
    ) {
      await reportAudioFailure(
        operation,
        "Host left the page; playback was interrupted",
      );
      return;
    }
    const buffer = host ? playback.clips.get(round.audio_candidate_id) : null;

    if (
      host &&
      ["countdown", "answering"].includes(game.phase) &&
      !playback.playedRounds.has(round.id) &&
      playback.leaseId &&
      playback.unlocked
    ) {
      playback.playedRounds.add(round.id);
      stopAudio();
      if (!buffer) {
        await reportAudioFailure(operation, "Clip not present in host cache");
        return;
      }
      // A reloaded/new tab must never restart an already-playing song.
      if (now() > round.starts_at_ms + 1000) {
        await reportAudioFailure(
          operation,
          "Host tab missed the start; playback was interrupted",
        );
        return;
      }
      const source = playback.context.createBufferSource();
      source.buffer = buffer;
      source.connect(playback.context.destination);
      playback.current = source;
      try {
        if (playback.context.state !== "running")
          throw new Error("Host audio is suspended");
        const delay = Math.max(0, (round.starts_at_ms - now()) / 1000);
        source.start(playback.context.currentTime + delay);
        source.stop(
          playback.context.currentTime +
            delay +
            Math.min(buffer.duration, getState().settings.answer_seconds),
        );
      } catch (error) {
        await reportAudioFailure(operation, error.message);
        return;
      }
    }
    if (
      host &&
      game.phase === "answering" &&
      playback.context &&
      playback.context.state !== "running"
    )
      await reportAudioFailure(operation, "Host audio was interrupted");
  }

  function reset() {
    invalidateWork();
    playback.interruptedRounds.clear();
    playback.playedRounds.clear();
    playback.failedRounds.clear();
    playback.conflict = false;
  }

  async function renewLease() {
    if (!getState()?.me.is_host || !playback.leaseId) return;
    if (!current(leasedSession)) {
      invalidateWork();
      return;
    }
    const operation = session();
    const leaseId = playback.leaseId;
    try {
      const lease = await api(path("/audio-controller"), {
        method: "POST",
        body: { tab_id: tabId, takeover: false },
        signal: operation.signal,
      });
      if (!current(operation) || playback.leaseId !== leaseId) return;
      playback.leaseId = lease.lease_id;
    } catch (error) {
      if (!current(operation) || playback.leaseId !== leaseId) return;
      if ([403, 409].includes(error.status)) {
        suspend();
        invalidateWork();
        playback.conflict = true;
        render();
      }
      throw error;
    }
  }

  return {
    get status() {
      return {
        unlocked: audioRunning(),
        leaseId: playback.leaseId,
        conflict: playback.conflict,
      };
    },
    readiness(round) {
      return {
        leaseId: playback.leaseId,
        ready: Boolean(
          leasedSession &&
          current(leasedSession) &&
          getState()?.game?.id === playback.preloadingGame &&
          playback.leaseId &&
          audioRunning() &&
          playback.preloadComplete &&
          !playback.interruptedRounds.has(round.id) &&
          playback.clips.has(round.audio_candidate_id),
        ),
      };
    },
    enable,
    renewLease,
    synchronize: synchronizePlayback,
    stop: stopAudio,
    suspend,
    reset,
  };
}
