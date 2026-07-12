import { describe, expect, it } from "vitest";
import { visibleReviewActions } from "./ReviewDetailPage";

// D2: every review transition control is gated by the server-provided capability
// grants. An EMPLOYEE (no manage/approve/finalize/aiDraft) must see NO buttons in
// ANY state — a clean read-only page instead of 403 walls (the #1 complaint).
const EMPLOYEE = { manage: false, approve: false, finalize: false, aiDraft: false };
const MANAGER = { manage: true, approve: true, finalize: true, aiDraft: true };

describe("visibleReviewActions (capability-gated ActionBar)", () => {
  it("EMPLOYEE sees no action in any state (no visible-but-unauthorized)", () => {
    for (const state of ["DRAFT", "PENDING_HUMAN_REVIEW", "APPROVED", "REJECTED", "EDITING"]) {
      expect(visibleReviewActions(state, EMPLOYEE)).toEqual([]);
    }
  });

  it("MANAGER sees the state-appropriate actions", () => {
    expect(visibleReviewActions("DRAFT", MANAGER)).toEqual(["ai", "start-edit"]);
    expect(visibleReviewActions("PENDING_HUMAN_REVIEW", MANAGER)).toEqual(["edit", "reject", "approve"]);
    expect(visibleReviewActions("APPROVED", MANAGER)).toEqual(["finalize"]);
    expect(visibleReviewActions("REJECTED", MANAGER)).toEqual(["revise"]);
  });

  it("capabilities gate independently (e.g. manage without approve)", () => {
    const draftsOnly = { manage: true, approve: false, finalize: false, aiDraft: false };
    expect(visibleReviewActions("DRAFT", draftsOnly)).toEqual(["start-edit"]);
    expect(visibleReviewActions("PENDING_HUMAN_REVIEW", draftsOnly)).toEqual(["edit"]);
    expect(visibleReviewActions("APPROVED", draftsOnly)).toEqual([]);
  });

  it("unknown/terminal states expose nothing", () => {
    expect(visibleReviewActions("FINALIZED", MANAGER)).toEqual([]);
    expect(visibleReviewActions("AI_DRAFTING", MANAGER)).toEqual([]);
  });
});
