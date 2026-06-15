import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/app/shell/AppLayout";
import { AuthGuard, RoleGate } from "@/app/guards";
import { LoginPage } from "@/features/auth/LoginPage";
import { ComingSoon } from "@/components/ComingSoon";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { UsersPage } from "@/features/admin/UsersPage";
import { TenantConfigPage } from "@/features/admin/TenantConfigPage";
import { BillingPage } from "@/features/admin/BillingPage";

/**
 * App routes. Each management/admin area is wrapped in a RoleGate so a
 * disallowed role gets a clean 403 page (the server enforces it independently).
 * Feature screens are filled in per build phase.
 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          element={
            <AuthGuard>
              <AppLayout />
            </AuthGuard>
          }
        >
          <Route index element={<DashboardPage />} />

          <Route
            path="approvals/*"
            element={
              <RoleGate min="MANAGER">
                <ComingSoon title="Approvals" phase="Phase 3" description="Inbox, route tracker and the workflow designer." />
              </RoleGate>
            }
          />
          <Route
            path="reviews/*"
            element={
              <RoleGate min="MANAGER">
                <ComingSoon title="Reviews" phase="Phase 4" description="The HITL review lifecycle." />
              </RoleGate>
            }
          />
          <Route
            path="org/*"
            element={
              <RoleGate min="MANAGER">
                <ComingSoon title="Org Chart" phase="Phase 5" description="Reporting tree, people, vacancies and positions." />
              </RoleGate>
            }
          />
          <Route
            path="jd/*"
            element={
              <RoleGate min="MANAGER">
                <ComingSoon title="JD Library" phase="Phase 7" description="Job descriptions, versions and lifecycle." />
              </RoleGate>
            }
          />
          <Route
            path="succession/*"
            element={
              <RoleGate min="MANAGER">
                <ComingSoon title="Succession" phase="Phase 6" description="Coverage, 9-box, bench and plans." />
              </RoleGate>
            }
          />
          <Route
            path="analytics/*"
            element={
              <RoleGate min="MANAGER">
                <ComingSoon title="Analytics" phase="Phase 6" description="Individual, department and calibration views." />
              </RoleGate>
            }
          />
          <Route
            path="audit/*"
            element={
              <RoleGate min="HRBP">
                <ComingSoon title="Audit Console" phase="Phase 7" description="Read-only, filterable activity log." />
              </RoleGate>
            }
          />

          <Route
            path="admin/users/*"
            element={
              <RoleGate min="ADMIN">
                <UsersPage />
              </RoleGate>
            }
          />
          <Route
            path="admin/tenant/*"
            element={
              <RoleGate min="ADMIN">
                <TenantConfigPage />
              </RoleGate>
            }
          />
          <Route
            path="admin/billing/*"
            element={
              <RoleGate min="ADMIN">
                <BillingPage />
              </RoleGate>
            }
          />
          <Route
            path="admin/integrations/*"
            element={
              <RoleGate min="ADMIN">
                <ComingSoon title="Integrations" phase="Phase 7" description="Jira and Slack configuration." />
              </RoleGate>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
