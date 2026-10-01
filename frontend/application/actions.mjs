import { requestId } from "../transport/client.mjs";

// User commands own mutations. Polling never guesses, submits or changes settings.
export function createActions({
  model,
  transport,
  audio,
  runtime,
  render,
  notice,
  forgetRoom,
  navigator = globalThis.navigator,
  confirm = globalThis.confirm,
}) {
  const ui = model.ui;
  const { api, path, gamePath, roundPath } = transport;
  let retryStart = null;
  async function share(copyCode = false) {
    const code = ui.state.room.code;
    const url = new URL("/", location.origin);
    url.searchParams.set("join", code);
    if (!copyCode && navigator.share) {
      try {
        await navigator.share({
          title: "Who's On Repeat",
          text: `Join my room: ${code}`,
          url: url.href,
        });
        return;
      } catch (error) {
        if (error.name === "AbortError") return;
      }
    }
    const content = copyCode ? code : url.href;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(content);
        notice(copyCode ? "Room code copied." : "Invite link copied.");
        return;
      } catch {
        /* LAN HTTP may not allow Clipboard; show selectable content below. */
      }
    }
    const field = document.createElement("textarea");
    field.value = content;
    field.style.cssText = "position:fixed;opacity:0;left:-9999px";
    document.body.append(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    notice(copied ? "Invitation copied." : `Share this room code: ${code}`);
  }
  async function action(name, payload) {
    if (name === "draft") {
      if (payload.name === "nickname") ui.draftNickname = payload.value;
      if (payload.name === "code") ui.draftCode = payload.value.toUpperCase();
      return;
    }
    if (name === "entry-tab") {
      ui.screen = payload;
      render();
      return;
    }
    if (name === "character" && !ui.state) {
      ui.character = payload;
      render();
      return;
    }
    if (name === "back-lobby") {
      ui.dismissedGame = ui.state.game.id;
      ui.historyOpen = false;
      render();
      return;
    }
    if (["copy-code", "share-room", "invite"].includes(name)) {
      try {
        await share(name === "copy-code");
      } catch (error) {
        notice(error.message);
      }
      return;
    }
    if (ui.pending) return;
    if (
      name === "leave" &&
      !confirm(
        ui.state.me.is_host
          ? "Leave this room? An active game will end for everyone."
          : "Leave this room?",
      )
    )
      return;
    if (
      name === "end-game" &&
      !confirm("End this game? Revealed scores will be kept.")
    )
      return;
    ui.pending = name;
    render();
    try {
      if (name === "admit") {
        const fields = {
          nickname: ui.draftNickname.trim(),
          character_id: ui.character,
        };
        let result;
        if (ui.screen === "join") {
          const resolved = await api(
            `/api/room-codes/${encodeURIComponent(ui.draftCode.trim())}`,
          );
          result = await api(`/api/rooms/${resolved.room_id}/join`, {
            method: "POST",
            body: fields,
          });
        } else
          result = await api("/api/rooms", {
            method: "POST",
            body: { ...fields, mode: "demo" },
          });
        audio.reset();
        model.rememberRoom(result);
        await api(path("/heartbeat"), { method: "POST", body: {} });
        await runtime.refresh({ fresh: true });
        const url = new URL(location.href);
        url.searchParams.delete("join");
        url.searchParams.delete("page");
        url.searchParams.set("room", ui.roomId);
        history.replaceState({}, "", url);
      } else if (name === "character") {
        ui.character = payload;
        await api(path("/player"), {
          method: "PATCH",
          body: { nickname: ui.state.me.nickname, character_id: payload },
        });
        await runtime.refresh({ fresh: true });
      } else if (name === "setting") {
        await api(path("/settings"), {
          method: "PATCH",
          body: { [payload.name]: payload.value },
        });
        await runtime.refresh({ fresh: true });
      } else if (name === "enable-audio" || name === "takeover-audio") {
        await audio.enable(name === "takeover-audio");
        await runtime.refresh({ fresh: true });
      } else if (name === "start") {
        const revision = ui.state.room.revision;
        if (!retryStart || retryStart.revision !== revision)
          retryStart = { revision, request_id: requestId() };
        await api(path("/start"), {
          method: "POST",
          body: {
            request_id: retryStart.request_id,
            room_revision: revision,
            lease_id: audio.status.leaseId,
          },
        });
        ui.dismissedGame = null;
        retryStart = null;
        await runtime.refresh({ fresh: true });
      } else if (name === "submit-answer") {
        const state = ui.state;
        const round = state.game.round;
        if (
          state.game.phase !== "answering" ||
          round.my_answer ||
          transport.now() >= round.deadline_at_ms
        )
          return;
        const gameId = state.game.id,
          roundId = round.id;
        const selection = ui.songGuess ? { ...ui.songGuess } : null;
        const answer = {
          song_guess: selection,
          who_player_ids: [...ui.listeners].sort(),
        };
        if (selection && !selection.token)
          throw new Error("Choose the song again before submitting.");
        await api(roundPath("/answers"), {
          method: "POST",
          body: {
            song_guess_token: selection?.token || null,
            who_player_ids: answer.who_player_ids,
          },
        });
        model.acceptAnswer(gameId, roundId, answer);
        await runtime.refresh({ fresh: true });
      } else if (name === "retry-ready" || name === "continue-ready") {
        const state = ui.state,
          round = state.game.round;
        const body = {
          request_id: requestId(),
          readiness_generation: round.readiness_generation,
        };
        if (name === "continue-ready")
          body.exclude_player_ids = state.game.missing_player_ids.filter(
            (id) => !state.players.find((player) => player.id === id)?.is_host,
          );
        await api(roundPath(name === "retry-ready" ? "/retry" : "/continue"), {
          method: "POST",
          body,
        });
        await runtime.refresh({ fresh: true });
      } else if (name === "end-game") {
        await api(gamePath("/end"), {
          method: "POST",
          body: { request_id: requestId() },
        });
        await runtime.refresh({ fresh: true });
      } else if (name === "leave") {
        await api(path("/leave"), {
          method: "POST",
          body: { request_id: requestId() },
        });
        forgetRoom();
      } else if (name === "show-history") {
        ui.historyOpen = !ui.historyOpen;
        if (ui.historyOpen)
          ui.history = await api(
            `/api/room-codes/${ui.state.room.code}/history`,
          );
      }
    } catch (error) {
      notice(error.message);
      if (ui.roomId) await runtime.refresh({ fresh: true });
    } finally {
      ui.pending = false;
      render();
    }
  }
  return action;
}
