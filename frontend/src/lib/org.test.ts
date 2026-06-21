import { describe, expect, it } from "vitest";
import { normalizeOrgTree } from "./org";
import type { OrgNode, RawOrgTree } from "@/lib/types";

const node = (id: string, extra: Partial<OrgNode> = {}): OrgNode => ({
  id,
  email: `${id}@acme.test`,
  display: id,
  role: "EMPLOYEE",
  headcount: 1,
  vacancies: 0,
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
