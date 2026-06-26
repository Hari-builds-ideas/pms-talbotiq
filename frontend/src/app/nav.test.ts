/**
 * RW_BUILD_1 1.2 — the sidebar is a pure function of role. These lock the re-cut:
 * a role sees ONLY the sections/items it can use (no shown-then-denied), employees
 * get the clean minimal Workspace set, and the enterprise tools stay HR/Admin-only.
 * See docs/NAV_RBAC_MAP.md / DECISIONS.md D31.
 */
import { describe, it, expect } from "vitest";
import { navForRole } from "./nav";
import type { Role } from "@/lib/enums";

const labels = (role: Role) => navForRole(role).flatMap((s) => s.items.map((i) => i.label));
const sections = (role: Role) => navForRole(role).map((s) => s.title);

const WORKSPACE = ["Home", "Goals & KPIs", "360 Feedback", "Reviews", "Career"];
const TEAM = ["Approvals", "Team Analytics"];
const ADVANCED = ["Succession", "Org Chart", "JD Library", "Audit Console"];
const ADMINISTRATION = ["Users & Roles", "Tenant Config", "Entitlements", "Integrations"];

describe("navForRole — per-role sidebar surface", () => {
  it("EMPLOYEE sees ONLY the Workspace everyday set — no management items", () => {
    expect(sections("EMPLOYEE")).toEqual(["Workspace"]);
    expect(labels("EMPLOYEE")).toEqual(WORKSPACE);
    // None of the management/enterprise/admin items leak into the employee nav.
    for (const hidden of [...TEAM, ...ADVANCED, ...ADMINISTRATION]) {
      expect(labels("EMPLOYEE")).not.toContain(hidden);
    }
  });

  it("MANAGER adds the Team section, but not Advanced or Administration", () => {
    expect(sections("MANAGER")).toEqual(["Workspace", "Team"]);
    expect(labels("MANAGER")).toEqual([...WORKSPACE, ...TEAM]);
    for (const hidden of [...ADVANCED, ...ADMINISTRATION]) {
      expect(labels("MANAGER")).not.toContain(hidden);
    }
  });

  it("HRBP adds the Advanced (HR tools) section, but not Administration", () => {
    expect(sections("HRBP")).toEqual(["Workspace", "Team", "Advanced"]);
    expect(labels("HRBP")).toEqual([...WORKSPACE, ...TEAM, ...ADVANCED]);
    for (const hidden of ADMINISTRATION) {
      expect(labels("HRBP")).not.toContain(hidden);
    }
  });

  it("ADMIN sees everything, including Administration", () => {
    expect(sections("ADMIN")).toEqual(["Workspace", "Team", "Advanced", "Administration"]);
    expect(labels("ADMIN")).toEqual([...WORKSPACE, ...TEAM, ...ADVANCED, ...ADMINISTRATION]);
  });

  it("employee surface is strictly minimal and a subset of every higher role", () => {
    const emp = labels("EMPLOYEE");
    expect(emp).toHaveLength(5);
    for (const role of ["MANAGER", "HRBP", "ADMIN"] as Role[]) {
      for (const item of emp) expect(labels(role)).toContain(item);
    }
  });
});
