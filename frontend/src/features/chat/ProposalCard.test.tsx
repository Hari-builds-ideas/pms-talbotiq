/**
 * RW_BUILD_4/5 — the chat assistant's propose-and-confirm card. The proposal is
 * INERT until Approve (which calls the execute endpoint; the server re-checks
 * permission + scope). The card is ACTION-AWARE: approve_goals vs approve_reviews
 * change the preview, the success line, and which query is invalidated. No live calls.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";

const executeAction = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: { executeAction: (...a: unknown[]) => executeAction(...a) },
}));

beforeEach(() => executeAction.mockClear());

import { ProposalCard } from "./ProposalCard";
import type { ChatProposal } from "@/lib/types";

function renderCard(proposal: ChatProposal) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProposalCard proposal={proposal} />
    </QueryClientProvider>,
  );
}

const GOALS_PROPOSAL: ChatProposal = {
  action: "approve_goals",
  summary: "Approve 2 pending goal(s) for your team?",
  preview: [
    { goal: "Ship onboarding", employee: "Reza" },
    { goal: "Cut latency", employee: "Mia" },
  ],
  params: { goal_ids: ["g1", "g2"] },
};

const REVIEWS_PROPOSAL: ChatProposal = {
  action: "approve_reviews",
  summary: "Approve 1 review(s) pending your sign-off?",
  preview: [{ employee: "Reza Pahlavi" }],
  params: { review_ids: ["r1"] },
};

describe("ProposalCard", () => {
  it("approve_goals → executes the action and reports goals approved", async () => {
    executeAction.mockResolvedValue({ action: "approve_goals", approved: 2, skipped: [] });
    renderCard(GOALS_PROPOSAL);
    expect(screen.getByText("Ship onboarding")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Approved 2 goals.")).toBeInTheDocument();
    expect(executeAction).toHaveBeenCalledWith("approve_goals", { goal_ids: ["g1", "g2"] });
  });

  it("approve_reviews → action-aware noun + shows the employee preview", async () => {
    executeAction.mockResolvedValue({ action: "approve_reviews", approved: 1, skipped: [{ reason: "x" }] });
    renderCard(REVIEWS_PROPOSAL);
    expect(screen.getByText("Reza Pahlavi")).toBeInTheDocument(); // preview has no goal, just the person
    await userEvent.setup().click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Approved 1 review, skipped 1.")).toBeInTheDocument();
    expect(executeAction).toHaveBeenCalledWith("approve_reviews", { review_ids: ["r1"] });
  });

  it("Cancel is inert — nothing executes", async () => {
    renderCard(REVIEWS_PROPOSAL);
    await userEvent.setup().click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText(/Cancelled — nothing was changed/i)).toBeInTheDocument();
    expect(executeAction).not.toHaveBeenCalled();
  });
});
