// Request IDs are identifiers, not player credentials. Cookies authenticate.
export function requestId(crypto = globalThis.crypto) {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // randomUUID needs a secure context; getRandomValues also works on local LAN
  // HTTP. These IDs identify commands/tabs, never authenticate a player.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2,"0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}


export function createTransport(getRoomId, getState, fetcher = globalThis.fetch) {
  let serverOffset = 0;
  const fetch = fetcher;
  const path = suffix => `/api/rooms/${encodeURIComponent(getRoomId())}${suffix}`;
  const gamePath = suffix => path(`/games/${getState().game.id}${suffix}`);
  const roundPath = suffix => gamePath(`/rounds/${getState().game.round.id}${suffix}`);
  async function api(url, {method = "GET", body, headers = {}} = {}) {
    const sentAt = Date.now();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),10000);
    let response, data;
    try {
      response = await fetch(url, {
        method, credentials: "same-origin", cache: "no-store",signal:controller.signal,
        headers: { ...headers, ...(body !== undefined ? {"Content-Type": "application/json"} : {}) },
        ...(body !== undefined ? {body: JSON.stringify(body)} : {}),
      });
      data = await response.json().catch(() => ({}));
    } finally {
      clearTimeout(timeout);
    }
    if (typeof data.server_now_ms === "number") {
      const offset = data.server_now_ms - (sentAt + Date.now()) / 2;
      serverOffset = getState() ? serverOffset * .7 + offset * .3 : offset;
    }
    if (!response.ok) {
      const error = new Error(data.error?.message || data.detail || `Request failed (${response.status})`);
      error.code = data.error?.code;
      error.status = response.status;
      error.details = data.error?.details;
      throw error;
    }
    return data;
  }


  return {api, path, gamePath, roundPath, now: () => Date.now() + serverOffset};
}
