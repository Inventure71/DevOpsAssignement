// Sample each window evenly: bounded analysis work even for long source buffers.
export function waveformLevels(
  buffer,
  count = 48,
  durationSeconds = buffer.duration,
) {
  const channels = Array.from(
    { length: buffer.numberOfChannels || 1 },
    (_, channel) => buffer.getChannelData(channel),
  );
  const samples = channels[0];
  const duration =
    Number.isFinite(buffer.duration) && buffer.duration > 0
      ? buffer.duration
      : null;
  const fraction =
    duration && Number.isFinite(durationSeconds)
      ? Math.max(0, durationSeconds / duration)
      : 1;
  // The full round is the x-axis. Short clips leave actual silence afterward,
  // rather than stretching ten seconds of sound into a twenty-second round.
  const length = Math.min(
    Number.MAX_SAFE_INTEGER,
    Math.floor(samples.length * fraction),
  );
  count = Math.round(
    Math.min(256, Math.max(1, Number.isFinite(count) ? count : 48)),
  );
  const levels = [];
  for (let bar = 0; bar < count; bar++) {
    const start = Math.floor((bar * length) / count);
    const end = Math.floor(((bar + 1) * length) / count);
    const stride = Math.max(1, Math.floor((end - start) / 128));
    let sum = 0,
      n = 0;
    for (let sample = start; sample < end; sample += stride) {
      for (const channel of channels) {
        const value = Number.isFinite(channel[sample]) ? channel[sample] : 0;
        sum += value * value;
        n++;
      }
    }
    levels.push(n ? Math.sqrt(sum / n) : 0);
  }
  const peak = Math.max(...levels, 0.001);
  return levels.map((level) => Math.round((level / peak) * 1000) / 1000);
}
