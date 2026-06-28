/**
 * RW_BUILD_5 quick win #2 — the AI review-quality check is ADVISORY: it renders the
 * flags as dismissable chips, never blocks, and degrades cleanly when the provider
 * is missing. The text reaches the endpoint verbatim. No live calls (aiApi mocked).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError } from "axios";
import { describe, it, expect, vi } from "vitest";

const reviewQuality = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  aiApi: { reviewQuality: (...a: unknown[]) => reviewQuality(...a) },
}));

function axiosErr(status: number) {
  const e = new AxiosError("fail");
  e.response = { status, data: {}, headers: {}, statusText: "", config: {} as never };
  return e;
}

import { ReviewQualityCheck } from "./ReviewQualityCheck";

function renderWith(text: string) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReviewQualityCheck text={text} />
    </QueryClientProvider>,
  );
}

describe("ReviewQualityCheck", () => {
  it("checks the draft text and renders advisory flags that can be dismissed", async () => {
    reviewQuality.mockResolvedValue({
      status: "ok",
      flags: [
        { type: "missing_evidence", note: "'strong delivery' isn't tied to a goal or metric." },
        { type: "recency_bias", note: "Examples are all from the last few weeks." },
      ],
    });
    renderWith("Reza had strong delivery this quarter.");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Check with AI/i }));

    expect(await screen.findByText(/isn't tied to a goal or metric/i)).toBeInTheDocument();
    expect(screen.getByText("Missing Evidence")).toBeInTheDocument();
    expect(screen.getByText("Recency Bias")).toBeInTheDocument();
    expect(reviewQuality).toHaveBeenCalledWith("Reza had strong delivery this quarter.");

    // Dismiss one chip → it disappears, the other stays (non-destructive, advisory).
    await user.click(screen.getAllByRole("button", { name: /Dismiss suggestion/i })[0]);
    expect(screen.queryByText(/isn't tied to a goal or metric/i)).toBeNull();
    expect(screen.getByText(/last few weeks/i)).toBeInTheDocument();
  });

  it("shows a clean result when nothing is flagged", async () => {
    reviewQuality.mockResolvedValue({ status: "ok", flags: [] });
    renderWith("Specific, balanced, evidence-backed review.");
    await userEvent.setup().click(screen.getByRole("button", { name: /Check with AI/i }));
    expect(await screen.findByText(/No issues flagged/i)).toBeInTheDocument();
  });

  it("degrades inline when the AI provider is unavailable (503)", async () => {
    reviewQuality.mockRejectedValue(axiosErr(503));
    renderWith("Some draft text.");
    await userEvent.setup().click(screen.getByRole("button", { name: /Check with AI/i }));
    expect(await screen.findByText(/AI check unavailable/i)).toBeInTheDocument();
  });

  it("disables the button with no text to check", () => {
    renderWith("   ");
    expect(screen.getByRole("button", { name: /Check with AI/i })).toBeDisabled();
  });
});
