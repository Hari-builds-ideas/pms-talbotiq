/**
 * Regression for BUG 1 — Goals approve showed a success toast but the row stayed
 * "Awaiting approval". Root cause: the list query key normalizes the cycle to
 * "all" (`cycle ?? "all"`) but the post-mutation invalidation used a cycle-specific
 * key, so with no cycle selected the cached ["goals","list","all"] query was never
 * invalidated → no refetch → stale UI. The fix invalidates by the stable prefix.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/endpoints", () => ({
  goalsApi: {
    approve: vi.fn(() => Promise.resolve({ id: "g1", approved_by: "u-1" })),
    recordActual: vi.fn(() => Promise.resolve({})),
    create: vi.fn(() => Promise.resolve({})),
  },
  cyclesApi: { recompute: vi.fn(() => Promise.resolve({})), scores: vi.fn() },
}));

import { useGoalMutations } from "./useGoals";

function wrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useGoalMutations.refresh invalidation (BUG 1)", () => {
  it("invalidates the default no-cycle list after approve (cycle === undefined)", async () => {
    const qc = new QueryClient();
    // Seed the list exactly as useGoals caches it when no cycle is selected.
    qc.setQueryData(["goals", "list", "all"], { results: [] });
    expect(qc.getQueryState(["goals", "list", "all"])?.isInvalidated).toBe(false);

    const { result } = renderHook(() => useGoalMutations(undefined), {
      wrapper: wrapper(qc),
    });
    await act(async () => {
      await result.current.approve.mutateAsync("g1");
    });

    await waitFor(() =>
      expect(qc.getQueryState(["goals", "list", "all"])?.isInvalidated).toBe(true),
    );
  });

  it("also invalidates a cycle-specific list after approve", async () => {
    const qc = new QueryClient();
    qc.setQueryData(["goals", "list", "cy-1"], { results: [] });
    const { result } = renderHook(() => useGoalMutations("cy-1"), {
      wrapper: wrapper(qc),
    });
    await act(async () => {
      await result.current.approve.mutateAsync("g1");
    });
    await waitFor(() =>
      expect(qc.getQueryState(["goals", "list", "cy-1"])?.isInvalidated).toBe(true),
    );
  });
});
