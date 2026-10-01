import test from "node:test";
import assert from "node:assert/strict";
import { syncKeyedChildren, syncKeyedGroups } from "../../frontend/dom.mjs";

// Model only DOM node movement: inserting an existing node reparents it.
function container() {
  return {
    children: [],
    insertBefore(node, reference) {
      node.remove();
      const position = reference
        ? this.children.indexOf(reference)
        : this.children.length;
      assert.notEqual(position, -1);
      this.children.splice(position, 0, node);
      node.parent = this;
    },
  };
}
const identity = {
  key: (value) => value.id,
  create: () => ({
    parent: null,
    remove() {
      if (this.parent) {
        this.parent.children.splice(this.parent.children.indexOf(this), 1);
        this.parent = null;
      }
    },
  }),
  update: (node, value) => {
    node.name = value.name;
  },
};
const value = (id, name = id) => ({ id, name });

test("keyed updates retain nodes when reordered or moved between roster columns", () => {
  const left = container(),
    right = container(),
    nodes = new Map();
  const update = (a, b) =>
    syncKeyedGroups(
      [
        { container: left, values: a },
        { container: right, values: b },
      ],
      nodes,
      identity,
    );
  update([value("a"), value("b")], [value("c"), value("d")]);
  const original = new Map(nodes);
  original.get("b").draft = "retained draft";
  update([value("d"), value("a", "Renamed")], [value("b"), value("c")]);
  assert.deepEqual(left.children, [original.get("d"), original.get("a")]);
  assert.deepEqual(right.children, [original.get("b"), original.get("c")]);
  assert.equal(nodes.get("b").draft, "retained draft");
  assert.equal(nodes.get("a").name, "Renamed");
  update([value("a")], [value("c")]);
  assert.equal(original.get("b").parent, null);
  assert.equal(original.get("d").parent, null);
  assert.equal(nodes.size, 2);
});

test("single lists use the same identity cache and empty rosters release all nodes", () => {
  const root = container(),
    nodes = new Map();
  syncKeyedChildren(root, [value("a")], nodes, identity);
  const retained = nodes.get("a");
  syncKeyedChildren(root, [value("a", "Updated"), value("b")], nodes, identity);
  assert.equal(root.children[0], retained);
  assert.equal(retained.name, "Updated");
  syncKeyedChildren(root, [], nodes, identity);
  assert.equal(nodes.size, 0);
  assert.deepEqual(root.children, []);
});
