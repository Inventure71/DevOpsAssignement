import test from "node:test";
import assert from "node:assert/strict";
import { createActions } from "../../frontend/application/actions.mjs";

function session(navigator, inviteUrl = "http://192.168.1.80:8000/?join=ABC123") {
  const notices = [];
  const action = createActions({
    model: { ui: { state: { room: { code: "ABC123", invite_url: inviteUrl } } } },
    transport: {},
    notice: (message) => notices.push(message),
    navigator,
  });
  return { action, notices };
}

test("Invite friends copies the server's LAN URL without consulting localhost", async () => {
  let copied;
  const { action, notices } = session({ clipboard: { writeText: async (value) => { copied = value; } } });
  await action("invite");
  assert.equal(copied, "http://192.168.1.80:8000/?join=ABC123");
  assert.deepEqual(notices, ["Invite link copied."]);
});

test("native sharing uses the same reachable invitation", async () => {
  let shared;
  const { action } = session({ share: async (value) => { shared = value; } });
  await action("share-room");
  assert.equal(shared.url, "http://192.168.1.80:8000/?join=ABC123");
});

test("an unavailable LAN address blocks link sharing but still permits copying the code", async () => {
  let copied;
  const { action, notices } = session({ clipboard: { writeText: async (value) => { copied = value; } } }, null);
  await action("invite");
  assert.equal(copied, undefined);
  assert.match(notices[0], /No network invite address/);
  await action("copy-code");
  assert.equal(copied, "ABC123");
});

test("when browser copy APIs fail, the notice contains the full invitation URL", async () => {
  let removed = false;
  const previous = globalThis.document;
  globalThis.document = {
    createElement: () => ({ style: {}, select() {}, remove() { removed = true; } }),
    body: { append() {} },
    execCommand: () => false,
  };
  try {
    const { action, notices } = session({});
    await action("invite");
    assert.equal(notices[0], "http://192.168.1.80:8000/?join=ABC123");
    assert.equal(removed, true);
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});
