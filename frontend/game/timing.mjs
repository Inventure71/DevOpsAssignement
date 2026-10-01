// The screen and audio drawing share one clock; neither owns a timer.
export function roundTiming({ startsAt, deadline, now }) {
  const valid =
    [startsAt, deadline, now].every(Number.isFinite) && deadline > startsAt;
  const duration = valid ? deadline - startsAt : 0;
  const elapsed = valid ? Math.min(duration, Math.max(0, now - startsAt)) : 0;
  const progress = duration ? elapsed / duration : 0;
  return {
    duration,
    elapsed,
    progress,
    remaining: duration - elapsed,
    remainingFraction: duration ? 1 - progress : 0,
    started: valid && now >= startsAt,
    expired: valid && now >= deadline,
  };
}
