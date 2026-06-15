import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/app/shell/AppLayout";
import { AuthGuard, RoleGate } from "@/app/guards";
import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { UsersPage } from "@/features/admin/UsersPage";
import { TenantConfigPage } from "@/features/admin/TenantConfigPage";
import { BillingPage } from "@/features/admin/BillingPage";
import { ApprovalsPage } from "@/features/approvals/ApprovalsPage";
import { ReviewsRoutes } from "@/features/reviews/ReviewsRoutes";
import { OrgPage } from "@/features/org/OrgPage";
import { SuccessionPage } from "@/features/succession/SuccessionPage";
import { AnalyticsPage } from "@/features/analytics/AnalyticsPage";
import { JdRoutes } from "@/features/jd/JdRoutes";
import { AuditPage } from "@/features/audit/AuditPage";
import { IntegrationsPage } from "@/features/integrations/IntegrationsPage";

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
                <ApprovalsPage />
              </RoleGate>
            }
          />
          <Route
            path="reviews/*"
            element={
              <RoleGate min="MANAGER">
                <ReviewsRoutes />
              </RoleGate>
            }
          />
          <Route
            path="org/*"
            element={
              <RoleGate min="MANAGER">
                <OrgPage />
              </RoleGate>
            }
          />
          <Route
            path="jd/*"
            element={
              <RoleGate min="MANAGER">
                <JdRoutes />
              </RoleGate>
            }
          />
          <Route
            path="succession/*"
            element={
              <RoleGate min="MANAGER">
                <SuccessionPage />
              </RoleGate>
            }
          />
          <Route
            path="analytics/*"
            element={
              <RoleGate min="MANAGER">
                <AnalyticsPage />
              </RoleGate>
            }
          />
          <Route
            path="audit/*"
            element={
              <RoleGate min="HRBP">
                <AuditPage />
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
                <IntegrationsPage />
              </RoleGate>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
