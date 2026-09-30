import {characters, esc, icon} from "./view-helpers.js";

// Screen templates read presentation state; IO and DOM updates belong elsewhere.
export function createViews(ui, getPlayback, now) {
  const playerName = id => ui.state?.players.find(p => p.id === id)?.nickname || "Player";
  let playback;
  function avatar(player) {
    return `<span class="avatar" aria-hidden="true">${icon(player.character_id)}</span>`;
  }

  function renderEntry() {
    const join = ui.screen === "join";
    return `<section class="entry">
      <div><p class="eyebrow">THE MUSIC PARTY GAME</p>
        <h1 class="entry-title">WHO'S<br>ON<br><span class="repeat">REPEAT?</span></h1>
        <p class="entry-copy">Guess the song. Guess who listens.<br>Find out how well you know your people.</p>
        <div class="entry-bottom"><span class="small-rule"></span><span>3–10 people. One shared speaker.<br>Everybody on their own screen.</span></div>
      </div>
      <div class="entry-right">
        <div class="vinyl-stage" aria-hidden="true"><div class="vinyl"><span class="vinyl-dot"></span></div></div>
        <div class="entry-form">
          <div class="tab-bar" aria-label="Choose how to play"><button class="tab ${join ? "" : "active"}" data-action="create-tab">Host a game</button><button class="tab ${join ? "active" : ""}" data-action="join-tab">Join a game</button></div>
          <form id="entry-form"><div class="form-grid">
            <label class="field ${join ? "" : "field-full"}"><span class="field-label">YOUR NAME</span><input name="nickname" autocomplete="nickname" maxlength="24" required placeholder="What should we call you?" value="${esc(ui.draftNickname)}"></label>
            ${join ? `<label class="field"><span class="field-label">ROOM CODE</span><input name="code" autocapitalize="characters" autocomplete="off" maxlength="6" minlength="6" required placeholder="ABC123" value="${esc(ui.draftCode)}" style="text-transform:uppercase;letter-spacing:2px"></label>` : ""}
            <fieldset class="field-full" style="border:0;padding:0;margin:0"><legend class="field-label">PICK YOUR CHARACTER</legend><div class="characters">${Object.entries(characters).map(([id, symbol]) => `<button type="button" class="character ${ui.character === id ? "selected" : ""}" data-character="${id}" aria-label="${id}" aria-pressed="${ui.character === id}">${symbol}</button>`).join("")}</div></fieldset>
          </div>
          <div class="mode-note"><span>${join ? "Enter the code your host shared." : "Demo · Original clips, assigned automatically"}</span>${join ? "" : `<span class="badge">NO SIGN-IN</span>`}</div>
          <button class="button full" type="submit" ${ui.pending ? "disabled" : ""}>${ui.pending ? "One moment…" : join ? "Join the room" : "Create a demo room"}<span aria-hidden="true">↗</span></button>
          ${join ? "" : `<p class="fine-print">Personal music mode is coming after provider integration. Demo songs are assigned from the built-in catalog.</p>`}
          </form>
        </div>
      </div>
    </section>`;
  }

  function roomHeader(title, eyebrow, timer = null) {
    return `<div class="workspace-head"><div><p class="eyebrow">${esc(eyebrow)}</p><h1>${esc(title)}</h1></div>${timer === null ? `<div class="room-code"><span class="field-label">ROOM CODE</span><strong>${esc(ui.state.room.code)}</strong><button class="text-button" data-action="copy-code">Copy code ↗</button></div>` : `<div class="timer" data-countdown="${timer}" role="timer" aria-label="Seconds remaining"></div>`}</div>`;
  }

  function roster() {
    return `<ul class="roster">${ui.state.players.map(player => `<li class="player-row">${avatar(player)}<div><span class="player-name">${esc(player.nickname)}${player.id === ui.state.me.id ? " · you" : ""}</span><span class="player-caption">${player.is_host ? "Host + player" : "Player"} · ${player.song_count ?? 0} songs ready</span></div><span class="player-status"><span class="status-dot ${player.connected ? "" : "offline"}"></span>${player.connected ? "Ready" : "Away"}</span></li>`).join("")}</ul>`;
  }

  function setting(name, label, values, current) {
    const labels = values.map(value => {
      const text = name === "decoys_enabled" ? value ? "On" : "Off" : name === "difficulty" ? value[0].toUpperCase()+value.slice(1) : `${value}${name === "answer_seconds" ? " seconds" : " rounds"}`;
      return `<option value="${value}" ${current === value ? "selected" : ""}>${text}</option>`;
    }).join("");
    return `<div class="setting-line"><label for="setting-${name}">${label}</label><select id="setting-${name}" data-setting="${name}" ${ui.state.me.is_host ? "" : "disabled"}>${labels}</select></div>`;
  }

  function audioControl() {
    if (!ui.state.me.is_host) return "";
    if (playback.leaseId && playback.unlocked) return `<p class="audio-status"><span class="status-dot"></span>This tab plays the shared audio. Keep it open.</p>`;
    return `<button class="button secondary full" data-action="${playback.conflict ? "takeover-audio" : "enable-audio"}">${playback.conflict ? "Use this tab for audio" : "Enable shared audio"} <span aria-hidden="true">♫</span></button><p class="fine-print">${playback.conflict ? "Another host tab controls the speaker. Switching during a round voids that attempt." : "Connect your speaker, then tap to enable sound. Only the host device plays music."}</p>`;
  }

  function renderLobby() {
    const {players, settings, me, game} = ui.state;
    const canStart = players.length >= 3 && players.length <= 10 && players.every(p => p.song_count >= 10) && playback.unlocked && playback.leaseId;
    let lastError = "";
    if (game?.status === "aborted" && game.end_reason) {
      lastError = `<p class="error-inline">${esc(endReason(game))}</p>`;
    }
    return `<section class="workspace">${roomHeader("The listening room.", "DEMO / LOBBY")}
      ${lastError}<div class="lobby-grid"><div><h2 class="section-heading">The lineup <span>${players.length} / 10</span></h2>${roster()}<p class="fine-print">Share the room code. Each person joins from their own browser.</p>
      <button class="text-button" data-action="show-history">${ui.historyOpen ? "Hide" : "View"} previous rankings ↗</button>${ui.historyOpen ? renderHistory() : ""}</div>
      <div><h2 class="section-heading">Set the session</h2><div class="settings">${setting("round_count", "Number of rounds", [5,10,15], settings.round_count)}${setting("answer_seconds", "Time to guess", [10,20,30], settings.answer_seconds)}${setting("difficulty", "Difficulty", ["easy","mixed","hard"], settings.difficulty || "mixed")}${setting("decoys_enabled", "Decoy songs", [true,false], settings.decoys_enabled ?? true)}</div>
      <div class="actions">${audioControl()}${me.is_host ? `<button class="button full" data-action="start" ${!canStart || ui.pending ? "disabled" : ""}>Start the session <span aria-hidden="true">↗</span></button><p class="fine-print">${players.length < 3 ? "You need at least 3 players to start." : players.some(p => p.song_count < 10) ? "Each player needs at least 10 songs. The catalog currently has four temporary tracks." : !playback.leaseId ? "Enable audio before starting." : "Songs load once. Rounds advance automatically."}</p>` : `<p class="empty-wait">Your songs are ready.<br>Waiting for ${esc(players.find(p => p.is_host)?.nickname || "the host")} to start.</p>`}</div></div></div></section>`;
  }

  function liveRoster(round, readiness = false) {
    return `<div class="live-roster" aria-label="Player status">${ui.state.players.map(player => {
      const submitted = round?.submitted_player_ids?.includes(player.id);
      const ready = round?.ready_player_ids?.includes(player.id);
      const excluded = round?.excluded_player_ids?.includes(player.id);
      const status = readiness ? excluded ? "not required" : ready ? "checked in" : "syncing" : submitted ? "submitted" : "listening";
      return `<span class="live-person ${submitted || (readiness && ready) ? "submitted" : ""}">${avatar(player)}${esc(player.nickname)} · ${status}${player.connected ? "" : " · away"}</span>`;
    }).join("")}</div>`;
  }

  function recoveryControls(game, round) {
    if (game.phase !== "ready" || !round || now() < round.readiness_deadline_at_ms) return "";
    const missing = game.missing_player_ids || ui.state.players.filter(p => !round.ready_player_ids.includes(p.id) && !round.excluded_player_ids.includes(p.id)).map(p => p.id);
    if (!missing.length) return "";
    const host = ui.state.players.find(p => p.is_host);
    return `<div class="recovery"><h2 class="section-heading">Waiting on a check-in</h2><p>${missing.map(id => esc(playerName(id))).join(", ")} ${missing.length === 1 ? "has" : "have"} not checked in. Everybody keeps their place and points.</p>${ui.state.me.is_host ? `<div class="recovery-actions"><button class="button" data-action="retry-ready">Retry check-in</button><button class="button secondary" data-action="continue-ready" ${missing.includes(host.id) ? "disabled" : ""}>Continue without ${missing.filter(id => id !== host.id).map(id => esc(playerName(id))).join(", ")}</button></div>${missing.includes(host.id) ? `<p class="fine-print">Host audio must be ready before the round can start.</p>` : ""}` : `<p>The host can retry or continue without the missing check-ins.</p>`}</div>`;
  }

  function renderPreparing(game) {
    const round = game.round;
    const setup = game.phase === "setup";
    const countdown = game.phase === "countdown";
    const title = setup ? "Building the set." : countdown ? "Here we go." : "Getting in sync.";
    const end = countdown ? round.starts_at_ms : setup ? game.phase_ends_at_ms : round?.readiness_deadline_at_ms;
    return `<section class="workspace game-shell">${roomHeader(title, setup ? "SETTING UP YOUR SESSION" : `ROUND ${round?.round_number || 1} / ${game.requested_rounds}`, end)}
      <div class="phase-focus">${countdown ? `<div class="giant-countdown" data-countdown="${round.starts_at_ms}"></div><p>Music starts together. Guesses open when the countdown ends.</p>` : `<div class="giant-countdown">${setup ? "◉" : "≋"}</div><p>${setup ? "Loading the full set and its backups. This only happens once." : "Your browser checks in automatically. No button to press."}</p>`}</div>
      ${ui.state.me.is_host && (!playback.unlocked || !playback.leaseId) ? audioControl() : ""}
      ${setup ? `<p class="fine-print">${game.playable_rounds ? `${game.playable_rounds} playable rounds prepared.` : "Preparing original demo clips…"}</p>` : liveRoster(round, true)}${recoveryControls(game, round)}${hostEndButton()}</section>`;
  }

  function renderAnswering(game) {
    const round = game.round;
    const submitted = !!round.my_answer || round.submitted_player_ids.includes(ui.state.me.id);
    return `<section class="workspace game-shell">${roomHeader(submitted ? "You're locked in." : "Know this one?", `ROUND ${round.round_number} / ${game.requested_rounds}`, round.deadline_at_ms)}
      <div class="progress"><div class="progress-fill" data-progress-start="${round.starts_at_ms}" data-progress-end="${round.deadline_at_ms}"></div></div>
      <div class="guess-layout"><div><h2 class="section-heading">What's playing?</h2><div class="options">${round.options.map(option => `<button class="option ${ui.songOption === option.index ? "selected" : ""}" data-option="${option.index}" aria-pressed="${ui.songOption === option.index}" ${submitted || ui.pending ? "disabled" : ""}><span class="option-letter">${"ABCD"[option.index]}</span><span><strong>${esc(option.title)}</strong><small>${esc(option.artist)}</small></span></button>`).join("")}</div></div>
      <div><h2 class="section-heading">Who's listening to it?</h2><div class="listener-list">${ui.state.players.map(player => `<button class="listener ${ui.listeners.has(player.id) ? "selected" : ""}" data-listener="${esc(player.id)}" aria-pressed="${ui.listeners.has(player.id)}" ${submitted || ui.pending ? "disabled" : ""}><span aria-hidden="true">${icon(player.character_id)}</span>${esc(player.nickname)}</button>`).join("")}<button class="listener ${ui.listeners.size === 0 ? "selected" : ""}" data-action="nobody" aria-pressed="${ui.listeners.size === 0}" ${submitted || ui.pending ? "disabled" : ""}>∅ Nobody</button></div><button class="button full" data-action="submit-answer" ${submitted || ui.pending ? "disabled" : ""}>${submitted ? "Answer submitted ✓" : ui.pending ? "Submitting…" : "Lock in my guess ↗"}</button><p class="submit-note">${submitted ? "One final answer. The reveal is coming." : "No names selected means Nobody. You can submit a listener guess without choosing a song."}</p></div></div>${liveRoster(round)}${hostEndButton()}</section>`;
  }

  function renderReveal(game) {
    const round = game.round;
    const reveal = round.reveal;
    if (!reveal) return renderLeaderboard(game);
    return `<section class="workspace game-shell">${roomHeader("The reveal.", `ROUND ${round.round_number} / ${game.requested_rounds}`, game.phase_ends_at_ms)}
      <div class="reveal-grid"><img class="cover" src="${esc(reveal.song.artwork_url || "/static/images/cover-placeholder.svg")}" alt="Cover for ${esc(reveal.song.title)}" data-cover><div><h2 class="reveal-title">${esc(reveal.song.title)}</h2><p class="reveal-artist">${esc(reveal.song.artist)}</p><p class="real-listeners"><span class="eyebrow">ON REPEAT FOR</span><br>${reveal.listener_ids.length ? reveal.listener_ids.map(id => esc(playerName(id))).join(" · ") : "Nobody. That was a decoy!"}</p></div></div>
      <h3 class="section-heading">The guesses</h3>${reveal.answers.map(answer => {
        const player = ui.state.players.find(p => p.id === answer.player_id);
        const option = round.options.find(o => o.index === answer.song_option);
        return `<div class="reveal-answer"><span class="player-name">${icon(player?.character_id)} ${esc(player?.nickname || "Player")}</span><span class="answer-description">${answer.status === "missing" ? "No answer" : `${esc(option?.title || "No song selected")}<br>${answer.who_player_ids?.length ? answer.who_player_ids.map(id => esc(playerName(id))).join(", ") : "Nobody"}`}</span><span class="points">+${answer.points ?? 0}</span></div>`;
      }).join("")}</section>`;
  }

  function endReason(game) {
    const names = game.missing_player_ids?.map(playerName).join(", ");
    const reasons = {
      completed: "The full set is finished.", host_ended: "The host ended the session.", host_left: "The host left the room.",
      host_timeout: "The host did not reconnect within 60 seconds.", server_restart: "The server restarted. Scores from revealed rounds are saved.",
      readiness_timeout: `Check-in timed out${names ? `: ${names}` : ""}.`, initial_readiness_timeout: `Check-in timed out${names ? `: ${names}` : ""}.`,
      too_many_skips: "More than 30% of the requested rounds had no playable replacement.", too_many_skipped: "More than 30% of the requested rounds had no playable replacement.",
      preparation_timeout: "The host's full-set audio preparation timed out. Enable audio and try again.", host_preparation_timeout: "The host's full-set audio preparation timed out. Enable audio and try again.",
    };
    return reasons[game.end_reason] || (game.end_reason ? String(game.end_reason).replace(/_/g, " ") : "Your revealed-round scores are saved.");
  }

  function renderLeaderboard(game) {
    const finished = game.status === "completed" || game.status === "aborted";
    const partial = game.status === "aborted";
    return `<section class="workspace game-shell">${roomHeader(finished ? partial ? "The session ended." : "That's a wrap." : "Who's on top?", finished ? partial ? "PARTIAL RANKINGS" : "FINAL RANKINGS" : "LEADERBOARD", finished ? null : game.phase_ends_at_ms)}
      ${finished ? `<p class="fine-print" style="margin-bottom:25px">${esc(endReason(game))}</p>` : ""}
      <div aria-label="Rankings">${(game.leaderboard || []).map((player, index) => `<div class="leader-row ${player.player_id === ui.state.me.id ? "mine" : ""}"><span class="rank">${player.rank ?? index + 1}</span>${avatar(player)}<span class="player-name">${esc(player.nickname)}</span><span class="score">${player.score ?? player.final_score ?? 0}<span class="player-caption" style="text-align:right">POINTS</span></span></div>`).join("")}</div>
      ${finished ? `<div class="actions"><button class="button" data-action="back-lobby">Back to the listening room ↗</button></div>` : `<p class="fine-print" style="margin-top:25px">Next round starts automatically.${ui.state.players.find(p => p.is_host)?.connected ? "" : " Waiting for the host to reconnect."}</p>${hostEndButton()}`}</section>`;
  }

  function hostEndButton() {
    return ui.state.me.is_host ? `<button class="text-button" style="margin-top:30px" data-action="end-game">End session</button>` : "";
  }

  function renderHistory() {
    if (!ui.history) return `<p class="fine-print">Loading previous rankings…</p>`;
    const games = Array.isArray(ui.history) ? ui.history : ui.history.games || ui.history.history || [];
    if (!games.length) return `<p class="fine-print">No sessions saved yet.</p>`;
    return `<div class="history">${games.map(game => `<div class="history-game"><strong>${game.status === "aborted" ? "Partial" : "Completed"} session</strong> · ${new Date(game.ended_at_ms || game.started_at_ms).toLocaleDateString()}<br>${(game.leaderboard || game.rankings || []).map(p => `${esc(p.nickname)} ${p.score ?? p.final_score ?? 0}`).join(" · ")}</div>`).join("")}</div>`;
  }


  return function screenMarkup() {
    playback = getPlayback();
    if (!ui.state) return renderEntry();
    const game = ui.state.game;
    const finished = game && ["completed", "aborted"].includes(game.status);
    if (!game || (finished && (ui.dismissedGame === game.id || game.end_reason?.includes("readiness") || game.end_reason?.includes("preparation")))) return renderLobby();
    if (["setup", "ready", "countdown"].includes(game.phase)) return renderPreparing(game);
    if (game.phase === "answering") return renderAnswering(game);
    if (game.phase === "reveal") return renderReveal(game);
    return renderLeaderboard(game);
  };
}
