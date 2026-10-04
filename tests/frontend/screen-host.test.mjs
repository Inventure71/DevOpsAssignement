import test from "node:test";
import assert from "node:assert/strict";
import {
  createScreenHost,
  screenKey,
} from "../../frontend/application/screen-host.mjs";

const model = (phase = "answering", round = "first") => ({
  ui: { page: "play", roomId: "room" },
  state: {
    room: { id: "room" },
    game: { id: "game", status: "playing", phase, round: { id: round } },
  },
});

test("screen identity follows navigation, restoration, dismissed games and round boundaries", () => {
  assert.equal(screenKey({ ui: { page: "about" } }), "info:about");
  assert.equal(
    screenKey({ ui: { page: "play", historyOpen: true } }),
    "history",
  );
  assert.equal(screenKey({ ui: { page: "play" } }), "entry");
  assert.equal(
    screenKey({ ui: { page: "play", roomId: "room" } }),
    "restoring",
  );
  const dismissed = model();
  dismissed.ui.dismissedGame = "game";
  assert.equal(screenKey(dismissed), "lobby:room");
  for (const status of ["completed", "aborted"]) {
    const finished = model();
    finished.state.game.status = status;
    assert.equal(screenKey(finished), "results:game");
  }
  assert.notEqual(screenKey(model()), screenKey(model("answering", "second")));
});

test("polling updates retained screens; transitions destroy once and forward server-clock ticks", () => {
  let mounts = 0,
    created = 0;
  const instances = [];
  const root = {
    replaceChildren() {
      mounts++;
    },
  };
  const factory = () => {
    const instance = {
      element: {},
      updates: 0,
      destroyed: 0,
      ticks: [],
      update() {
        this.updates++;
      },
      tick(now) {
        this.ticks.push(now);
      },
      destroy() {
        this.destroyed++;
      },
    };
    created++;
    instances.push(instance);
    return instance;
  };
  const host = createScreenHost(root, { round: factory, results: factory });
  host.update(model());
  host.update(model());
  assert.equal(created, 1);
  assert.equal(mounts, 1);
  assert.equal(instances[0].updates, 2);
  host.tick(12000);
  assert.deepEqual(instances[0].ticks, [12000]);
  host.update(model("reveal"));
  host.update(model("leaderboard"));
  assert.equal(created, 2);
  assert.equal(instances[0].destroyed, 1);
  assert.equal(instances[1].updates, 2);
  host.update(model("answering", "second"));
  assert.equal(instances[1].destroyed, 1);
  host.destroy();
  host.destroy();
  assert.equal(instances[2].destroyed, 1);
  assert.equal(host.animated, false);
  host.tick(99999);
  assert.deepEqual(instances[2].ticks, []);
});
