import type { ReviewComment } from "@/lib/types";

export interface CommentThread {
  comment: ReviewComment;
  replies: ReviewComment[];
}

/**
 * Group a flat, time-ordered comment list into one-level threads: each top-level
 * comment (no parent) with its replies (comments whose `parent` is that id). A
 * reply whose parent isn't present is treated as top-level so it's never dropped.
 * Input order is preserved (the API returns oldest-first).
 */
export function threadComments(comments: ReviewComment[]): CommentThread[] {
  const byId = new Set(comments.map((c) => c.id));
  const repliesByParent = new Map<string, ReviewComment[]>();
  for (const c of comments) {
    if (c.parent && byId.has(c.parent)) {
      const arr = repliesByParent.get(c.parent) ?? [];
      arr.push(c);
      repliesByParent.set(c.parent, arr);
    }
  }
  return comments
    .filter((c) => !c.parent || !byId.has(c.parent))
    .map((c) => ({ comment: c, replies: repliesByParent.get(c.id) ?? [] }));
}
