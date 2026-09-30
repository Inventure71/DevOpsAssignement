import {requestId} from "./transport.js";

// All user gestures and mutations enter here; polling never submits answers.
export function bindActions({app, leaveButton, navigator, confirm}, model, transport, audio, render, showNotice, forgetRoom) {
  const ui = model.ui;
  const {api, path, gamePath, roundPath} = transport;
  app.addEventListener("input", event => {
    if (event.target.name === "nickname") ui.draftNickname = event.target.value;
    if (event.target.name === "code") ui.draftCode = event.target.value.toUpperCase();
  });

  app.addEventListener("change", async event => {
    if (!event.target.dataset.setting || !ui.state?.me.is_host) return;
    const name = event.target.dataset.setting;
    const value = name === "difficulty" ? event.target.value : name === "decoys_enabled" ? event.target.value === "true" : Number(event.target.value);
    try { await api(path("/settings"),{method:"PATCH",body:{...ui.state.settings,[name]:value}}); }
    catch (error) {
      showNotice(error.message);
      render(true);
    }
  });

  app.addEventListener("submit", async event => {
    if (event.target.id !== "entry-form") return;
    event.preventDefault();
    if (ui.pending) return;
    ui.pending = true;
    render();
    try {
      const fields = {nickname:ui.draftNickname.trim(),character_id:ui.character};
      let result;
      if (ui.screen === "join") {
        const resolved = await api(`/api/room-codes/${encodeURIComponent(ui.draftCode.trim().toUpperCase())}`);
        result = await api(`/api/rooms/${resolved.room_id}/join`,{method:"POST",body:fields});
      } else result = await api("/api/rooms",{method:"POST",body:{...fields,mode:"demo"}});
      model.rememberRoom(result);
      await api(path("/heartbeat"),{method:"POST",body:{}});
    } catch (error) {
      showNotice(error.message);
    }
    finally {
      ui.pending = false;
      render();
    }
  });

  app.addEventListener("click", async event => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    // Let the form's default click action dispatch submit before any rerender.
    if (button.type === "submit" && !button.dataset.action) return;
    if (button.dataset.character) { ui.character = button.dataset.character; render(); return; }
    if (button.dataset.option !== undefined) { ui.songOption = Number(button.dataset.option); render(); return; }
    if (button.dataset.listener) { const id = button.dataset.listener; ui.listeners.has(id) ? ui.listeners.delete(id) : ui.listeners.add(id); render(); return; }
    const action = button.dataset.action;
    try {
      if (action === "create-tab" || action === "join-tab") { ui.screen = action === "join-tab" ? "join" : "create"; render(); }
      else if (action === "copy-code") {
        if (navigator.clipboard?.writeText) {
          try { await navigator.clipboard.writeText(ui.state.room.code); showNotice("Room code copied."); }
          catch (_) { showNotice(`Share this room code: ${ui.state.room.code}`); }
        } else showNotice(`Share this room code: ${ui.state.room.code}`);
      }
      else if (action === "enable-audio" || action === "takeover-audio") await audio.enable(action === "takeover-audio");
      else if (action === "nobody") { ui.listeners.clear(); render(); }
      else if (action === "start") {
        ui.pending = true; render();
        await api(path("/start"),{method:"POST",body:{request_id:requestId(),room_revision:ui.state.room.revision,lease_id:audio.status.leaseId}});
        ui.dismissedGame = null;
      } else if (action === "submit-answer") {
        const gameId = ui.state.game.id;
        const roundId = ui.state.game.round.id;
        const answer = {song_option:ui.songOption,who_player_ids:[...ui.listeners].sort()};
        const answerUrl = roundPath("/answers");
        ui.pending = true; render();
        await api(answerUrl,{method:"POST",body:answer});
        model.acceptAnswer(gameId, roundId, answer);
      } else if (action === "retry-ready" || action === "continue-ready") {
        const round = ui.state.game.round;
        const body = {request_id:requestId(),readiness_generation:round.readiness_generation};
        if (action === "continue-ready") body.exclude_player_ids = (ui.state.game.missing_player_ids || ui.state.players.filter(p => !round.ready_player_ids.includes(p.id) && !round.excluded_player_ids.includes(p.id)).map(p => p.id)).filter(id => !ui.state.players.find(p => p.id === id)?.is_host);
        await api(roundPath(action === "retry-ready" ? "/retry" : "/continue"),{method:"POST",body});
      } else if (action === "end-game") {
        if (confirm("End this session? Scores from revealed rounds will be kept.")) await api(gamePath("/end"),{method:"POST",body:{request_id:requestId()}});
      } else if (action === "back-lobby") { ui.dismissedGame = ui.state.game.id; render(); }
      else if (action === "show-history") {
        ui.historyOpen = !ui.historyOpen; render();
        if (ui.historyOpen) { ui.history = await api(`/api/room-codes/${ui.state.room.code}/history`); render(); }
      }
    } catch (error) {
      showNotice(error.message);
    }
    finally {
      ui.pending = false;
      render();
    }
  });

  leaveButton.addEventListener("click", async () => {
    if (!confirm(ui.state.me.is_host ? "Leave the room? An active session will end for everyone." : "Leave the room?")) return;
    try { await api(path("/leave"),{method:"POST",body:{request_id:requestId()}}); forgetRoom(); }
    catch (error) { showNotice(error.message); }
  });


}
