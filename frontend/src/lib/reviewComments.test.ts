import { describe, expect, it } from "vitest";
import { threadComments } from "./reviewComments";
import type { ReviewComment } from "@/lib/types";

const c = (id: string, parent: string | null = null): ReviewComment => ({
  id,
  author: "u1",
  author_name: "U One",
  section: null,
  body: id,
  parent,
  created_at: "2026-01-01T00:00:00Z",
  edited_at: null,
});

describe("threadComments", () => {
  it("groups replies under their top-level parent, preserving order", () => {
    const threads = threadComments([c("a"), c("b"), c("a1", "a"), c("a2", "a")]);
    expect(threads.map((t) => t.comment.id)).toEqual(["a", "b"]);
    expect(threads[0].replies.map((r) => r.id)).toEqual(["a1", "a2"]);
    expect(threads[1].replies).toEqual([]);
  });

  it("treats a reply whose parent is absent as top-level (never dropped)", () => {
    const threads = threadComments([c("orphan", "missing-parent")]);
    expect(threads.map((t) => t.comment.id)).toEqual(["orphan"]);
    expect(threads[0].replies).toEqual([]);
  });

  it("returns [] for no comments", () => {
    expect(threadComments([])).toEqual([]);
  });
});
