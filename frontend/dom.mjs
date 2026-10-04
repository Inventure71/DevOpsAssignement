// Shared DOM helpers keep user-provided text out of HTML interpolation.
export function element(markup) {
  const template = document.createElement("template");
  template.innerHTML = markup.trim();
  return template.content.firstElementChild;
}
export function text(node, value) {
  const next = String(value ?? "");
  if (node.textContent !== next) node.textContent = next;
}
/** Keep keyed children in order without replacing live component instances. */
export function syncKeyedChildren(
  container,
  values,
  nodes,
  { key, create, update },
) {
  syncKeyedGroups([{ container, values }], nodes, { key, create, update });
}

/** Reconcile related columns with one identity cache, retaining moved sprites. */
export function syncKeyedGroups(groups, nodes, { key, create, update }) {
  const active = new Set(groups.flatMap(({ values }) => values.map(key)));
  for (const [id, node] of nodes) {
    if (!active.has(id)) {
      node.remove();
      nodes.delete(id);
    }
  }
  for (const { container, values } of groups) {
    values.forEach((value, index) => {
      const id = key(value);
      let node = nodes.get(id);
      if (!node) {
        node = create(value);
        nodes.set(id, node);
      }
      update(node, value);
      if (container.children[index] !== node)
        container.insertBefore(node, container.children[index] ?? null);
    });
  }
}
