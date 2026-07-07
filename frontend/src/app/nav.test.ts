/**
 * The sidebar is a pure function of role. These lock the TalbotIQ-mockup IA re-cut
 * (PERFORMANCE / TALENT / INSIGHTS / SETTINGS) while preserving the RW invariants:
 * a role sees ONLY the sections/items it can use (no shown-then-denied), employees
 * get the clean minimal everyday set, and the enterprise/admin tools stay gated.
 * See docs/design/REDESIGN_PLAN.md §(b) / docs/NAV_RBAC_MAP.md / DECISIONS.md D31.
 */
import { describe, it, expect } from "vitest";
import { navForRole } from "./nav";
import type { Role } from "@/lib/enums";

const labels = (role: Role) => navForRole(role).flatMap((s) => s.items.map((i) => i.label));
const sections = (role: Role) => navForRole(role).map((s) => s.title);

const DASHBOARD = ["Dashboard"];
const PERF_EMP = ["Goals & OKRs", "Reviews", "Feedback", "Check-ins", "Recognition"];
const PERF_MGR = [...PERF_EMP, "Approvals"];
const TALENT_EMP = ["Career Paths"];
const TALENT_MGR = ["Employees", "Career Paths"];
const TALENT_HRBP = ["Employees", "Career Paths", "Succession", "JD Library"];
const INSIGHTS_MGR = ["Analytics"];
const INSIGHTS_HRBP = ["Analytics", "Audit"];
const SETTINGS = ["Users & Roles", "Configure", "Entitlements"];

// Items no employee should ever see in the nav (display gating; server still enforces).
const MANAGER_PLUS = ["Approvals", "Employees", "Analytics"];
const HR_ADMIN = ["Succession", "JD Library", "Audit", ...SETTINGS];

describe("navForRole — per-role sidebar surface (TalbotIQ IA)", () => {
  it("EMPLOYEE sees ONLY the everyday set — no management/enterprise/admin items", () => {
    expect(sections("EMPLOYEE")).toEqual(["", "Performance", "Talent"]);
    expect(labels("EMPLOYEE")).toEqual([...DASHBOARD, ...PERF_EMP, ...TALENT_EMP]);
    for (const hidden of [...MANAGER_PLUS, ...HR_ADMIN]) {
      expect(labels("EMPLOYEE")).not.toContain(hidden);
    }
  });

  it("MANAGER adds team items (Approvals/Employees/Analytics), but not HR/Admin tools", () => {
    expect(sections("MANAGER")).toEqual(["", "Performance", "Talent", "Insights"]);
    expect(labels("MANAGER")).toEqual([
      ...DASHBOARD,
      ...PERF_MGR,
      ...TALENT_MGR,
      ...INSIGHTS_MGR,
    ]);
    for (const hidden of HR_ADMIN) {
      expect(labels("MANAGER")).not.toContain(hidden);
    }
  });

  it("HRBP adds the HR tools (Succession/JD/Audit), but not Administration", () => {
    expect(sections("HRBP")).toEqual(["", "Performance", "Talent", "Insights"]);
    expect(labels("HRBP")).toEqual([
      ...DASHBOARD,
      ...PERF_MGR,
      ...TALENT_HRBP,
      ...INSIGHTS_HRBP,
    ]);
    for (const hidden of SETTINGS) {
      expect(labels("HRBP")).not.toContain(hidden);
    }
  });

  it("ADMIN sees everything, including Settings", () => {
    expect(sections("ADMIN")).toEqual(["", "Performance", "Talent", "Insights", "Settings"]);
    expect(labels("ADMIN")).toEqual([
      ...DASHBOARD,
      ...PERF_MGR,
      ...TALENT_HRBP,
      ...INSIGHTS_HRBP,
      ...SETTINGS,
    ]);
  });

  it("employee surface is strictly minimal and a subset of every higher role", () => {
    const emp = labels("EMPLOYEE");
    expect(emp).toHaveLength(7);
    for (const role of ["MANAGER", "HRBP", "ADMIN"] as Role[]) {
      for (const item of emp) expect(labels(role)).toContain(item);
    }
  });
});
