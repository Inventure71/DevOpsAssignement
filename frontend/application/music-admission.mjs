// OAuth credentials stay in server cookies. This controller owns only navigation
// and the bounded polling lifecycle for an import receipt.
export function createMusicAdmission({
  ui,
  api,
  render,
  admitted,
  location = globalThis.location,
  history = globalThis.history,
  schedule = setTimeout,
  cancel = clearTimeout,
}) {
  let generation = 0;
  let timer = null;
  let request = null;
  let failures = 0;
  function stop() {
    generation++;
    cancel(timer);
    timer = null;
    request?.abort();
    request = null;
  }
  function clearCallback() {
    const url = new URL(location.href);
    url.searchParams.delete("spotify");
    history.replaceState({}, "", url);
  }
  async function poll(epoch) {
    if (epoch !== generation) return;
    request = new AbortController();
    try {
      const result = await api("/api/music/spotify/status", {
        signal: request.signal,
      });
      if (epoch !== generation) return;
      failures = 0;
      if (result.status === "complete") {
        if (!result.admission?.room_id)
          throw new Error("The music import returned an invalid room receipt.");
        await admitted(result.admission);
        if (epoch !== generation) return;
        ui.musicImport = null;
        clearCallback();
        render();
        return;
      }
      if (result.status === "failed") {
        ui.error = result.error || {
          message: "Spotify could not import your music. Please try again.",
        };
        ui.musicImport = { status: "failed", error: ui.error };
        clearCallback();
        render();
        return;
      }
      if (!["pending", "processing"].includes(result.status))
        throw new Error("The music import returned an invalid status.");
      ui.musicImport = { status: result.status };
      render();
      timer = schedule(() => void poll(epoch), 750);
    } catch (error) {
      if (epoch !== generation) return;
      failures++;
      if ([401, 404, 410].includes(error.status)) {
        ui.error = { message: error.message };
        ui.musicImport = { status: "failed", error: ui.error };
        clearCallback();
      } else if (failures >= 3) {
        ui.musicImport = {
          status: "interrupted",
          message: "Connection interrupted. Check your connection and retry.",
        };
      } else {
        ui.musicImport = { status: "processing", reconnecting: true };
        timer = schedule(() => void poll(epoch), 1500);
      }
      render();
    } finally {
      if (epoch === generation) request = null;
    }
  }
  return {
    async start(fields) {
      ui.error = null;
      ui.canonicalUrl = null;
      const config = await api("/api/music/spotify/config");
      if (!config.enabled)
        throw new Error("Spotify sign-in is not configured on this server yet.");
      if (config.requires_shared_url)
        throw new Error(
          "Spotify is configured for the server computer only. The host must finish network setup before other devices can sign in.",
        );
      const application = new URL(config.application_url);
      if (
        !["http:", "https:"].includes(application.protocol) ||
        application.username || application.password
      )
        throw new Error("The Spotify application URL is invalid.");
      if (application.origin !== location.origin) {
        if (ui.screen === "join" && ui.draftCode)
          application.searchParams.set("join", ui.draftCode);
        ui.canonicalUrl = application.href;
        throw new Error("Open the configured game address before signing in.");
      }
      await api("/api/music/spotify/cancel", { method: "POST", body: {} });
      const result = await api("/api/music/spotify/admissions", {
        method: "POST",
        body: fields,
      });
      const authorization = new URL(result.authorization_url);
      if (
        authorization.origin !== "https://accounts.spotify.com" ||
        authorization.pathname !== "/authorize"
      )
        throw new Error("The Spotify authorization address is invalid.");
      location.assign(authorization.href);
    },
    resume(callbackStatus) {
      stop();
      failures = 0;
      ui.roomId = null;
      ui.state = null;
      ui.page = "play";
      ui.error = null;
      if (callbackStatus === "error") {
        ui.error = {
          message: "Spotify verification failed. Sign in again to retry.",
        };
        ui.musicImport = { status: "failed", error: ui.error };
        clearCallback();
        render();
        return Promise.resolve();
      }
      ui.musicImport = { status: "processing" };
      render();
      return poll(generation);
    },
    stop,
  };
}
