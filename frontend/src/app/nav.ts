import type { LucideIcon } from "lucide-react";
import {
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
import type { Role } from "@/lib/enums";

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
 * Nav model — gated by role per the V0 brief table. Management-only areas
 * (Succession, Analytics, Audit) and Admin areas are simply absent for roles
 * that can't reach them; the server independently enforces 403/404.
 */
export const NAV: NavSection[] = [
  {
    title: "Workspace",
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard, minRole: "MANAGER", end: true },
      { label: "Approvals", to: "/approvals", icon: ClipboardCheck, minRole: "MANAGER" },
      { label: "Reviews", to: "/reviews", icon: FileText, minRole: "MANAGER" },
      { label: "Goals & KPIs", to: "/goals", icon: Target, minRole: "MANAGER" },
      { label: "360 Feedback", to: "/feedback", icon: MessageSquareText, minRole: "MANAGER" },
      { label: "Org Chart", to: "/org", icon: Network, minRole: "MANAGER" },
      { label: "JD Library", to: "/jd", icon: ScrollText, minRole: "MANAGER" },
      { label: "Career", to: "/career", icon: GraduationCap, minRole: "EMPLOYEE" },
    ],
  },
  {
    title: "Talent Intelligence",
    items: [
      { label: "Succession", to: "/succession", icon: GitBranch, minRole: "MANAGER" },
      { label: "Analytics", to: "/analytics", icon: TrendingUp, minRole: "MANAGER" },
    ],
  },
  {
    title: "Governance",
    items: [
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

export const APP_ICON = Building2;
