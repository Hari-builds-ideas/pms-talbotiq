/**
 * RW_BUILD_3 — the check-ins page is role-aware: everyone gets "My check-ins" with
 * the weekly form; only a manager gets the "My team" tab (the server independently
 * scopes the team feed). Asserts the tab surface per role + the form renders.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const auth = vi.hoisted(() => ({ isManager: false }));
vi.mock("@/lib/auth/AuthContext", () => ({
  // atLeast("MANAGER") -> the toggle; any lower role check -> true.
  useAuth: () => ({ atLeast: (r: string) => (r === "MANAGER" ? auth.isManager : true) }),
}));
vi.mock("./useCheckins", () => ({
  useMyCheckins: () => ({ data: [], isLoading: false, isError: false, refetch: () => {} }),
  useTeamCheckins: () => ({ data: [], isLoading: false, isError: false, refetch: () => {} }),
  useCheckinMutations: () => ({
    save: { mutateAsync: vi.fn(), isPending: false },
    respond: { mutateAsync: vi.fn(), isPending: false },
  }),
  mondayOf: () => "2026-06-22",
}));
const meetingSummary = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: { meetingSummary: (...a: unknown[]) => meetingSummary(...a) },
}));

import { CheckInsPage } from "./CheckInsPage";

describe("CheckInsPage", () => {
  it("an employee sees My check-ins + the weekly form, but not the team tab", () => {
    auth.isManager = false;
    render(<CheckInsPage />);
    expect(screen.getByRole("tab", { name: "My check-ins" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "My team" })).toBeNull();
    expect(screen.getByLabelText("Mood 3")).toBeInTheDocument(); // the weekly form
    expect(screen.getByRole("button", { name: /Share check-in/i })).toBeInTheDocument();
  });

  it("a manager additionally gets the My team tab", () => {
    auth.isManager = true;
    render(<CheckInsPage />);
    expect(screen.getByRole("tab", { name: "My check-ins" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "My team" })).toBeInTheDocument();
  });

  // RW_BUILD_5 quick win #1 wiring: the AI meeting-summary card lives only in the
  // manager "My team" tab (never shown to employees) and renders the draft summary
  // + action items returned by the endpoint. Persists nothing — it's HITL.
  it("manager can summarise notes with AI — shows the draft summary + action items", async () => {
    auth.isManager = true;
    meetingSummary.mockResolvedValue({
      status: "ok",
      summary: { summary: "Aligned on Q3 priorities.", action_items: ["Escalate the design review"] },
      confidence: 0.9,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <CheckInsPage />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "My team" }));
    await user.type(screen.getByLabelText("Meeting notes"), "1:1 with Ada about Q3");
    await user.click(screen.getByRole("button", { name: /Summarise with AI/i }));
    expect(await screen.findByText("Aligned on Q3 priorities.")).toBeInTheDocument();
    expect(screen.getByText("Escalate the design review")).toBeInTheDocument();
    expect(meetingSummary).toHaveBeenCalledWith("1:1 with Ada about Q3");
  });

  it("does not expose the AI summary card to employees", () => {
    auth.isManager = false;
    render(<CheckInsPage />);
    expect(screen.queryByRole("button", { name: /Summarise with AI/i })).toBeNull();
  });
});
