import { musicAuthorization } from "./music-authorization.mjs";
import { musicPreparation } from "../game/preparation.mjs";

const draftKey = "repeat_music_draft";
function providersFrom(config) {
  const providers = config?.providers;
  if (!providers || typeof providers !== "object" || Array.isArray(providers) ||
    !Object.entries(providers).every(([id, provider]) => provider?.id === id &&
      typeof provider.label === "string" && typeof provider.enabled === "boolean"))
    throw new Error("The music configuration is invalid.");
  return providers;
}
// Only identity drafts live in browser storage. Authorization and import receipts
// remain in server cookies. Server mutations serialize; stale reads never render.
export function createMusicAdmission({
  ui, api, render, admitted,
  location = globalThis.location, history = globalThis.history,
  storage, schedule = setTimeout, cancel = clearTimeout,
  authorizers = musicAuthorization,
}) {
  let generation = 0, timer = null, request = null, failures = 0;
  let mutations = Promise.resolve();
  function stop() {
    generation++;
    cancel(timer);
    timer = null;
    request?.abort();
    request = null;
  }
  function serialize(operation) {
    const next = mutations.then(operation, operation);
    mutations = next.catch(() => {});
    return next;
  }
  async function mutate(epoch, operation) {
    try { await serialize(operation); }
    catch (error) { if (epoch === generation) throw error; }
  }
  function clearCallback() {
    const url = new URL(location.href);
    url.searchParams.delete("music");
    history.replaceState({}, "", url);
  }
  function identity(fields) {
    if (!fields || typeof fields.nickname !== "string" || typeof fields.character_id !== "string") return null;
    return { nickname: fields.nickname, character_id: fields.character_id, mode: "normal",
      ...(typeof fields.room_id === "string" ? { room_id: fields.room_id } : {}) };
  }
  function remembered() {
    try {
      const value = JSON.parse(storage?.getItem(draftKey) || "null");
      const fields = identity(value?.fields);
      return fields ? { fields, ...(typeof value.code === "string" ? { code: value.code } : {}) } : null;
    } catch { return null; }
  }
  function draft(fields, code) {
    const clean = identity(fields);
    if (!clean) throw new Error("Your music connection is missing your player details. Go back and try again.");
    const prior = ui.musicConnection;
    ui.musicConnection = { ...prior, fields: clean, code: code ?? prior?.code };
    ui.draftNickname = clean.nickname;
    ui.character = clean.character_id;
    ui.mode = "normal";
    ui.screen = clean.room_id ? "join" : "create";
    if (ui.musicConnection.code) ui.draftCode = ui.musicConnection.code;
    storage?.setItem(draftKey, JSON.stringify({ fields: clean, code: ui.musicConnection.code }));
  }
  function restoreConnection(result) {
    const saved = remembered();
    const fields = identity(result?.connection) || ui.musicConnection?.fields || saved?.fields;
    if (fields) draft(fields, ui.musicConnection?.code || saved?.code);
  }
  async function accept(result, epoch) {
    if (result.status !== "complete") return false;
    if (!result.admission?.room_id) throw new Error("The music import returned an invalid room receipt.");
    if (typeof result.admission_id !== "string" || !result.admission_id)
      throw new Error("The music import returned an invalid connection receipt.");
    if (epoch !== generation) return true;
    await admitted(result.admission);
    if (epoch !== generation) return true;
    ui.musicImport = null;
    ui.musicConnection = null;
    ui.error = null;
    storage?.removeItem(draftKey);
    clearCallback();
    render();
    // Publish the accepted room before retiring its receipt. Pagehide during
    // acknowledgment then resumes the actual room, rather than an expired import.
    try { await api("/api/music/acknowledge", { method: "POST", body: { admission_id: result.admission_id } }); } catch {}
    return true;
  }
  async function config(epoch) {
    if (epoch !== generation || !ui.musicConnection) return;
    ui.musicConnection.loading = true;
    ui.musicConnection.configError = null;
    render();
    try {
      const result = await api("/api/music/config");
      if (epoch !== generation) return;
      ui.musicConnection.providers = providersFrom(result);
    } catch (error) {
      if (epoch !== generation) return;
      ui.musicConnection.configError = error.message;
    } finally {
      if (epoch === generation && ui.musicConnection) {
        ui.musicConnection.loading = false;
        render();
      }
    }
  }
  async function failed(error, epoch) {
    if (epoch !== generation) return;
    ui.error = error;
    ui.musicImport = null;
    clearCallback();
    if (ui.musicConnection) {
      ui.musicConnection.error = musicPreparation({ status: "failed", error }).message;
      await config(epoch);
      if (epoch !== generation) return;
    }
    render();
  }
  async function poll(epoch, callbackStatus) {
    if (epoch !== generation) return;
    const controller = new AbortController();
    request = controller;
    try {
      const result = await api("/api/music/status", { signal: controller.signal });
      if (epoch !== generation) return;
      failures = 0;
      restoreConnection(result);
      if (await serialize(() => accept(result, epoch))) return;
      if (epoch !== generation) return;
      if (result.status === "cancelled") {
        ui.musicImport = null;
        ui.error = null;
        clearCallback();
        await config(epoch);
        if (epoch !== generation) return;
        render();
        return;
      }
      if (result.status === "failed" || callbackStatus === "error") {
        await failed(result.error || { message: "Music verification failed. Connect your music again to retry." }, epoch);
        if (epoch !== generation) return;
        return;
      }
      if (!["pending", "processing"].includes(result.status)) throw new Error("The music import returned an invalid status.");
      ui.musicImport = { status: result.status };
      render();
      timer = schedule(() => void poll(epoch), 750);
    } catch (error) {
      if (epoch !== generation) return;
      failures++;
      if ([401, 404, 410].includes(error.status)) {
        restoreConnection();
        await failed({ message: error.message, code: error.code }, epoch);
        if (epoch !== generation) return;
      } else if (failures >= 3) ui.musicImport = { status: "interrupted" };
      else {
        ui.musicImport = { status: "processing", reconnecting: true };
        timer = schedule(() => void poll(epoch), 1500);
      }
      render();
    } finally {
      if (request === controller) request = null;
    }
  }
  return {
    async open(fields, code) {
      stop();
      const epoch = generation;
      ui.error = null;
      ui.canonicalUrl = null;
      ui.musicImport = null;
      ui.musicConnection = null;
      ui.page = "play";
      draft(fields, code);
      await config(epoch);
    },
    async loadConfig() { await config(generation); },
    async start(provider = Object.keys(authorizers)[0]) {
      stop();
      const epoch = generation;
      const connection = ui.musicConnection;
      if (!connection) throw new Error("Choose your player details before connecting music.");
      ui.error = null;
      connection.error = null;
      ui.canonicalUrl = null;
      await mutate(epoch, async () => {
        if (epoch !== generation) return;
        const cancelled = await api("/api/music/cancel", { method: "POST", body: {} });
        if (epoch !== generation) return;
        if (await accept(cancelled, epoch)) return;
        if (epoch !== generation) return;
        if (cancelled.status !== "cancelled") throw new Error("Couldn’t cancel the previous music connection. Try again.");
        const result = await api("/api/music/config");
        if (epoch !== generation) return;
        connection.providers = providersFrom(result);
        const capability = connection.providers[provider];
        const strategy = Object.hasOwn(authorizers, provider) ? authorizers[provider] : null;
        if (!capability?.enabled || !strategy) throw new Error(capability?.reason || "This music provider is unavailable.");
        ui.canonicalUrl = strategy.application(capability, location, connection.code);
        if (ui.canonicalUrl) throw new Error("Open the configured game address before signing in.");
        const { mode, ...fields } = connection.fields;
        const admission = await api("/api/music/admissions", { method: "POST", body: { ...fields, provider } });
        if (epoch !== generation) return;
        location.assign(strategy.authorization(admission.authorization));
      });
    },
    async back(toProviders = false) {
      stop();
      const epoch = generation;
      await mutate(epoch, async () => {
        if (epoch !== generation) return;
        const result = await api("/api/music/cancel", { method: "POST", body: {} });
        if (epoch !== generation) return;
        restoreConnection(result);
        if (await accept(result, epoch)) return;
        if (epoch !== generation) return;
        if (result.status !== "cancelled") throw new Error("Couldn’t cancel your music connection. Try again.");
        ui.musicImport = null;
        ui.error = null;
        ui.canonicalUrl = null;
        clearCallback();
        if (toProviders && ui.musicConnection) {
          ui.musicConnection.error = null;
          await config(epoch);
          if (epoch !== generation) return;
        } else {
          ui.musicConnection = null;
          storage?.removeItem(draftKey);
        }
        render();
      });
    },
    resume(callbackStatus) {
      stop();
      failures = 0;
      ui.roomId = null;
      ui.state = null;
      ui.page = "play";
      ui.error = null;
      restoreConnection();
      ui.musicImport = { status: "processing" };
      render();
      return poll(generation, callbackStatus);
    },
    recover() {
      const saved = remembered();
      if (!saved || (ui.screen === "join" && (!saved.code ||
        (ui.draftCode || "").trim().toUpperCase() !== saved.code.trim().toUpperCase())))
        return Promise.resolve();
      return this.resume();
    },
    resumePage() {
      if (ui.musicImport) return this.resume();
      if (ui.musicConnection) return this.loadConfig();
      return Promise.resolve();
    },
    stop,
  };
}
