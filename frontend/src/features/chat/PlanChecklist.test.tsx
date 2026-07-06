/**
 * AGENT_UX_V3 §B–E — the agent plan checklist. A plan is INERT: rendering it executes
 * nothing; each Approve calls approveStep (server re-checks capability + scope). "Approve
 * all & run" orchestrates the SAME endpoint sequentially and STOPS on a failure. Executed
 * steps show a result card; async drafts poll the shared job endpoint. No live calls.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";

const approveStep = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: { approveStep: (...a: unknown[]) => approveStep(...a) },
  aiJobsApi: { get: vi.fn() },
}));

beforeEach(() => approveStep.mockClear());

import { PlanChecklist } from "./PlanChecklist";
import type { ChatPlan, ChatPlanStep } from "@/lib/types";

const STEP = (id: string, action: string, reason: string): ChatPlanStep => ({
  id, ordinal: 0, action, feel: "confirm",
  summary: `${action} for Rhea?`, reason, preview: [{ employee: "Rhea" }], status: "pending",
});

const PLAN: ChatPlan = {
  id: "p1", session: "s1", message: "start a 360 for Rhea and draft her review",
  summary: "Planned two steps for your approval.",
  steps: [
    STEP("st1", "initiate_360", "Rhea is on your team, so you can open a 360."),
    STEP("st2", "draft_review", "Rhea's review is in DRAFT and in your scope."),
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

const doneResult = (stepId: string, message: string) => ({
  plan_id: "p1", step_id: stepId, action: "initiate_360", feel: "confirm", ordinal: 0,
  out_of_order: false, status: "done", result: { message },
});

describe("PlanChecklist", () => {
  it("renders the ordered steps and executes nothing on render", () => {
    renderPlan(PLAN);
    expect(screen.getByText("Start 360")).toBeInTheDocument();
    expect(screen.getByText("Draft review")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Approve" })).toHaveLength(2); // per-step
    expect(approveStep).not.toHaveBeenCalled(); // INERT
  });

  it("approving ONE step calls approveStep for that step and invalidates its query", async () => {
    approveStep.mockResolvedValue(doneResult("st1", "360 cycle created for Rhea."));
    const { qc } = renderPlan(PLAN);
    const spy = vi.spyOn(qc, "invalidateQueries");
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Approve" })[0]);
    expect(approveStep).toHaveBeenCalledWith("p1", "st1"); // exactly that step
    expect(await screen.findByText(/360 cycle created for Rhea/i)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith({ queryKey: ["feedback"] });
  });

  it("shows a result card with an Open link when the step returns an artifact (§B)", async () => {
    approveStep.mockResolvedValue({
      ...doneResult("st1", "done"),
      result: { message: "done", artifact: { type: "feedback_cycle", id: "c1", title: "360 — Rhea", state: "DRAFT", deeplink: "/feedback" } },
    });
    renderPlan(PLAN);
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Approve" })[0]);
    expect(await screen.findByText("360 — Rhea")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open/i })).toBeInTheDocument();
  });

  it("Approve all & run executes steps sequentially and STOPS at a failure (§D)", async () => {
    const plan3: ChatPlan = {
      ...PLAN,
      steps: [
        STEP("st1", "initiate_360", "r1"),
        STEP("st2", "draft_review", "r2"),
        STEP("st3", "give_recognition", "r3"),
      ],
    };
    approveStep.mockImplementation((_p: string, stepId: string) =>
      stepId === "st2" ? Promise.reject(new Error("nope")) : Promise.resolve(doneResult(stepId, "done")),
    );
    renderPlan(plan3);
    await userEvent.setup().click(screen.getByRole("button", { name: /Approve all & run/i }));
    await waitFor(() => expect(approveStep).toHaveBeenCalledWith("p1", "st2"));
    expect(approveStep).toHaveBeenCalledWith("p1", "st1");
    expect(approveStep).not.toHaveBeenCalledWith("p1", "st3"); // run stopped at the failure
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
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});
