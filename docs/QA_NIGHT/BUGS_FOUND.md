# QA_NIGHT — bugs found (severity-ranked)

Overnight machine-checkable QA, 2026-07-14, TWO passes.

**Pass 1** — 173 live HTTP checks at :8090 across four ACME roles + a GLOBEX tenant
(sweeps A/B/C/XT + the Phase-2 probe): **3 bugs found + fixed** (N1–N3). A follow-up
**`/security-review`** of the branch then found **1 HIGH** privilege escalation (N4) — fixed.

**Pass 2** — a second, deeper run over the modules pass 1 skipped: sweep D
(succession/career/one-on-ones/notifications, 28/28), sweep E (JD/review/feedback/
approvals **lifecycle** sub-endpoints, 34/34), and cross-tenant on the new modules
(11/11). Found **1 MEDIUM** (N5, JD non-object body → 500) — fixed.

**Total: 5 bugs found, all 5 FIXED with regression tests** (1 HIGH escalation, 1 HIGH
route-bypass, 3 MEDIUM/LOW). 2 low-severity observations remain as write-ups.

---

## FIXED tonight

### BUG-N5 · JD save-draft accepted a non-object body → 500 on submit/export — MEDIUM · fixed `f5cc539`
- **Module:** JD Library · `apps/jd/serializers.py` (`JDDraftSerializer`)
- **Steps:** as HRBP → `POST /api/jd/<id>/save-draft {"body": "just a string"}` (a bare JSON
  string, not an object) → then `POST /api/jd/<id>/submit` **or** `GET /api/jd/<id>/export`.
- **Actual (before):** the string body persisted onto the working version; the next legitimate
  operation crashed with **HTTP 500** (`AttributeError: 'str' object has no attribute 'get'` in
  `lifecycle.validate_jd_content` / export, which do `body.get("summary")`). A poisoned version
  row bricked the JD's submit + export paths.
- **Expected:** `body`/`inputs` must be JSON objects; a non-object is a clean 400 at the API
  boundary, nothing persisted.
- **Root cause:** `JDDraftSerializer.body = JSONField()` accepts ANY valid JSON (string/list/
  number), but every downstream consumer treats it as a dict.
- **Fix:** `validate_body` / `validate_inputs` reject non-dict input → 400. Regression test
  `test_save_draft_rejects_non_object_body_with_400` (also asserts submit stays 422 and export
  doesn't 500). Found in QA pass-2 sweep E. Only HRBP+ can reach save-draft, so impact is a
  self-inflicted broken-JD (500), not a cross-user issue — hence MEDIUM.

### BUG-N4 · Invite flow let an HRBP mint a full ADMIN account (privilege escalation) — HIGH · fixed `8c0bce5`
- **Module:** Identity / invitations · `apps/identity/invite_views.py`
- **Steps:** as HRBP (holds `INVITE_USERS`, but NOT the Admin-only `MANAGE_USERS_ROLES`)
  → `POST /api/admin/invitations {"email": "...", "role": "ADMIN"}` → the 201 returns the
  signed `invite_url` in-band → `POST /api/auth/invitations/<token>/accept` with a chosen
  password (AllowAny — no mailbox needed).
- **Actual (before):** a brand-new **ADMIN** account in the tenant. `InvitationCreateSerializer.role`
  accepted any role and no layer (serializer, view, `create_user`) capped it against the
  inviter's own role — so the invite path was a weaker alternate route around the Admin-only
  user/role-management gate. Intra-tenant vertical escalation HRBP → ADMIN.
- **Expected:** an inviter can assign a role only **at or below their own**; ADMIN invite by
  an HRBP → 403, nothing created.
- **Fix:** role-rank ceiling in `InvitationAdminView.post` (mirrors the SAML
  no-escalation rank cap). Regression test `test_hrbp_cannot_invite_a_higher_role_but_admin_can`
  + live-verified on :8090 (HRBP→ADMIN 403, HRBP→MANAGER 201, ADMIN→ADMIN 201).
  Found by `/security-review`, not the live sweeps — the sweeps checked *capability* denial
  (employee can't invite) but not the *role-ceiling within* an allowed capability.

### BUG-N1 · Repeat finalize bypassed an in-flight approval route — HIGH · fixed `9881297`
- **Module:** Reviews ↔ Approvals (Module 3 ↔ 5 integration) · `apps/reviews/state_machine.py`
- **Steps:** tenant has an ACTIVE "review" approval workflow → review reaches APPROVED →
  `POST /api/reviews/<id>/finalize` (enters the route, review stays APPROVED, 200) →
  call **finalize again**.
- **Actual (before):** 200 — the review flipped to FINALIZED while its route was still
  IN_PROGRESS. Any FINALIZE_REVIEW holder could defeat the approval matrix by calling
  finalize twice. Verified in the DB: `state=FINALIZED`, `route status=IN_PROGRESS`.
- **Expected:** the second call must wait on the route → 409 ACTIVE_ROUTE.
- **Root cause:** `finalize()` only branched to the route when `approval_route_id is None`;
  with a route already linked it fell through to `_finalize_apply`.
- **Fix:** explicit guard — in-flight route ⇒ raise `ActiveRouteExists` (409). Regression
  test `test_second_finalize_cannot_bypass_an_in_flight_route`. The one demo row corrupted
  during discovery was repaired (stale route CANCELLED).

### BUG-N2 · Non-numeric KPI actual → HTTP 500 + ghost audit row — MEDIUM · fixed `478e3d2`
- **Module:** Goals · `apps/goals/views.py` (`KpiActualsView`)
- **Steps:** owner posts `{"value": "not-a-number"}` to `/api/goals/kpis/<id>/actuals`.
- **Actual (before):** 500 (`decimal.InvalidOperation` inside `record_actual`) — and the
  **audit row "actual.recorded" was already written** for a write that never happened
  (audit-before-write ordering).
- **Expected:** 400 `{"value": "Enter a number."}`, no audit row, no measurement.
- **Fix:** validate the Decimal **before** the audit record (mirrors the AI
  `record_actual` action's guard). Regression test
  `test_non_numeric_actual_is_400_and_writes_nothing` asserts 400 + no measurement + no audit.

### BUG-N3 · Recognition accepted a 50,000-char message — LOW · fixed `15c5dad`
- **Module:** Recognition · `apps/recognition/services.py`
- **Steps:** `POST /api/recognition/` with a 50k-char `message`.
- **Actual (before):** 201 — the card landed in the feed. `TextField(max_length=1000)`
  is not enforced at the DB layer, and the service validated everything except length.
- **Expected:** 400 (limit 1000, matching the model's declared cap).
- **Fix:** service-level length check. Test `test_oversized_message_rejected`.

---

## Open observations (write-up only — not changed)

### OBS-N1 · 403 vs 404 mix on denied object access — LOW / consistency
- Some scoped denials return **403** (e.g. a peer posting to someone else's KPI actuals,
  cross-manager check-in respond), others **404** (cross-tenant everything, out-of-scope
  goal reads). The 403s are same-tenant-only, so no cross-tenant existence oracle exists
  (cross-tenant is a uniform 404 — verified in sweep XT, 29/29). Within a tenant a 403 can
  confirm an object id exists.
- **Suggested:** decide a policy (likely: keep 403 for capability failures, 404 for scope
  failures) and align the handful of OWN-check endpoints. Not changed at night — touching
  status codes across modules is a contract change QA/mobile may depend on.

### OBS-N2 · audit-before-write pattern can log an action that then fails — LOW
- The convention audits before the mutation (INSERT-only log, intentional). BUG-N2 showed
  the failure mode: a validation-late path leaves an audit row for a non-event. Most write
  paths validate first, so exposure is limited; worth a one-pass review that every
  `record(...)` sits **after** input validation (not after the DB write — that ordering is
  by design).
- **Suggested:** grep-audit each `record(action=...)` call site once, during the day.

---

## Verified-clean (no bug, worth stating)

- **Cross-tenant isolation: 29/29.** Every ACME record hit by a GLOBEX admin (goals,
  reviews, KPIs, check-ins, recognition, feedback, users, cycles, JDs — reads AND writes)
  → uniform 404; globex lists contain zero ACME rows; globex AI chat cannot resolve ACME
  people; ACME/GLOBEX logins don't cross tenants.
- **RBAC matrix holds over HTTP** for all four roles across goals/reviews/feedback/
  check-ins/recognition/org/JD/analytics/audit/approvals/cycles/billing/admin/AI
  (sweeps A+B+C: 144/144 after fixes). Employee org-export is correctly scoped to the
  own reporting line (5 nodes, not 211) — looked alarming, is by design.
- **Audit log is INSERT-only over HTTP** (GET-only console; POST/DELETE → 405).
- **State machines fail cleanly**: review transitions (409 ILLEGAL_TRANSITION /
  422 HITL_APPROVAL_REQUIRED), 360 open→give→close ordering, double-approve, double-submit,
  give-after-close — all clean 4xx, never 500, no corruption.
- **Validation walls hold**: weight >100 / negative, empty & oversized titles, malformed
  JSON, unknown ids, absurd values, SQLi-shaped search strings, invalid emails/roles/plans.
- **Phase-2 re-verified tonight: 49/49** (profile, password change/reset, email change,
  2FA surface, sessions/revoke/history/lockout, invitations + resend, plan gating).
