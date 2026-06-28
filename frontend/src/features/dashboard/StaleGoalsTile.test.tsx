/**
 * RW_BUILD_5 quick win #3 — the manager/HR stale-goals tile lists ACTIVE goals with
 * no recent progress (with staleness) and shows the advisory AI follow-up suggestion.
 * READ-ONLY; resilient when the suggestion is null. No live calls (aiApi mocked).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

const staleGoals = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: { staleGoals: (...a: unknown[]) => staleGoals(...a) },
}));

import { StaleGoalsTile } from "./tiles";

function renderTile() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StaleGoalsTile />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StaleGoalsTile", () => {
  it("lists stale goals with their staleness + the advisory AI suggestion", async () => {
    staleGoals.mockResolvedValue({
      stale: [
        { goal: "Ship onboarding revamp", employee: "Reza Pahlavi", days_stale: 41 },
        { goal: "Reduce p95 latency", employee: "Mia Fontaine", days_stale: null },
      ],
      suggestion: "Book a focused check-in on the onboarding revamp with Reza and agree one next step.",
    });
    renderTile();
    expect(await screen.findByText("Ship onboarding revamp")).toBeInTheDocument();
    expect(screen.getByText("41d stale")).toBeInTheDocument();
    expect(screen.getByText("no progress yet")).toBeInTheDocument(); // null days_stale
    expect(screen.getByText("Reza Pahlavi")).toBeInTheDocument();
    expect(screen.getByText(/Book a focused check-in/i)).toBeInTheDocument();
  });

  it("shows a clean empty state when nothing is stale", async () => {
    staleGoals.mockResolvedValue({ stale: [], suggestion: null });
    renderTile();
    expect(await screen.findByText("No stale goals")).toBeInTheDocument();
  });

  it("still lists the goals when the AI suggestion is null (resilient)", async () => {
    staleGoals.mockResolvedValue({
      stale: [{ goal: "Improve test coverage", employee: "Sam Okafor", days_stale: 33 }],
      suggestion: null,
    });
    renderTile();
    expect(await screen.findByText("Improve test coverage")).toBeInTheDocument();
    expect(screen.queryByText(/Suggested follow-up/i)).toBeNull();
  });
});
