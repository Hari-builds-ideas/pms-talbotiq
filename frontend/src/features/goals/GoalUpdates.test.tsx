/**
 * The goal Updates timeline (AGENT_UX_V3 Part 2.3): lists progress notes from the
 * audited endpoint, honest empty state, and the owner can add one. No live calls.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const goalUpdates = vi.fn();
const addGoalUpdate = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  goalsApi: {
    goalUpdates: (...a: unknown[]) => goalUpdates(...a),
    addGoalUpdate: (...a: unknown[]) => addGoalUpdate(...a),
  },
}));
vi.mock("@/lib/toast", () => ({ notifySuccess: vi.fn(), notifyError: vi.fn() }));

beforeEach(() => {
  goalUpdates.mockReset();
  addGoalUpdate.mockReset();
});

import { GoalUpdates } from "./GoalUpdates";

function renderIt(canAdd: boolean) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <GoalUpdates goalId="g1" canAdd={canAdd} />
    </QueryClientProvider>,
  );
}

describe("GoalUpdates", () => {
  it("lists updates from the API with their author", async () => {
    goalUpdates.mockResolvedValue([
      { id: "u1", goal: "g1", text: "Shipped v2 of the pricing page.", author: "a", author_name: "Vera", created_at: "2026-07-01" },
    ]);
    renderIt(false);
    expect(await screen.findByText(/Shipped v2 of the pricing page/)).toBeInTheDocument();
    expect(screen.getByText(/Vera/)).toBeInTheDocument();
  });

  it("shows an honest empty state when there are none", async () => {
    goalUpdates.mockResolvedValue([]);
    renderIt(false);
    expect(await screen.findByText(/No updates yet/)).toBeInTheDocument();
  });

  it("the owner can add an update (posts to the audited endpoint)", async () => {
    goalUpdates.mockResolvedValue([]);
    addGoalUpdate.mockResolvedValue({ id: "u2", goal: "g1", text: "x", author: "a", author_name: "Me", created_at: "2026-07-02" });
    renderIt(true);
    await screen.findByText(/No updates yet/);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Add a goal update"), "Closed the migration.");
    await user.click(screen.getByRole("button", { name: /Add/i }));
    await waitFor(() => expect(addGoalUpdate).toHaveBeenCalledWith("g1", "Closed the migration."));
  });
});
