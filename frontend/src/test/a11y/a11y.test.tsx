/**
 * Automated WCAG 2.1 A/AA guard — renders the key Admin-Hub screens in the real
 * shell (sidebar + topbar + main + skip-link) with realistic MSW data and asserts
 * axe-core finds ZERO A/AA violations. This is the regression gate the build keeps
 * green; see docs/ACCESSIBILITY.md for what it does and does NOT cover (jsdom has
 * no layout engine, so color-contrast / focus-visible / reflow are checked by the
 * token-contrast test + a documented manual/AT pass).
 */
import { fireEvent, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const me = {
  id: "u-admin-001",
  email: "admin@acme.test",
  display_name: "Ada Admin",
  display: "Ada Admin",
  role: "ADMIN",
  tenant_id: "t-1",
  tenant_name: "Acme",
  tenant_slug: "acme",
  mfa_enabled: false,
  manager_id: null,
};

vi.mock("@/lib/auth/AuthContext", () => ({
  useAuth: () => ({
    me,
    status: "authenticated",
    features: {},
    hasFeature: () => true,
    atLeast: () => true,
    logout: vi.fn(),
    completeLogin: vi.fn(),
    refreshFeatures: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import { axeViolations, renderBare, renderInShell, summarize } from "./harness";
import { server } from "@/mocks/server";

import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ReviewsRoutes } from "@/features/reviews/ReviewsRoutes";
import { GoalsPage } from "@/features/goals/GoalsPage";
import { FeedbackPage } from "@/features/feedback/FeedbackPage";
import { OrgPage } from "@/features/org/OrgPage";
import { SuccessionPage } from "@/features/succession/SuccessionPage";
import { AnalyticsPage } from "@/features/analytics/AnalyticsPage";
import { JdRoutes } from "@/features/jd/JdRoutes";
import { CareerPage } from "@/features/career/CareerPage";
import { AuditPage } from "@/features/audit/AuditPage";
import { UsersPage } from "@/features/admin/UsersPage";
import { TenantConfigPage } from "@/features/admin/TenantConfigPage";
import { ApprovalsPage } from "@/features/approvals/ApprovalsPage";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function settle() {
  await waitFor(() => {}, { timeout: 1500 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 600));
}

const screens: Array<[string, () => ReturnType<typeof renderInShell>]> = [
  ["login", () => renderBare(<LoginPage />, "/login")],
  ["dashboard", () => renderInShell(<DashboardPage />, "/")],
  ["reviews", () => renderInShell(<ReviewsRoutes />, "/reviews")],
  ["goals", () => renderInShell(<GoalsPage />, "/goals")],
  ["feedback", () => renderInShell(<FeedbackPage />, "/feedback")],
  ["org chart", () => renderInShell(<OrgPage />, "/org")],
  ["succession (nine-box)", () => renderInShell(<SuccessionPage />, "/succession")],
  ["analytics", () => renderInShell(<AnalyticsPage />, "/analytics")],
  ["jd generation", () => renderInShell(<JdRoutes />, "/jd")],
  ["career", () => renderInShell(<CareerPage />, "/career")],
  ["audit log", () => renderInShell(<AuditPage />, "/audit")],
  ["admin users", () => renderInShell(<UsersPage />, "/admin/users")],
  ["admin tenant/KPI config", () => renderInShell(<TenantConfigPage />, "/admin/tenant")],
  ["approvals", () => renderInShell(<ApprovalsPage />, "/approvals")],
];

describe("WCAG 2.1 A/AA — axe guard over the Admin Hub screens", () => {
  for (const [name, renderFn] of screens) {
    it(`has no A/AA violations: ${name}`, async () => {
      const { container } = renderFn();
      await settle();
      const violations = await axeViolations(container);
      expect(violations, `\n${name}:\n${summarize(violations)}`).toEqual([]);
    });
  }

  it("has no A/AA violations: command palette (⌘K) open", async () => {
    const { container } = renderInShell(<DashboardPage />, "/");
    await settle();
    fireEvent.keyDown(document, { key: "k", metaKey: true, ctrlKey: true });
    await waitFor(() => {
      // cmdk renders a dialog/listbox when open
      if (!container.ownerDocument.querySelector('[role="dialog"],[cmdk-root]')) {
        throw new Error("palette not open yet");
      }
    }, { timeout: 1500 }).catch(() => {});
    const root = container.ownerDocument.body;
    const violations = await axeViolations(root);
    expect(violations, `command palette:\n${summarize(violations)}`).toEqual([]);
  });
});
