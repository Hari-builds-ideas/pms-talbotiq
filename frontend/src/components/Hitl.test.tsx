import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceBadge, HitlBanner, SourceBadge } from "./Hitl";

// HITL is the AI-safety surface: a draft must never read as final, and a
// low-confidence (< 0.70) artifact must be visibly flagged.

describe("ConfidenceBadge", () => {
  it("formats the score as a percentage when present", () => {
    render(<ConfidenceBadge score={0.88} />);
    expect(screen.getByText(/Confidence 88%/)).toBeInTheDocument();
  });

  it("renders nothing when there is no score", () => {
    const { container } = render(<ConfidenceBadge score={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("accepts a string score (Decimal from the API)", () => {
    render(<ConfidenceBadge score="0.66" />);
    expect(screen.getByText(/Confidence 66%/)).toBeInTheDocument();
  });
});

describe("HitlBanner", () => {
  it("reads as a pending (not final) draft above the confidence floor", () => {
    render(<HitlBanner confidence={0.88} source="AI" />);
    expect(screen.getByText(/Pending human review/i)).toBeInTheDocument();
    expect(screen.queryByText(/Low-confidence/i)).not.toBeInTheDocument();
    expect(screen.getByText(/AI-generated/i)).toBeInTheDocument();
  });

  it("elevates a low-confidence (< 0.70) draft with a warning title", () => {
    render(<HitlBanner confidence={0.5} source="AI" />);
    expect(screen.getByText(/Low-confidence draft — review carefully/i)).toBeInTheDocument();
  });

  it("renders a custom lead message when given", () => {
    render(<HitlBanner confidence={0.9} message="This JD is pending review." />);
    expect(screen.getByText("This JD is pending review.")).toBeInTheDocument();
  });
});

describe("SourceBadge", () => {
  it("marks AI provenance", () => {
    render(<SourceBadge source="AI" />);
    expect(screen.getByText(/AI-generated/i)).toBeInTheDocument();
  });
  it("renders nothing without a source", () => {
    const { container } = render(<SourceBadge source={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
