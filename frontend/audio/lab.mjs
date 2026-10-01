import { waveformLevels } from "./levels.mjs";

// Isolated fixture audio. The drawing component never fetches or schedules sound.
export function createLabAudio({
  url,
  durationSeconds = 20,
  onChange,
  environment = globalThis,
}) {
  let context,
    buffer,
    pending,
    source,
    abort,
    generation = 0;
  let levels = [];
  let state = "idle",
    closed = false,
    lastError = null;
  const publish = (error = lastError) => {
    lastError = error;
    if (!closed) onChange({ playbackState: state, levels, error });
  };
  function audioContext() {
    if (!context) {
      const Context =
        environment.AudioContext || environment.webkitAudioContext;
      if (!Context)
        throw new Error("Audio preview is unavailable in this browser.");
      context = new Context();
    }
    return context;
  }
  function load() {
    if (closed) return Promise.reject(new Error("Audio preview is closed."));
    if (buffer) return Promise.resolve(buffer);
    if (pending) return pending;
    state = "loading";
    publish(null);
    abort = new environment.AbortController();
    const timeout = environment.setTimeout(() => abort.abort(), 10000);
    pending = (async () => {
      const response = await environment.fetch(url, {
        signal: abort.signal,
        cache: "force-cache",
      });
      if (!response.ok)
        throw new Error("Could not load the preview clip. Try again.");
      const decoded = await audioContext().decodeAudioData(
        await response.arrayBuffer(),
      );
      if (!(decoded.duration > 0))
        throw new Error("The preview clip is empty.");
      buffer = decoded;
      levels = waveformLevels(
        buffer,
        64,
        Math.min(durationSeconds, buffer.duration),
      );
      if (state === "loading") state = "idle";
      publish();
      return buffer;
    })()
      .catch((error) => {
        state = "error";
        publish(error.message);
        throw error;
      })
      .finally(() => {
        environment.clearTimeout(timeout);
        pending = null;
      });
    return pending;
  }
  function stop() {
    generation++;
    if (source) {
      source.onended = null;
      source.stop();
      source.disconnect();
      source = null;
    }
    state = "idle";
    publish(null);
  }
  function unlock() {
    if (closed) return Promise.resolve();
    try {
      return audioContext().resume();
    } catch (error) {
      return Promise.reject(error);
    }
  }
  async function play() {
    stop();
    const attempt = generation;
    state = "loading";
    publish(null);
    try {
      // Resume within the click handler, before awaiting a fetch or decode.
      const resume = audioContext().resume();
      const [decoded] = await Promise.all([load(), resume]);
      if (closed || attempt !== generation) return null;
      const delay = 3;
      const duration = Math.min(durationSeconds, decoded.duration);
      const startsAt = environment.Date.now() + delay * 1000;
      source = context.createBufferSource();
      source.buffer = decoded;
      source.connect(context.destination);
      source.onended = () => {
        if (attempt !== generation || closed) return;
        source.disconnect();
        source = null;
        state = "ended";
        publish();
      };
      source.start(context.currentTime + delay);
      source.stop(context.currentTime + delay + duration);
      state = "playing";
      publish();
      return { startsAt, deadline: startsAt + duration * 1000 };
    } catch (error) {
      if (attempt === generation) {
        state = "error";
        publish(error.message);
      }
      return null;
    }
  }
  function close() {
    if (closed) return;
    stop();
    closed = true;
    abort?.abort();
    void context?.close().catch(() => {});
  }
  return { load, play, stop, close, unlock };
}
