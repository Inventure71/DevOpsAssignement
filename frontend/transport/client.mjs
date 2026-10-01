// Cookies authenticate requests; command identifiers are not credentials.
export function requestId(crypto = globalThis.crypto) {
  if (typeof crypto?.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const h = [...bytes]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
export function createTransport(
  getRoomId,
  getState,
  fetcher = globalThis.fetch,
  clock = Date.now,
) {
  let offset = 0;
  let observed = false;
  let bestRtt = Infinity;
  const path = (suffix) =>
    `/api/rooms/${encodeURIComponent(getRoomId())}${suffix}`;
  const gamePath = (suffix) => path(`/games/${getState().game.id}${suffix}`);
  const roundPath = (suffix) =>
    gamePath(`/rounds/${getState().game.round.id}${suffix}`);
  async function api(url, { method = "GET", body, headers = {}, signal } = {}) {
    const sentAt = clock();
    const controller = new AbortController();
    const cancel = () => controller.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    if (signal?.aborted) controller.abort();
    const timer = setTimeout(cancel, 10000);
    let response, data;
    try {
      response = await fetcher(url, {
        method,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
        headers: {
          ...headers,
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
      data = await response.json().catch(() => ({}));
      if (typeof data.server_now_ms === "number") {
        const receivedAt = clock();
        const rtt = receivedAt - sentAt;
        const sample = data.server_now_ms - (sentAt + receivedAt) / 2;
        if (!observed || rtt <= bestRtt * 1.5) {
          offset = observed ? offset * 0.75 + sample * 0.25 : sample;
          observed = true;
          bestRtt = Math.min(bestRtt, rtt);
        }
      }
      if (!response.ok) {
        const error = new Error(
          data.error?.message || `Request failed (${response.status})`,
        );
        Object.assign(error, {
          status: response.status,
          code: data.error?.code,
          details: data.error?.details,
        });
        throw error;
      }
      return data;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancel);
    }
  }
  return { api, path, gamePath, roundPath, now: () => clock() + offset };
}
