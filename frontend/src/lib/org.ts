import type { OrgNode, OrgTree, RawOrgTree } from "@/lib/types";

/**
 * Normalize the raw `GET /api/org/tree` payload into the shape the tree
 * components consume.
 *
 * The API returns `nodes` as a LIST of node objects and `edges` as `{from,to}`
 * objects (manager→report); the components want an id→node map and `[from,to]`
 * tuples. Doing this at the boundary (rather than inside the render) is what
 * keeps `OrgTreeView` simple — and it fixes the "not iterable" crash that came
 * from array-destructuring `{from,to}` objects and indexing the node LIST by id.
 *
 * Defensive by design: a missing/null payload, null arrays, a node without an
 * id, or an edge with a null endpoint are all skipped rather than thrown on, so
 * an empty or partial tree renders as empty instead of crashing.
 */
export function normalizeOrgTree(raw: RawOrgTree | null | undefined): OrgTree {
  const nodes: Record<string, OrgTree["nodes"][string]> = {};
  for (const n of raw?.nodes ?? []) {
    if (n && n.id) nodes[n.id] = n;
  }

  const edges: Array<[string, string]> = [];
  for (const e of raw?.edges ?? []) {
    if (e && e.from && e.to) edges.push([e.from, e.to]);
  }

  const roots = (raw?.roots ?? []).filter(Boolean);

  return { nodes, edges, roots };
}

/** The set of ids AT OR BELOW `rootId` in the reporting tree (self + all reports,
 *  transitively), walked over `direct_report_ids`. Used to scope "who can I create a
 *  goal for" to a manager's own line — mirroring the server's TEAM-scope rule
 *  (`actor_can_access`: self + reporting subtree). `rootId` is always included. */
export function subtreeIds(rootId: string, nodes: Record<string, OrgNode>): Set<string> {
  const out = new Set<string>();
  const stack = [rootId];
  while (stack.length) {
    const id = stack.pop() as string;
    if (out.has(id)) continue;
    out.add(id);
    for (const cid of nodes[id]?.direct_report_ids ?? []) {
      if (!out.has(cid)) stack.push(cid);
    }
  }
  return out;
}

/** The loaded children of a node (its `direct_report_ids` that are present in the
 *  node map). Used by the lazy org tree to render a node's expanded children. */
export function childrenOf(id: string, nodes: Record<string, OrgNode>): OrgNode[] {
  return (nodes[id]?.direct_report_ids ?? [])
    .map((cid) => nodes[cid])
    .filter((n): n is OrgNode => Boolean(n));
}

/** True when every one of a node's `direct_report_ids` is already in the map —
 *  i.e. expanding it needs no further fetch. A node with no children is trivially
 *  "loaded". */
export function allChildrenLoaded(id: string, nodes: Record<string, OrgNode>): boolean {
  return (nodes[id]?.direct_report_ids ?? []).every((cid) => cid in nodes);
}
