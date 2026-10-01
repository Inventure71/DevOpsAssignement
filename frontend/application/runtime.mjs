// One state read at a time; heartbeats and host lease renewal run independently.
export function createRuntime(
  model,
  transport,
  audio,
  render,
  notice,
  forgetRoom,
  schedule = setTimeout,
  cancel = clearTimeout,
) {
  let running = false,
    generation = 0,
    inflight = null,
    pollTimer = null,
    beatTimer = null;
  async function read(epoch) {
    if (!model.ui.roomId) return;
    const room = model.ui.roomId;
    try {
      const state = await transport.api(transport.path("/state"));
      if (epoch !== generation) return;
      if (model.applySnapshot(state, room)) {
        render();
        await audio.synchronize();
      }
    } catch (error) {
      if (epoch !== generation || room !== model.ui.roomId) return;
      if ([401, 404, 410].includes(error.status)) {
        forgetRoom();
        notice(error.message);
      } else {
        model.ui.disconnected = true;
        render();
      }
    }
  }
  async function refresh({ fresh = false } = {}, epoch = generation) {
    while (inflight) {
      const pending = inflight;
      await pending.operation;
      if (epoch !== generation) return;
      if (!fresh && pending.epoch === epoch) return;
    }
    if (epoch !== generation) return;
    const pending = { epoch, operation: read(epoch) };
    inflight = pending;
    try {
      await pending.operation;
    } finally {
      if (inflight === pending) inflight = null;
    }
  }
  async function poll(epoch) {
    await refresh({}, epoch);
    if (running && epoch === generation)
      pollTimer = schedule(() => void poll(epoch), 500);
  }
  async function heartbeat(epoch) {
    if (!running || epoch !== generation) return;
    if (model.ui.roomId && model.ui.state) {
      try {
        await transport.api(transport.path("/heartbeat"), {
          method: "POST",
          body: {},
        });
        if (epoch !== generation) return;
        await audio.renewLease();
      } catch {
        /* State polling renders connectivity and audio handles lease conflicts. */
      }
    }
    if (running && epoch === generation)
      beatTimer = schedule(() => void heartbeat(epoch), 5000);
  }
  return {
    refresh,
    start() {
      if (running) return;
      running = true;
      const epoch = ++generation;
      void poll(epoch);
      void heartbeat(epoch);
    },
    stop() {
      running = false;
      generation++;
      cancel(pollTimer);
      cancel(beatTimer);
    },
  };
}
