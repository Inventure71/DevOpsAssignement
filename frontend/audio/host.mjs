import { requestId } from "../transport/client.mjs";
import { waveformLevels } from "./levels.mjs";

// One controller owns the lease, decoded buffers, preload workers and sources.
// The rest of the UI sees only a status snapshot and narrow operations.
export function createAudioController(
  transport,
  getState,
  now,
  tabId,
  readySent,
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
  async function enable(takeover = false) {
    // This runs directly from a user gesture before the first network await.
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context)
      throw new Error(
        "This browser does not support shared audio. Try a current browser.",
      );
    playback.context ||= new Context();
    await playback.context.resume();
    const silent = playback.context.createBufferSource();
    silent.buffer = playback.context.createBuffer(
      1,
      1,
      playback.context.sampleRate,
    );
    silent.connect(playback.context.destination);
    silent.start();
    playback.unlocked = playback.context.state === "running";
    try {
      const lease = await api(path("/audio-controller"), {
        method: "POST",
        body: { tab_id: tabId, takeover },
      });
      playback.leaseId = lease.lease_id;
      playback.conflict = false;
      render();
    } catch (error) {
      if (error.status === 409) playback.conflict = true;
      render();
      throw error;
    }
  }

  async function preloadClip(candidate, gameId) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      if (!decodedByUrl.has(candidate.preview_url)) {
        const decode = async () => {
          const response = await fetch(candidate.preview_url, {
            credentials: "same-origin",
            cache: "force-cache",
            signal: controller.signal,
          });
          if (!response.ok) throw new Error("Clip unavailable");
          return playback.context.decodeAudioData(await response.arrayBuffer());
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
      if (playback.preloadingGame === gameId)
        playback.clips.set(candidate.candidate_id, buffer);
    } finally {
      clearTimeout(timeout);
    }
  }

  async function preload(gameId, reportChecks) {
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
        headers: { "X-Audio-Lease": playback.leaseId },
      });
      const candidates = manifest.candidates || [];
      let position = 0;
      // Limit parallel fetch/decode work so phones stay responsive during setup.
      const worker = async () => {
        while (
          playback.preloadingGame === gameId &&
          position < candidates.length &&
          getState()?.game?.id === gameId &&
          playback.leaseId
        ) {
          const candidate = candidates[position++];
          let ok = false;
          try {
            await preloadClip(candidate, gameId);
            ok = true;
          } catch (_) {
            /* Report failure and let the server substitute. */
          }
          if (reportChecks)
            await api(path(`/games/${gameId}/preload-check`), {
              method: "POST",
              body: {
                request_id: requestId(),
                lease_id: playback.leaseId,
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
      if (playback.preloadingGame === gameId) playback.preloadComplete = true;
    } catch (error) {
      if (playback.preloadingGame === gameId) {
        playback.preloadingGame = null;
        playback.preloadRetryAt = now() + 2000;
        showNotice(`Audio preparation will retry: ${error.message}`);
      }
    }
  }

  async function reportAudioFailure(game, round, reason) {
    if (
      playback.failedRounds.has(round.id) ||
      !playback.leaseId ||
      !["ready", "countdown", "answering"].includes(game.phase)
    )
      return;
    playback.failedRounds.add(round.id);
    playback.interruptedRounds.add(round.id);
    stopAudio();
    try {
      await api(roundPath("/audio-failure"), {
        method: "POST",
        body: {
          request_id: requestId(),
          readiness_generation: round.readiness_generation,
          lease_id: playback.leaseId,
          reason,
        },
      });
    } catch (error) {
      if (![409, 410].includes(error.status))
        playback.failedRounds.delete(round.id);
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
    if (
      host &&
      playback.interruptedRounds.has(round.id) &&
      ["ready", "countdown", "answering"].includes(game.phase)
    ) {
      await reportAudioFailure(
        game,
        round,
        "Host left the page; playback was interrupted",
      );
      return;
    }
    const buffer = host ? playback.clips.get(round.audio_candidate_id) : null;
    if (game.phase === "ready") {
      const key = `${round.id}:${round.readiness_generation}`;
      const locallyReady =
        !host ||
        (playback.leaseId &&
          playback.unlocked &&
          buffer &&
          playback.preloadComplete);
      if (locallyReady && !readySent.has(key)) {
        readySent.add(key);
        try {
          await api(roundPath("/ready"), {
            method: "POST",
            body: {
              readiness_generation: round.readiness_generation,
              lease_id: host ? playback.leaseId : null,
            },
          });
        } catch (error) {
          readySent.delete(key);
          if (![409, 410].includes(error.status)) showNotice(error.message);
        }
      }
    }
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
        await reportAudioFailure(game, round, "Clip not present in host cache");
        return;
      }
      // A reloaded/new tab must never restart an already-playing song.
      if (now() > round.starts_at_ms + 1000) {
        await reportAudioFailure(
          game,
          round,
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
        await reportAudioFailure(game, round, error.message);
      }
    }
    if (
      host &&
      game.phase === "answering" &&
      playback.context &&
      playback.context.state !== "running"
    )
      await reportAudioFailure(game, round, "Host audio was interrupted");
  }

  function reset() {
    stopAudio();
    playback.leaseId = null;
    playback.preloadingGame = null;
    playback.preloadComplete = false;
    playback.clips.clear();
    decodedByUrl.clear();
    cachedGame = null;
    playback.preloadRetryAt = 0;
    playback.interruptedRounds.clear();
    playback.playedRounds.clear();
    playback.failedRounds.clear();
    playback.conflict = false;
  }

  async function renewLease() {
    if (!getState()?.me.is_host || !playback.leaseId) return;
    try {
      const lease = await api(path("/audio-controller"), {
        method: "POST",
        body: { tab_id: tabId, takeover: false },
      });
      playback.leaseId = lease.lease_id;
    } catch (error) {
      if ([403, 409].includes(error.status)) {
        playback.leaseId = null;
        playback.conflict = true;
        stopAudio();
        render();
      }
      throw error;
    }
  }

  return {
    get status() {
      return {
        unlocked: playback.unlocked,
        leaseId: playback.leaseId,
        conflict: playback.conflict,
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
