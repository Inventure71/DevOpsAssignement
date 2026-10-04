// Drafts and accepted receipts are local; identity, deadlines and points are server-owned.
export function safeStorage(storage) {
  const memory = new Map();
  return {
    getItem(key) {
      try {
        return storage.getItem(key);
      } catch {
        return memory.get(key) || null;
      }
    },
    setItem(key, value) {
      memory.set(key, value);
      try {
        storage.setItem(key, value);
      } catch {}
    },
    removeItem(key) {
      memory.delete(key);
      try {
        storage.removeItem(key);
      } catch {}
    },
  };
}
export function createModel(
  storage,
  initialRoom = storage.getItem("repeat_room_id"),
) {
  const ui = {
    roomId: initialRoom,
    state: null,
    page: "play",
    screen: "create",
    character: "coral",
    draftNickname: "",
    draftCode: "",
    mode: "normal",
    launchStatus: "loading",
    launchConfig: null,
    launchError: null,
    musicImport: null,
    canonicalUrl: null,
    error: null,
    songGuess: null,
    listeners: new Set(),
    answerRound: null,
    pending: false,
    history: null,
    historyOpen: false,
    disconnected: false,
    dismissedGame: null,
  };
  const readySent = new Set();
  const acceptedAnswers = new Map();
  let answerGame = null;
  function rememberRoom(result) {
    ui.roomId = result.room_id;
    storage.setItem("repeat_room_id", ui.roomId);
    ui.dismissedGame = null;
    ui.page = "play";
  }
  function forgetRoom() {
    ui.roomId = null;
    ui.state = null;
    ui.answerRound = null;
    ui.songGuess = null;
    ui.listeners.clear();
    ui.history = null;
    ui.historyOpen = false;
    ui.dismissedGame = null;
    ui.disconnected = false;
    storage.removeItem("repeat_room_id");
    readySent.clear();
    acceptedAnswers.clear();
    answerGame = null;
  }
  function applySnapshot(state, requestedRoom) {
    if (requestedRoom !== ui.roomId) return false;
    if (
      ui.state?.room.id === state.room.id &&
      state.room.revision < ui.state.room.revision
    )
      return false;
    if (
      ui.state?.game?.id === state.game?.id &&
      state.game &&
      state.game.state_version < ui.state.game.state_version
    )
      return false;
    ui.disconnected = false;
    if (answerGame !== (state.game?.id || null)) {
      acceptedAnswers.clear();
      readySent.clear();
      answerGame = state.game?.id || null;
      ui.answerRound = null;
      ui.songGuess = null;
      ui.listeners = new Set();
    }
    const round = state.game?.round;
    const accepted = round && acceptedAnswers.get(round.id);
    if (accepted) {
      round.my_answer = accepted;
      if (!round.submitted_player_ids.includes(state.me.id))
        round.submitted_player_ids.push(state.me.id);
    }
    ui.state = state;
    if (ui.pending !== "character") ui.character = state.me.character_id;
    if (round && ui.answerRound !== round.id) {
      ui.answerRound = round.id;
      ui.songGuess = null;
      ui.listeners = new Set();
    }
    if (round?.my_answer) {
      ui.songGuess = round.my_answer.song_guess;
      ui.listeners = new Set(round.my_answer.who_player_ids || []);
    }
    return true;
  }
  function acceptAnswer(gameId, roundId, answer) {
    if (ui.state?.game?.id !== gameId) return;
    const receipt = {
      song_guess: answer.song_guess ? { ...answer.song_guess } : null,
      who_player_ids: [...answer.who_player_ids],
    };
    acceptedAnswers.set(roundId, receipt);
    const round = ui.state.game.round;
    if (round?.id === roundId) {
      round.my_answer = receipt;
      if (!round.submitted_player_ids.includes(ui.state.me.id))
        round.submitted_player_ids.push(ui.state.me.id);
    }
  }
  return {
    ui,
    readySent,
    rememberRoom,
    forgetRoom,
    applySnapshot,
    acceptAnswer,
  };
}
