import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AIJobBanner } from "./AIJobBanner";
import { isTerminal } from "@/lib/hooks/useAIJob";
import type { AIJob, AIJobStatus } from "@/lib/types";

// The async-AI job surface (BUILD_2): a working state while QUEUED/RUNNING, a
// calm assistive banner on DEGRADED, a recoverable error on FAILED, and nothing
// on SUCCEEDED (the caller re-fetches the artifact). AI is assistive, never a
// dead-end — the manual path is always available.

function job(status: AIJobStatus, error_code = ""): AIJob {
  return {
    id: "job-1",
    status,
    agent_code: "agent1",
    target_type: "review",
    target_id: "rev-1",
    result_id: null,
    confidence: null,
    error_code,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

describe("isTerminal", () => {
  it("is true only for terminal states", () => {
    expect(isTerminal("QUEUED")).toBe(false);
    expect(isTerminal("RUNNING")).toBe(false);
    expect(isTerminal("SUCCEEDED")).toBe(true);
    expect(isTerminal("DEGRADED")).toBe(true);
    expect(isTerminal("FAILED")).toBe(true);
    expect(isTerminal(null)).toBe(false);
  });
});

describe("AIJobBanner", () => {
  it("renders nothing when there is no job or on SUCCEEDED", () => {
    const { container: a } = render(<AIJobBanner job={null} />);
    expect(a).toBeEmptyDOMElement();
    const { container: b } = render(<AIJobBanner job={job("SUCCEEDED")} />);
    expect(b).toBeEmptyDOMElement();
  });

  it("shows the working state with a custom label while QUEUED/RUNNING", () => {
    render(<AIJobBanner job={job("RUNNING")} working="AI is drafting this review…" />);
    expect(screen.getByText(/AI is drafting this review/i)).toBeInTheDocument();
  });

  it("DEGRADED reads as a calm, assistive state — copy per reason", () => {
    const { rerender } = render(<AIJobBanner job={job("DEGRADED", "NOT_CONFIGURED")} />);
    expect(screen.getByText(/AI assistant unavailable/i)).toBeInTheDocument();
    rerender(<AIJobBanner job={job("DEGRADED", "BUDGET_EXCEEDED")} />);
    expect(screen.getByText(/AI budget reached/i)).toBeInTheDocument();
    rerender(<AIJobBanner job={job("DEGRADED", "ANONYMITY_HOLD")} />);
    expect(screen.getByText(/Held for anonymity/i)).toBeInTheDocument();
  });

  it("offers retry on FAILED and on a retryable DEGRADE, but NOT on the anonymity hold", () => {
    const onRetry = () => {};
    const { rerender } = render(<AIJobBanner job={job("FAILED")} onRetry={onRetry} />);
    expect(screen.getByText(/AI step failed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();

    rerender(<AIJobBanner job={job("DEGRADED", "ANONYMITY_HOLD")} onRetry={onRetry} />);
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });
});
