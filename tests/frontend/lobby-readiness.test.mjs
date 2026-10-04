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
  ];
}

test("lobby start eligibility requires the host, enough songs and players, and a ready connection", () => {
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
  const [state, ui] = ready();
  state.players[1].song_count = 4;
  assert.match(startReadiness(state, ui).reason, /B has fewer/);
  state.players[2].song_count = 6;
  assert.match(startReadiness(state, ui).reason, /B, C have fewer/);
  state.players.forEach((player) => {
    player.song_count = 10;
  });
  ui.pending = "start";
  assert.deepEqual(startReadiness(state, ui), {
    canStart: false,
    blocker: "pending",
    reason: "Starting…",
  });
});

test("two-player playtests use the server minimum and still require songs", () => {
  const [state, ui] = ready();
  state.room = { minimum_players: 2, playtest: true };
  state.players.pop();
  assert.equal(startReadiness(state, ui).canStart, true);
  state.players[1].song_count = 9;
  assert.match(startReadiness(state, ui).reason, /10 songs/);
  state.players.pop();
  assert.equal(startReadiness(state, ui).reason, "At least 2 players are needed to start.");
  state.room.minimum_players = 3;
  assert.equal(startReadiness(state, ui).reason, "At least 3 players are needed to start.");
});
