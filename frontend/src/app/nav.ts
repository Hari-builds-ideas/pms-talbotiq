import type { LucideIcon } from "lucide-react";
import {
  Award,
  BarChart3,
  CalendarCheck,
  ClipboardCheck,
  CreditCard,
  FileText,
  GitBranch,
  LayoutDashboard,
  MessageSquareText,
  Route,
  ScrollText,
  Settings,
  ShieldCheck,
  Sprout,
  Target,
  UserCog,
  Users,
} from "lucide-react";
import { ROLE_RANK, type Role } from "@/lib/enums";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Minimum role to see this entry (display gating — server still enforces). */
  minRole: Role;
  /** End-match for the active route (for index routes). */
  end?: boolean;
}

export interface NavSection {
  /** Group label shown in the sidebar; empty string = no header (the Dashboard row). */
  title: string;
  items: NavItem[];
}

/**
 * Nav model — the TalbotIQ mockup's sectioned sidebar (PERFORMANCE / TALENT /
 * INSIGHTS / SETTINGS), mapped onto the app's REAL routes. Per-role visibility is
 * preserved from the RW re-cut (docs/NAV_RBAC_MAP.md): each item's `minRole` is the
 * LOWEST role whose primary read of that screen succeeds against the backend RBAC
 * matrix, and because every capability is granted to an upward-closed role slice,
 * `minRole` is exactly a capability check. A role sees ONLY what it can use; items
 * it can't are simply absent (the server still enforces 403/404 — hiding a link is
 * UX, not security).
 *
 * The mockup also shows aspirational items with no backing route (1:1 Meetings, PIP &
 * Improvement, Teams, Skills & Competencies, Reports, Engagement, Benchmarks). Per
 * the no-dead-links rule those are intentionally OMITTED (decision N1) — Check-ins
 * stands in for "1:1 Meetings", Employees maps to the org/people surface.
 */
export const NAV: NavSection[] = [
  {
    title: "",
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard, minRole: "EMPLOYEE", end: true },
    ],
  },
  {
    title: "Performance",
    items: [
      { label: "Goals & OKRs", to: "/goals", icon: Target, minRole: "EMPLOYEE" },
      { label: "Reviews", to: "/reviews", icon: FileText, minRole: "EMPLOYEE" },
      { label: "Feedback", to: "/feedback", icon: MessageSquareText, minRole: "EMPLOYEE" },
      { label: "Check-ins", to: "/checkins", icon: CalendarCheck, minRole: "EMPLOYEE" },
      { label: "Recognition", to: "/recognition", icon: Award, minRole: "EMPLOYEE" },
      { label: "Approvals", to: "/approvals", icon: ClipboardCheck, minRole: "MANAGER" },
    ],
  },
  {
    title: "Talent",
    items: [
      { label: "Employees", to: "/org", icon: Users, minRole: "MANAGER" },
      { label: "Career Paths", to: "/career", icon: Route, minRole: "EMPLOYEE" },
      { label: "Succession", to: "/succession", icon: GitBranch, minRole: "HRBP" },
      { label: "JD Library", to: "/jd", icon: ScrollText, minRole: "HRBP" },
    ],
  },
  {
    title: "Insights",
    items: [
      { label: "Analytics", to: "/analytics", icon: BarChart3, minRole: "MANAGER" },
      { label: "Audit", to: "/audit", icon: ShieldCheck, minRole: "HRBP" },
    ],
  },
  {
    title: "Settings",
    items: [
      { label: "Users & Roles", to: "/admin/users", icon: UserCog, minRole: "ADMIN" },
      { label: "Configure", to: "/admin/tenant", icon: Settings, minRole: "ADMIN" },
      { label: "Entitlements", to: "/admin/billing", icon: CreditCard, minRole: "ADMIN" },
      // "Integrations" nav item removed — there is no /admin/integrations page (Jira/Slack
      // aren't wired), so the link went nowhere. Re-add with a real "not connected" page
      // when integrations ship. BUGS_FOUND #6/#16.
    ],
  },
];

/**
 * The sections + items a role should SEE — the single source the sidebar renders
 * and the tests assert. An item is visible iff the role's rank meets the item's
 * `minRole`; empty sections drop out. Pure function of role.
 */
export function navForRole(role: Role): NavSection[] {
  return NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) => ROLE_RANK[role] >= ROLE_RANK[item.minRole]),
  })).filter((section) => section.items.length > 0);
}

/**
 * Clamp a post-login redirect target to something the role can actually view.
 * If `from` points at a gated nav destination the role can't reach (e.g. an admin
 * route after switching to an HRBP account), fall back to "/" (the dashboard, which
 * every role can see) so the user never lands on a "You don't have access" page.
 * Unknown paths are left as-is; a missing role → "/". (BUGS_FOUND P0-3.)
 */
export function landingPathFor(from: string | undefined, role: Role | undefined): string {
  if (!role) return "/";
  const target = from || "/";
  let match: NavItem | null = null;
  for (const section of NAV) {
    for (const item of section.items) {
      if (item.to === "/") continue;
      if (target === item.to || target.startsWith(item.to + "/")) {
        if (!match || item.to.length > match.to.length) match = item;
      }
    }
  }
  if (match && ROLE_RANK[role] < ROLE_RANK[match.minRole]) return "/";
  return target;
}

/** Brand mark (TalbotIQ leaf). */
export const APP_ICON = Sprout;
