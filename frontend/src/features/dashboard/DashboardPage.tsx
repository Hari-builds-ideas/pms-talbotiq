import { CalendarDays } from "lucide-react";
import { useAuth } from "@/lib/auth/AuthContext";
import { ManagerDashboard } from "./managerDashboard";
import {
  AdminCockpit,
  EmployeeCockpit,
  HrbpCockpit,
} from "./cockpit-roles";

/**
 * Role-true cockpit. The manager view is the TalbotIQ mockup composition;
 * the other roles land on their own real tiles. Everything is composed
 * client-side from the real feature endpoints (no /dashboard endpoint).
 */
export function DashboardPage() {
  const { me } = useAuth();
  const role = me?.role;
  const first = me?.display ? me.display.split(" ")[0] : null;

  return (
    <div className="space-y-6">
      <DashboardHeader name={first} subtitle={descriptionFor(role)} />

      {role === "EMPLOYEE" ? (
        <EmployeeCockpit />
      ) : role === "ADMIN" ? (
        <AdminCockpit />
      ) : role === "HRBP" ? (
        <HrbpCockpit />
      ) : (
        <ManagerDashboard />
      )}
    </div>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function todayLabel(): string {
  try {
    return new Date().toLocaleDateString(undefined, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function DashboardHeader({ name, subtitle }: { name: string | null; subtitle: string }) {
  return (
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          {greeting()}{name ? `, ${name}` : ""} <span aria-hidden>👋</span>
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">{todayLabel()}</span>
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground">
          <CalendarDays className="h-3.5 w-3.5 text-primary" />
          Current cycle
        </span>
      </div>
    </div>
  );
}

function descriptionFor(role?: string): string {
  switch (role) {
    case "EMPLOYEE":
      return "Your goals, review, feedback and development in one place.";
    case "ADMIN":
      return "Tenant health, entitlements and the activity trail.";
    case "HRBP":
      return "Feedback summaries to release, succession coverage and approvals.";
    default:
      return "Here's what's happening with your team today.";
  }
}
