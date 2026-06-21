import { describe, expect, it } from "vitest";
import { allChildrenLoaded, childrenOf, normalizeOrgTree } from "./org";
import type { OrgNode, RawOrgTree } from "@/lib/types";

const node = (id: string, extra: Partial<OrgNode> = {}): OrgNode => ({
  id,
  email: `${id}@acme.test`,
  display: id,
  role: "EMPLOYEE",
  headcount: 1,
  vacancies: 0,
  direct_report_ids: [],
  ...extra,
});

describe("normalizeOrgTree", () => {
  it("turns the node LIST into an id→node map", () => {
    const raw: RawOrgTree = { roots: ["a"], nodes: [node("a"), node("b")], edges: [] };
    const t = normalizeOrgTree(raw);
    expect(Array.isArray(t.nodes)).toBe(false);
    expect(t.nodes["a"].email).toBe("a@acme.test");
    expect(t.nodes["b"].display).toBe("b");
  });

  it("turns {from,to} edge objects into [from,to] tuples (the crash fix)", () => {
    const raw: RawOrgTree = {
      roots: ["a"],
      nodes: [node("a"), node("b")],
      edges: [{ from: "a", to: "b" }],
    };
    const t = normalizeOrgTree(raw);
    // Iterating + array-destructuring must not throw and must yield the tuple.
    for (const [parent, child] of t.edges) {
      expect(parent).toBe("a");
      expect(child).toBe("b");
    }
    expect(t.edges).toEqual([["a", "b"]]);
  });

  it("passes roots through", () => {
    const raw: RawOrgTree = { roots: ["a", "b"], nodes: [node("a"), node("b")], edges: [] };
    expect(normalizeOrgTree(raw).roots).toEqual(["a", "b"]);
  });

  it("is defensive: null/undefined payload → empty normalized tree", () => {
    for (const bad of [null, undefined]) {
      const t = normalizeOrgTree(bad);
      expect(t.nodes).toEqual({});
      expect(t.edges).toEqual([]);
      expect(t.roots).toEqual([]);
    }
  });

  it("is defensive: null arrays / null edge endpoints / id-less nodes are skipped", () => {
    const raw = {
      roots: null,
      nodes: [null, node("a"), { email: "x" }],
      edges: [{ from: null, to: "a" }, { from: "a", to: null }, { from: "a", to: "a" }],
    } as unknown as RawOrgTree;
    const t = normalizeOrgTree(raw);
    expect(Object.keys(t.nodes)).toEqual(["a"]); // null + id-less dropped
    expect(t.edges).toEqual([["a", "a"]]); // only the fully-populated edge survives
    expect(t.roots).toEqual([]);
  });
});

describe("lazy org tree helpers", () => {
  const nodes = {
    a: node("a", { direct_report_ids: ["b", "c"] }),
    b: node("b"), // b's children not loaded
    // c is referenced by a but NOT in the map (unfetched)
  };

  it("childrenOf returns only the loaded children", () => {
    expect(childrenOf("a", nodes).map((n) => n.id)).toEqual(["b"]); // c unfetched → skipped
    expect(childrenOf("b", nodes)).toEqual([]); // leaf
    expect(childrenOf("missing", nodes)).toEqual([]); // unknown id
  });

  it("allChildrenLoaded is false while a child is unfetched, true once present", () => {
    expect(allChildrenLoaded("a", nodes)).toBe(false); // c missing
    expect(allChildrenLoaded("b", nodes)).toBe(true); // no children → trivially loaded
    const full = { ...nodes, c: node("c") };
    expect(allChildrenLoaded("a", full)).toBe(true); // both b and c present
  });
});
