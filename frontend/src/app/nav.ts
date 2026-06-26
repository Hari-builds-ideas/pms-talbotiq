import type { LucideIcon } from "lucide-react";
import {
  Award,
  Building2,
  ClipboardCheck,
  CreditCard,
  FileText,
  GitBranch,
  GraduationCap,
  LayoutDashboard,
  Network,
  Plug,
  MessageSquareText,
  ScrollText,
  Settings,
  ShieldCheck,
  Target,
  TrendingUp,
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
  title: string;
  items: NavItem[];
}

/**
 * Nav model, re-weighted per role (RW_BUILD_1, see docs/NAV_RBAC_MAP.md). Each
 * item's `minRole` is the LOWEST role whose primary read of that screen succeeds
 * against the backend RBAC matrix — and because every capability is granted to an
 * upward-closed role slice, `minRole` is exactly a capability check. A role sees
 * ONLY what it can use; items it can't are simply absent (the server still
 * enforces 403/404 independently — hiding a link is UX, not security).
 *
 *  - Workspace (EMPLOYEE+): the everyday surface every role gets — own goals,
 *    feedback, reviews, career. Employees see this and nothing else.
 *  - Team (MANAGER+): the team workflows (approvals, team analytics).
 *  - Advanced (HRBP+): the enterprise/HR tools, demoted off the everyday surface
 *    (succession + nine-box, org chart, JD library, audit). Managers can still
 *    deep-link where the backend allows; they're just not advertised here.
 *  - Administration (ADMIN): system administration.
 *
 * (Check-ins / Recognition are in the employee set per the re-weighting plan but
 * have no routes yet — RW_BUILD_2/3 add them; omitted here to avoid dead links.)
 */
export const NAV: NavSection[] = [
  {
    title: "Workspace",
    items: [
      { label: "Home", to: "/", icon: LayoutDashboard, minRole: "EMPLOYEE", end: true },
      { label: "Goals & KPIs", to: "/goals", icon: Target, minRole: "EMPLOYEE" },
      { label: "360 Feedback", to: "/feedback", icon: MessageSquareText, minRole: "EMPLOYEE" },
      { label: "Recognition", to: "/recognition", icon: Award, minRole: "EMPLOYEE" },
      { label: "Reviews", to: "/reviews", icon: FileText, minRole: "EMPLOYEE" },
      { label: "Career", to: "/career", icon: GraduationCap, minRole: "EMPLOYEE" },
    ],
  },
  {
    title: "Team",
    items: [
      { label: "Approvals", to: "/approvals", icon: ClipboardCheck, minRole: "MANAGER" },
      { label: "Team Analytics", to: "/analytics", icon: TrendingUp, minRole: "MANAGER" },
    ],
  },
  {
    title: "Advanced",
    items: [
      { label: "Succession", to: "/succession", icon: GitBranch, minRole: "HRBP" },
      { label: "Org Chart", to: "/org", icon: Network, minRole: "HRBP" },
      { label: "JD Library", to: "/jd", icon: ScrollText, minRole: "HRBP" },
      { label: "Audit Console", to: "/audit", icon: ShieldCheck, minRole: "HRBP" },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users & Roles", to: "/admin/users", icon: Users, minRole: "ADMIN" },
      { label: "Tenant Config", to: "/admin/tenant", icon: Settings, minRole: "ADMIN" },
      { label: "Entitlements", to: "/admin/billing", icon: CreditCard, minRole: "ADMIN" },
      { label: "Integrations", to: "/admin/integrations", icon: Plug, minRole: "ADMIN" },
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

export const APP_ICON = Building2;
