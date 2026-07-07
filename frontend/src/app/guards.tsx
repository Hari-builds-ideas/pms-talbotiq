import * as React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Ban, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth/AuthContext";
import { ROLE_RANK, type Role } from "@/lib/enums";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

/** Full-screen branded loader for the auth bootstrap. */
export function FullScreenLoader({ label }: { label?: string }) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 bg-background text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
      {label && <p className="text-sm">{label}</p>}
    </div>
  );
}

/** Redirects unauthenticated users to /login (preserving the target). */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullScreenLoader label="Loading your workspace…" />;
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/**
 * Gates a route to a minimum role. Renders a clean 403 page rather than hiding,
 * matching the "your role can't do this" rule (the server enforces it too).
 */
export function RoleGate({
  min,
  children,
}: {
  min: Role;
  children: React.ReactNode;
}) {
  const { me, status } = useAuth();
  // Never flash a false 403 while auth is still resolving (BUGS_FOUND P0-3).
  if (status === "loading") return <FullScreenLoader label="Loading…" />;
  if (me && ROLE_RANK[me.role] >= ROLE_RANK[min]) return <>{children}</>;
  return <NotPermitted />;
}

export function NotPermitted() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-border bg-card px-6 py-20 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-subtle text-danger">
        <Ban className="h-6 w-6" />
      </div>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">You don't have access</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Your role doesn't have permission to view this area. If you think this is
          a mistake, contact your workspace admin.
        </p>
      </div>
      <Button asChild variant="outline" size="sm">
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
