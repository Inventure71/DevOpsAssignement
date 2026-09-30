// Presentation state and immutable submission receipts belong to this model.
// Server snapshots remain authoritative; receipts only protect an accepted
// answer from an older in-flight response reopening its controls.
export function createModel(storage) {
  const ui = {
    roomId: storage.getItem("repeat_room_id"), state: null,
    screen: "create", character: "vinyl", draftNickname: "", draftCode: "",
    songOption: null, listeners: new Set(), answerRound: null, pending: false,
    history: null, historyOpen: false, disconnected: false, dismissedGame: null,
  };
  const readySent = new Set();
  const acceptedAnswers = new Map();
  let answerGame = null;

  function rememberRoom(result) {
    ui.roomId = result.room_id;
    storage.setItem("repeat_room_id", ui.roomId);
    ui.dismissedGame = null;
  }

  function forgetRoom() {
    ui.roomId = null;
    ui.state = null;
    ui.answerRound = null;
    ui.songOption = null;
    ui.listeners.clear();
    storage.removeItem("repeat_room_id");
    readySent.clear();
    acceptedAnswers.clear();
    answerGame = null;
    ui.history = null;
    ui.historyOpen = false;
  }

  function applySnapshot(state, requestedRoom) {
    if (requestedRoom !== ui.roomId) return false;
    if (ui.state?.game?.id === state.game?.id && state.game && state.game.state_version < ui.state.game.state_version) return false;
    ui.disconnected = false;
    if (answerGame !== (state.game?.id || null)) {
      acceptedAnswers.clear();
      readySent.clear();
      answerGame = state.game?.id || null;
    }
    const round = state.game?.round;
    const accepted = round && acceptedAnswers.get(round.id);
    if (accepted) {
      round.my_answer = accepted;
      if (!round.submitted_player_ids.includes(state.me.id)) round.submitted_player_ids.push(state.me.id);
    }
    ui.state = state;
    if (round && ui.answerRound !== round.id) {
      ui.answerRound = round.id;
      ui.songOption = null;
      ui.listeners = new Set();
    }
    if (round?.my_answer) {
      ui.songOption = round.my_answer.song_option;
      ui.listeners = new Set(round.my_answer.who_player_ids || []);
    }
    return true;
  }

  function acceptAnswer(gameId, roundId, answer) {
    if (ui.state?.game?.id !== gameId) return;
    acceptedAnswers.set(roundId, answer);
    const round = ui.state.game.round;
    if (round?.id === roundId) {
      round.my_answer = answer;
      if (!round.submitted_player_ids.includes(ui.state.me.id)) round.submitted_player_ids.push(ui.state.me.id);
    }
  }

  return {ui, readySent, rememberRoom, forgetRoom, applySnapshot, acceptAnswer};
}
