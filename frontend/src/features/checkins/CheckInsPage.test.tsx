/**
 * RW_BUILD_3 — the check-ins page is role-aware: everyone gets "My check-ins" with
 * the weekly form; only a manager gets the "My team" tab (the server independently
 * scopes the team feed). Asserts the tab surface per role + the form renders.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

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
});
