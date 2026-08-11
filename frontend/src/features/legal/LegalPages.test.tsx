/**
 * The legal + support pages.
 *
 * The banner assertion is the point of this file. The bodies are an engineer's draft,
 * and a page that *looks* like reviewed policy is worse than an obviously unfinished
 * one — a customer's legal team will skim it and assume somebody signed it off. When
 * counsel-approved text lands, this test fails, which makes removing the banner a
 * deliberate decision visible in the diff rather than a silent one.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PrivacyPage, SUPPORT_EMAIL, SupportPage, TermsPage } from "./LegalPages";

const show = (ui: React.ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

describe("legal pages", () => {
  it("privacy is headed and marked as a draft", () => {
    show(<PrivacyPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Privacy Policy");
    expect(screen.getByText(/pending legal review/i)).toBeTruthy();
  });

  it("terms is headed and marked as a draft", () => {
    show(<TermsPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Terms of Service");
    expect(screen.getByText(/pending legal review/i)).toBeTruthy();
  });

  it("support carries no draft banner — it is not a legal document", () => {
    show(<SupportPage />);
    expect(screen.queryByText(/pending legal review/i)).toBeNull();
  });

  it("every page offers a reachable support address", () => {
    for (const ui of [<PrivacyPage key="p" />, <TermsPage key="t" />, <SupportPage key="s" />]) {
      const { unmount } = show(ui);
      const mailto = screen
        .getAllByRole("link")
        .filter((a) => a.getAttribute("href")?.startsWith("mailto:"));
      expect(mailto.length).toBeGreaterThan(0);
      expect(mailto[0].getAttribute("href")).toBe(`mailto:${SUPPORT_EMAIL}`);
      unmount();
    }
  });

  it("privacy states the two things a customer actually asks about", () => {
    show(<PrivacyPage />);
    // Who is responsible, and whether the AI can act on its own.
    expect(screen.getByText(/data controller/i)).toBeTruthy();
    expect(screen.getByText(/held for human review/i)).toBeTruthy();
  });
});
