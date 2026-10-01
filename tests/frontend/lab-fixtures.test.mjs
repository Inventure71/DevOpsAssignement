import test from "node:test";
import assert from "node:assert/strict";
import { BLOB_COLORS } from "../../frontend/components/blob-palette.mjs";
import {
  createLabState,
  createLabUi,
  createRoundFixture,
} from "../../frontend/lab/fixtures.mjs";

function fixture(query = "", scene = "reveal") {
  const state = createLabState(1000);
  return createRoundFixture({
    scene,
    state,
    ui: createLabUi(),
    now: 1000,
    levels: [0, 1],
    params: new URLSearchParams(query),
  });
}

test("reveal fixtures expose only the current player's answer, including edge cases", () => {
  for (const query of [
    "",
    "wrong-answer",
    "missing-answer",
    "artist-only",
    "nobody",
  ]) {
    const reveal = fixture(query).round.reveal;
    assert.deepEqual(Object.keys(reveal).sort(), [
      "listener_ids",
      "my_answer",
      "song",
    ]);
    assert.equal(reveal.my_answer.player_id, "lab-0");
    assert.equal("answers" in reveal, false);
  }
  assert.equal(
    fixture("wrong-answer").round.reveal.my_answer.song_match,
    "wrong",
  );
  assert.equal(
    fixture("missing-answer").round.reveal.my_answer.status,
    "missing",
  );
  assert.equal(
    fixture("missing-answer").round.reveal.my_answer.song_guess,
    null,
  );
  assert.equal(
    fixture("artist-only").round.reveal.my_answer.song_match,
    "artist",
  );
  assert.equal(fixture("artist-only").round.reveal.my_answer.points, 50);
  for (const query of ["missing-answer", "missing-answer&nobody"]) {
    assert.equal(fixture(query).round.reveal.my_answer.who_player_ids, null);
    assert.equal(fixture(query).round.reveal.my_answer.status, "missing");
  }
  assert.deepEqual(fixture("nobody").round.reveal.listener_ids, []);
  assert.deepEqual(fixture("nobody").round.reveal.my_answer.who_player_ids, []);
});

test("separate lab sessions own their player identities and mutable selections", () => {
  const first = createLabState(1000),
    second = createLabState(2000);
  assert.deepEqual(
    first.players.map((player) => player.character_id),
    BLOB_COLORS.map((color) => color.id),
  );
  assert.equal(first.me, first.players[0]);
  first.me.character_id = "rose";
  assert.equal(second.me.character_id, "coral");
  const firstUi = createLabUi(),
    secondUi = createLabUi();
  firstUi.listeners.clear();
  assert.equal(secondUi.listeners.size, 3);
});

test("submitted, missing artwork and tied ranks remain independently reproducible", () => {
  const submitted = fixture("", "submitted");
  assert.equal(submitted.phase, "setup");
  assert.ok(submitted.round.my_answer);
  assert.ok(submitted.round.submitted_player_ids.includes("lab-0"));
  const leaderboard = fixture("broken-artwork&tied-ranks", "leaderboard");
  assert.equal(leaderboard.phase, "leaderboard");
  assert.equal(
    leaderboard.round.reveal.song.artwork_url,
    "/ui/missing-lab-cover.png",
  );
  assert.equal(
    leaderboard.leaderboard[0].score,
    leaderboard.leaderboard[1].score,
  );
  assert.equal(leaderboard.leaderboard[1].rank, 1);
});
