/**
 * OVERNIGHT_A — the agent plan checklist. A plan is INERT: rendering it executes
 * nothing; each Approve calls approveStep (the server re-checks capability + scope).
 * Steps show a grounded reason (Explain), live status, and Skip. No live calls.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";

const approveStep = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: { approveStep: (...a: unknown[]) => approveStep(...a) },
}));

beforeEach(() => approveStep.mockClear());

import { PlanChecklist } from "./PlanChecklist";
import type { ChatPlan } from "@/lib/types";

const PLAN: ChatPlan = {
  id: "p1",
  session: "s1",
  message: "start a 360 for Rhea and draft her review",
  summary: "Planned two steps for your approval.",
  steps: [
    {
      id: "st1", ordinal: 0, action: "initiate_360", feel: "confirm",
      summary: "Start a 360 for Rhea?", reason: "Rhea is on your team, so you can open a 360.",
      preview: [{ employee: "Rhea" }], status: "pending",
    },
    {
      id: "st2", ordinal: 1, action: "draft_review", feel: "confirm",
      summary: "Draft an AI review for Rhea?", reason: "Rhea's review is in DRAFT and in your scope.",
      preview: [{ employee: "Rhea" }], status: "pending",
    },
  ],
  created_at: "2026-07-03T00:00:00Z",
};

function renderPlan(plan: ChatPlan) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  return { qc, ...render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><PlanChecklist plan={plan} /></MemoryRouter>
    </QueryClientProvider>,
  ) };
}

describe("PlanChecklist", () => {
  it("renders the ordered steps and executes nothing on render", () => {
    renderPlan(PLAN);
    expect(screen.getByText("Start 360")).toBeInTheDocument();
    expect(screen.getByText("Draft review")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Approve/i })).toHaveLength(2);
    expect(approveStep).not.toHaveBeenCalled(); // INERT
  });

  it("approving ONE step calls approveStep for that step and invalidates its query", async () => {
    approveStep.mockResolvedValue({
      plan_id: "p1", step_id: "st1", action: "initiate_360", feel: "confirm", ordinal: 0,
      out_of_order: false, status: "done", result: { message: "360 cycle created for Rhea." },
    });
    const { qc } = renderPlan(PLAN);
    const spy = vi.spyOn(qc, "invalidateQueries");
    await userEvent.setup().click(screen.getAllByRole("button", { name: /Approve/i })[0]);
    expect(approveStep).toHaveBeenCalledWith("p1", "st1"); // exactly that step
    expect(await screen.findByText(/360 cycle created for Rhea/i)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith({ queryKey: ["feedback"] });
  });

  it("Explain reveals the grounded reason", async () => {
    renderPlan(PLAN);
    expect(screen.queryByText(/Rhea is on your team/i)).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getAllByRole("button", { name: /Explain/i })[0]);
    expect(screen.getByText(/Rhea is on your team/i)).toBeInTheDocument();
  });

  it("Skip marks a step skipped without executing it", async () => {
    renderPlan(PLAN);
    await userEvent.setup().click(screen.getAllByRole("button", { name: /Skip/i })[0]);
    expect(screen.getByText("Skipped")).toBeInTheDocument();
    expect(approveStep).not.toHaveBeenCalled();
  });

  it("an empty plan shows the summary, not a checklist", () => {
    renderPlan({ ...PLAN, steps: [], summary: "Some steps couldn't be prepared." });
    expect(screen.getByText(/Some steps couldn't be prepared/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve/i })).not.toBeInTheDocument();
  });
});
