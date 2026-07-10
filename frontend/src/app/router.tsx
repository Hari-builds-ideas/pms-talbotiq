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
import { GoalsPage } from "@/features/goals/GoalsPage";
import { FeedbackPage } from "@/features/feedback/FeedbackPage";
import { OrgPage } from "@/features/org/OrgPage";
import { SuccessionPage } from "@/features/succession/SuccessionPage";
import { AnalyticsPage } from "@/features/analytics/AnalyticsPage";
import { JdRoutes } from "@/features/jd/JdRoutes";
import { CareerPage } from "@/features/career/CareerPage";
import { isHiddenInV1 } from "@/app/v1";
import { ProfilePage } from "@/features/people/ProfilePage";
import { RecognitionPage } from "@/features/recognition/RecognitionPage";
import { CheckInsPage } from "@/features/checkins/CheckInsPage";
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
          {/* Goals / Reviews / Feedback are EVERYDAY surfaces open to every role:
              the backend grants VIEW_OWN_GOALS / VIEW_OWN_REVIEW / GIVE_FEEDBACK to
              all roles (own scope) and enforces it server-side, so no RoleGate here.
              The prior min="MANAGER" gate was stricter than the backend and produced
              the "dashboard tile → no access" dead end for employees (RW_BUILD_1,
              D31). Management-only ACTIONS inside these screens stay role-gated. */}
          <Route path="reviews/*" element={<ReviewsRoutes />} />
          <Route path="goals/*" element={<GoalsPage />} />
          <Route path="feedback/*" element={<FeedbackPage />} />
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
          {/* Career roadmap is open to everyone: employees get a read-only view
              of their OWN roadmap (VIEW_CAREER_ROADMAP is granted to all roles,
              OWN scope), managers/HRBP additionally see their team. No RoleGate —
              the dashboard advertises this tile to employees, so it must not 403
              the person who clicks it (BUG 3). Scope is enforced server-side. */}
          {/* v1: career roadmaps hidden (deferred to v2). Route kept, guarded by the
              central v1 scope switch so v2 restores it by editing app/v1.ts only. */}
          {!isHiddenInV1("/career") && <Route path="career/*" element={<CareerPage />} />}
          {/* Employee profile — read-only growth narrative composed from existing
              scope-bound endpoints; no RoleGate (each section's endpoint enforces
              scope, 404 → friendly empty state, same D31 pattern as career/goals). */}
          <Route path="people/:id" element={<ProfilePage />} />
          {/* Recognition (RW_BUILD_2) — everyday surface for ALL roles; the feed's
              row visibility is enforced server-side, so no RoleGate. */}
          <Route path="recognition/*" element={<RecognitionPage />} />
          {/* Weekly Check-ins (RW_BUILD_3) — everyday surface for ALL roles; scope
              (own / a manager's reports) is enforced server-side. */}
          <Route path="checkins/*" element={<CheckInsPage />} />
          {/* v1: succession + nine-box hidden (deferred to v2). Route + component kept. */}
          {!isHiddenInV1("/succession") && (
            <Route
              path="succession/*"
              element={
                <RoleGate min="MANAGER">
                  <SuccessionPage />
                </RoleGate>
              }
            />
          )}
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
          {/* v1: raw-JSON tenant-config hidden (too technical for v1 admins). Kept for v2. */}
          {!isHiddenInV1("/admin/tenant") && (
            <Route
              path="admin/tenant/*"
              element={
                <RoleGate min="ADMIN">
                  <TenantConfigPage />
                </RoleGate>
              }
            />
          )}
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
