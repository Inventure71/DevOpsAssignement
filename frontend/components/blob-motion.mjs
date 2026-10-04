// One bounded frame loop per page, shared by visible moving blobs.
export function createBlobMotionHub({
  requestFrame,
  cancelFrame,
  frameMs = 1000 / 30,
}) {
  const members = new Set();
  let enabled = true,
    frame = null,
    last = null,
    frames = 0;
  function schedule() {
    if (enabled && members.size && frame === null) frame = requestFrame(tick);
  }
  function tick(time) {
    frame = null;
    if (!enabled || !members.size) return;
    if (last === null || time - last >= frameMs - 0.5) {
      const elapsed =
        last === null ? 1 / 30 : Math.min(0.064, (time - last) / 1000);
      last = time;
      frames++;
      for (const member of members) member(time, elapsed);
    }
    schedule();
  }
  function stop() {
    if (frame !== null) cancelFrame(frame);
    frame = null;
    last = null;
  }
  return {
    add(member) {
      members.add(member);
      schedule();
      return () => {
        members.delete(member);
        if (!members.size) stop();
      };
    },
    setEnabled(value) {
      enabled = Boolean(value);
      if (enabled) schedule();
      else stop();
    },
    get stats() {
      return { members: members.size, running: frame !== null, frames };
    },
  };
}
