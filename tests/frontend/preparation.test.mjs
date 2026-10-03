import test from "node:test";
import assert from "node:assert/strict";
import { musicPreparation, roundPreparation } from "../../frontend/game/preparation.mjs";

test("music preparation separates busy, offline retry and failed sign-in recovery", () => {
  for (const status of ["pending", "processing"]) {
    const progress = musicPreparation({ status, message: "Loaded 20/60 provider candidates" });
    assert.equal(progress.busy, true);
    assert.equal(progress.retry, false);
    assert.equal(progress.back, false);
    assert.doesNotMatch(progress.message, /20|60|provider|candidate/);
  }
  assert.match(musicPreparation({ reconnecting: true }).message, /Reconnecting/);
  const interrupted = musicPreparation({ status: "interrupted" });
  assert.equal(interrupted.busy, false);
  assert.equal(interrupted.retry, true);
  assert.match(interrupted.message, /connection/);
  const denied = musicPreparation({ status: "failed", error: { code: "music_authorization_denied" } });
  assert.equal(denied.back, true);
  assert.match(denied.message, /cancelled/);
  assert.match(musicPreparation({ status: "failed", error: { code: "music_account_taken" } }).message, /another account/);
  assert.match(musicPreparation({ status: "failed", error: { code: "music_admission_expired" } }).message, /expired/);
});

test("insufficient history stays actionable without revealing candidate/resolver diagnostics", () => {
  const result = musicPreparation({ status: "failed", error: {
    code: "insufficient_playable_songs", details: { candidate_count: 60, playable_count: 4 },
  } });
  assert.match(result.message, /at least 10 songs/);
  assert.match(result.message, /another Spotify account or play the demo/);
  assert.doesNotMatch(result.message, /60|4|candidate|resolver/);
  const unknown = musicPreparation({ status: "failed", error: { message: "Apple JWT invalid, worker quota 60" } });
  assert.doesNotMatch(unknown.message, /Apple|JWT|worker|quota|60/);
});

test("host and guest preparation give distinct next steps and omit clip counts", () => {
  const game = { phase: "setup", preparation: { checked: 32, total: 60 } };
  assert.match(roundPreparation(game, [], 0, true).message, /Keep this screen open/);
  assert.match(roundPreparation(game, [], 0, false).message, /host/);
  assert.doesNotMatch(roundPreparation(game, [], 0, true).message, /32|60|clip/);
  game.phase = "ready";
  game.round = { readiness_deadline_at_ms: 1000 };
  game.missing_player_ids = ["guest"];
  const players = [{ id: "guest", nickname: "Jules" }];
  assert.match(roundPreparation(game, players, 999, true).message, /Jules/);
  assert.match(roundPreparation(game, players, 1000, true).message, /Retry or continue/);
  assert.match(roundPreparation(game, players, 1000, false).message, /host/);
  game.phase = "answering";
  assert.equal(roundPreparation(game, players, 1100, true), null);
});
