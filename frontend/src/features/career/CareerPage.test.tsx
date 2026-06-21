/**
 * Regression for BUG 3 — the employee dashboard advertised a Career Roadmap tile
 * but /career was gated at MANAGER, so an employee clicking it got "You do not have
 * access" (a dead link). The route gate is removed; CareerPage now gives employees
 * a READ-ONLY view of their OWN roadmap (no "My team" tab, no manage controls),
 * while managers keep the full experience. Scope is enforced server-side regardless.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let role = "EMPLOYEE";
const rank: Record<string, number> = { EMPLOYEE: 0, MANAGER: 1, HRBP: 2, ADMIN: 3 };
vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => ({
    me: { id: "u-1", role },
    atLeast: (min: string) => rank[role] >= rank[min],
    hasFeature: () => true,
  }),
}));

// The data hooks + target queries — return empty so the read-only empty state renders.
vi.mock("./useCareer", () => ({
  useMyRoadmaps: () => ({ data: { results: [] }, isLoading: false, isError: false }),
  useScopedRoadmaps: () => ({ data: { results: [] }, isLoading: false, isError: false }),
  useRoadmapProgress: () => ({ data: [] }),
  useSkillGap: () => ({ data: null }),
  useCareerMutations: () => ({
    selectTarget: { mutateAsync: vi.fn(), isPending: false },
    regenerate: { mutateAsync: vi.fn(), isPending: false },
    adopt: { mutateAsync: vi.fn(), isPending: false },
    setProgress: { mutateAsync: vi.fn() },
  }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  careerApi: { enrich: vi.fn() },
  jdApi: { list: vi.fn(() => Promise.resolve({ results: [] })) },
  orgApi: { positions: vi.fn(() => Promise.resolve({ results: [] })) },
}));

import { CareerPage } from "./CareerPage";

function renderAs(r: string) {
  role = r;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CareerPage />
    </QueryClientProvider>,
  );
}

describe("CareerPage access (BUG 3)", () => {
  it("employee gets a read-only OWN roadmap — no team tab, no target picker", () => {
    renderAs("EMPLOYEE");
    expect(screen.queryByText("My team")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /target role/i })).not.toBeInTheDocument();
    // The empty state speaks to read-only employees, not "choose a target".
    expect(screen.getByText(/your manager can set up/i)).toBeInTheDocument();
  });

  it("manager keeps the team tab + the target picker", () => {
    renderAs("MANAGER");
    expect(screen.getByText("My team")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /target role/i }).length).toBeGreaterThan(0);
  });
});
