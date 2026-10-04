import { BLOB_COLORS } from "../components/blob-palette.mjs";

export const LAB_SCENES = Object.freeze([
  "characters",
  "lobby",
  "listening",
  "submitted",
  "reveal",
  "leaderboard",
]);
// Metadata-only samples keep rendering tests independent of installed music.
const SAMPLE_SONGS = Object.freeze([
  Object.freeze({
    token: "sample-song", title: "Sample song", artist: "Sample artist", artwork_url: null,
  }),
  Object.freeze({
    token: "sample-other", title: "Another sample song", artist: "Another sample artist", artwork_url: null,
  }),
]);
const NAMES = [
  "jules",
  "milo",
  "sara",
  "alex",
  "ken",
  "taylor",
  "morgan",
  "riley",
];
const LISTENERS = ["lab-1", "lab-4", "lab-7"];

export function createLabState(now) {
  const players = NAMES.map((nickname, index) => ({
    id: `lab-${index}`,
    nickname,
    character_id: BLOB_COLORS[index].id,
    is_host: index === 0,
    connected: true,
    song_count: 36,
    music_status: "demo",
  }));
  return {
    server_now_ms: now,
    room: {
      id: "lab",
      code: "7F3K9Q",
      state: "playing",
      mode: "demo",
      revision: 1,
    },
    me: players[0],
    players,
    settings: {
      round_count: 10,
      answer_seconds: 20,
      difficulty: "mixed",
      decoys_enabled: true,
    },
    game: null,
  };
}

export function createLabUi() {
  return {
    pending: false,
    listeners: new Set(LISTENERS),
    songGuess: null,
    character: "coral",
    draftNickname: "jules",
    draftCode: "",
    disconnected: false,
  };
}

/** Fixture data follows the same owner-only reveal contract as the server. */
export function createRoundFixture({
  scene, state, ui, now, levels, params, songs = SAMPLE_SONGS,
}) {
  const game = {
    id: "lab-game",
    status: "playing",
    phase: ["listening", "submitted"].includes(scene) ? "setup" : scene,
    preparation: { checked: levels.length ? 1 : 0, total: 1 },
    state_version: 1,
    requested_rounds: 10,
    playable_rounds: 10,
    missing_player_ids: [],
    round: {
      id: "lab-round",
      round_number: 1,
      attempt: 1,
      readiness_generation: 1,
      starts_at_ms: now - 8000,
      deadline_at_ms: now + 12000,
      submitted_player_ids: ["lab-2", "lab-5"],
      my_answer: null,
      waveform: levels,
    },
  };
  if (scene === "submitted") {
    game.round.my_answer = {
      song_guess: songs[0],
      who_player_ids: [...ui.listeners],
    };
    game.round.submitted_player_ids.push("lab-0", "lab-1", "lab-7");
  }
  if (!["reveal", "leaderboard"].includes(scene)) return game;

  game.phase_ends_at_ms = now + 5000;
  game.leaderboard = state.players.map((player, index) => ({
    player_id: player.id,
    nickname: player.nickname,
    character_id: player.character_id,
    rank: index + 1,
    score: 900 - index * 75,
  }));
  const own = {
    player_id: state.me.id,
    status: "submitted",
    song_guess: songs[params.has("wrong-answer") ? 1 : 0],
    who_player_ids: ["lab-1", "lab-4"],
    points: 100,
    song_match: params.has("wrong-answer") ? "wrong" : "correct",
  };
  if (params.has("missing-answer"))
    Object.assign(own, {
      status: "missing",
      song_guess: null,
      song_match: "unanswered",
      who_player_ids: null,
      points: 0,
    });
  else if (params.has("artist-only"))
    Object.assign(own, {
      song_guess: { ...songs[0], title: "Another track" },
      song_match: "artist",
      points: 50,
    });
  if (params.has("nobody") && own.status === "submitted")
    own.who_player_ids = [];
  game.round.reveal = {
    song: {
      ...songs[0],
      artwork_url: params.has("broken-artwork")
        ? "/ui/missing-lab-cover.png"
        : songs[0].artwork_url,
    },
    listener_ids: params.has("nobody") ? [] : [...LISTENERS],
    my_answer: own,
  };
  if (params.has("tied-ranks"))
    Object.assign(game.leaderboard[1], {
      rank: 1,
      score: game.leaderboard[0].score,
    });
  return game;
}
