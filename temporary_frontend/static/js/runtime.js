// Polling uses one request at a time. Heartbeats are independent of rendering.
export function createRuntime(model, transport, audio, render, showNotice, forgetRoom, schedule = setTimeout) {
  const ui = model.ui;
  const {api, path} = transport;

  async function poll() {
    try {
      if (!ui.roomId) return;
      const requestedRoom = ui.roomId;
      try {
        const state = await api(path("/state"));
        if (!model.applySnapshot(state, requestedRoom)) return;
        render();
        await audio.synchronize();
      } catch (error) {
        if ([401, 404, 410].includes(error.status)) {
          forgetRoom();
          showNotice(error.message);
        } else if (!ui.disconnected) {
          ui.disconnected = true;
          showNotice("Connection interrupted. Reconnecting automatically…");
        }
      }
    } finally {
      schedule(poll, 500);
    }
  }

  async function heartbeat() {
    if (ui.roomId && ui.state) {
      try {
        await api(path("/heartbeat"), {method: "POST", body: {}});
        await audio.renewLease();
      } catch (_) {
        // Polling reports connectivity; audio handles its own lease conflicts.
      }
    }
    schedule(heartbeat, 5000);
  }

  return {poll, heartbeat, start: () => { void poll(); void heartbeat(); }};
}
