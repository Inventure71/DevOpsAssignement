import test from "node:test";
import assert from "node:assert/strict";
import {
  roundResult,
  gamePlayers,
  standingsModel,
  phaseProgress,
} from "../../frontend/game/results.mjs";

function state(answer = {}) {
  const players = ["a", "b", "c", "d"].map((id, index) => ({
    id,
    nickname: id,
    character_id: "coral",
  }));
  return {
    players,
    me: players[0],
    game: {
      phase: "reveal",
      status: "playing",
      phase_ends_at_ms: 25000,
      leaderboard: players.map((player, index) => ({
        player_id: player.id,
        nickname: player.nickname,
        character_id: player.character_id,
        score: 900 - index * 75,
        rank: index + 1,
      })),
      round: {
        reveal: {
          song: { title: "Track", artist: "Artist" },
          listener_ids: ["a", "b"],
          my_answer: {
            player_id: "a",
            status: "submitted",
            song_match: "correct",
            song_guess: { title: "Track", artist: "Artist" },
            who_player_ids: ["a", "c"],
            points: 120,
            ...answer,
          },
        },
      },
    },
  };
}

test("reveal classifies all four listener-selection cases from the local frozen answer", () => {
  const result = roundResult(state());
  assert.deepEqual(
    result.players.map((player) => [
      player.id,
      player.selected,
      player.actual,
      player.verdict,
      player.mood,
    ]),
    [
      ["a", true, true, "Correct", "celebrating"],
      ["b", false, true, "Wrong", "sad"],
      ["c", true, false, "Wrong", "sad"],
      ["d", false, false, "Correct", "celebrating"],
    ],
  );
  assert.equal(result.listenerCorrect, 2);
  assert.equal(result.listenerVerdict.label, "2 / 4 correct");
  assert.equal(result.points, 120);
  assert.equal(result.songVerdict.label, "Correct");
});

test("wrong-song and artist-only feedback use server classification independently of listener points", () => {
  const wrong = roundResult(state({ song_match: "wrong", points: 200 }));
  assert.equal(wrong.songVerdict.label, "Wrong");
  assert.equal(wrong.artistVerdict.label, "Wrong");
  assert.equal(wrong.points, 200);
  const partial = roundResult(state({ song_match: "artist", points: 75 }));
  assert.equal(partial.songVerdict.label, "Wrong");
  assert.equal(partial.artistVerdict.label, "Correct");
  assert.equal(partial.points, 75);
});

test("Nobody is an explicit submitted empty selection; missing answers get no invented correctness", () => {
  const decoy = state({ who_player_ids: [] });
  decoy.game.round.reveal.listener_ids = [];
  const nobody = roundResult(decoy);
  assert.equal(nobody.listenerVerdict.label, "4 / 4 correct");
  assert(
    nobody.players.every(
      (player) =>
        player.selection === "Not selected" && player.verdict === "Correct",
    ),
  );
  const missing = roundResult(
    state({
      status: "missing",
      song_guess: null,
      who_player_ids: null,
      points: 0,
      song_match: "unanswered",
    }),
  );
  assert.equal(missing.listenerVerdict.label, "No answer");
  assert.equal(missing.songVerdict.label, "No answer");
  assert.equal(missing.listenerCorrect, 0);
  assert(
    missing.players.every(
      (player) => player.correct === null && player.mood === "idle",
    ),
  );
  const listenerOnly = roundResult(
    state({ song_guess: null, song_match: "unanswered" }),
  );
  assert.equal(listenerOnly.songVerdict.label, "No guess");
  assert.equal(listenerOnly.listenerCorrect, 2);
});

test("reveal restores departed players from the frozen standings and ignores later identities", () => {
  const current = state();
  current.players = [
    { id: "a", nickname: "Changed", character_id: "sage" },
    { id: "outsider", nickname: "New" },
  ];
  assert.deepEqual(
    gamePlayers(current).map((player) => player.id),
    ["a", "b", "c", "d"],
  );
  assert.equal(gamePlayers(current)[0].nickname, "a");
  assert.equal(gamePlayers(current)[0].character_id, "coral");
  assert.equal(roundResult(current).listenerTotal, 4);
});

test("podium preserves server ranks and ties without changing the input or recalculating scores", () => {
  const rows = [
    { player_id: "d", rank: 4, score: 50 },
    { player_id: "a", rank: 1, score: 100 },
    { player_id: "b", rank: 1, score: 100 },
    { player_id: "c", rank: 3, score: 60 },
  ];
  const original = structuredClone(rows);
  const model = standingsModel(rows);
  assert.deepEqual(
    model.podium.map((player) => [player.player_id, player.rank]),
    [
      ["a", 1],
      ["b", 1],
      ["c", 3],
    ],
  );
  assert.deepEqual(
    model.remaining.map((player) => player.player_id),
    ["d"],
  );
  assert.deepEqual(rows, original);
  for (let count = 0; count < 3; count++)
    assert.equal(standingsModel(rows.slice(0, count)).podium.length, count);
});

test("result countdown catches up to the server deadline and labels the actual next phase", () => {
  const game = state().game;
  assert.deepEqual(phaseProgress(game, 22000), {
    seconds: 3,
    fraction: 0.6,
    label: "Leaderboard",
  });
  assert.deepEqual(phaseProgress(game, 26000), {
    seconds: 0,
    fraction: 0,
    label: "Leaderboard",
  });
  game.phase = "leaderboard";
  assert.equal(phaseProgress(game, 21000).label, "Next round");
  for (const status of ["completed", "aborted"])
    assert.equal(phaseProgress({ ...game, status }, 22000), null);
  assert.equal(phaseProgress({ ...game, phase_ends_at_ms: null }, 22000), null);
  assert.equal(roundResult({ game: null }), null);
});
