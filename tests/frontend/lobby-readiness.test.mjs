import test from "node:test";
import assert from "node:assert/strict";
import { startReadiness } from "../../frontend/game/lobby-readiness.mjs";

function ready() {
  return [
    {
      me: { is_host: true },
      players: ["A", "B", "C"].map((nickname) => ({
        nickname,
        song_count: 10,
      })),
    },
    {},
    { unlocked: true, leaseId: "lease" },
  ];
}

test("only the host with enough songs, players, shared audio and a ready connection can start", () => {
  assert.equal(startReadiness(...ready()).canStart, true);
  for (const alter of [
    ([state]) => {
      state.me.is_host = false;
    },
    ([state]) => {
      state.players.pop();
    },
    ([state]) => {
      state.players[1].song_count = 9;
    },
    ([, , audio]) => {
      audio.unlocked = false;
    },
    ([, , audio]) => {
      audio.leaseId = null;
    },
    ([, ui]) => {
      ui.disconnected = true;
    },
    ([, ui]) => {
      ui.pending = "setting";
    },
  ]) {
    const args = ready();
    alter(args);
    const result = startReadiness(...args);
    assert.equal(result.canStart, false);
    assert.notEqual(result.reason, startReadiness(...ready()).reason);
  }
});

test("readiness explains named shortages and pending start rather than claiming readiness", () => {
  const [state, ui, audio] = ready();
  state.players[1].song_count = 4;
  assert.match(startReadiness(state, ui, audio).reason, /B has fewer/);
  state.players[2].song_count = 6;
  assert.match(startReadiness(state, ui, audio).reason, /B, C have fewer/);
  state.players.forEach((player) => {
    player.song_count = 10;
  });
  ui.pending = "start";
  assert.deepEqual(startReadiness(state, ui, audio), {
    canStart: false,
    reason: "Starting…",
  });
});

test("two-player playtests use the server minimum and still require songs and shared audio", () => {
  const [state, ui, audio] = ready();
  state.room = { minimum_players: 2, playtest: true };
  state.players.pop();
  assert.equal(startReadiness(state, ui, audio).canStart, true);
  audio.unlocked = false;
  assert.match(startReadiness(state, ui, audio).reason, /Enable shared audio/);
  audio.unlocked = true;
  state.players[1].song_count = 9;
  assert.match(startReadiness(state, ui, audio).reason, /10 songs/);
  state.players.pop();
  assert.equal(startReadiness(state, ui, audio).reason, "At least 2 players are needed to start.");
  state.room.minimum_players = 3;
  assert.equal(startReadiness(state, ui, audio).reason, "At least 3 players are needed to start.");
});
