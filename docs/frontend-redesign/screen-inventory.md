# Screen Inventory — Talbotiq PMS (Admin Hub, current build)

> **Purpose.** Every screen in the desktop Admin Hub: purpose, actions, data,
> components, and ALL states — with an honest **build verdict** (STRONG / OK /
> WEAK / MISSING) and the key gaps. **Grounding.** The real `frontend/src/features/*`
> (surveyed) + `docs/frontend-contract/01_screens.md` + the serializers. This is the
> "what exists vs what's weak" map that drives the redesign priority.
> **Surface note:** the Admin Hub is **Manager-and-up**; succession is
> **management-only and 404 for employees** — it must never appear on an employee
> surface or the mobile build. Employee self-service is the mobile surface.
>
> Every screen also handles the global states (loading / 401→login /
> 403→not-permitted / 404→not-yours / 429→retry-or-upgrade / 503→AI-unavailable /
> locked-by-flag) via the shared `errors.ts` mapper + `ErrorState`/`EmptyState`/
> `FeatureGate`; only screen-specific gaps are called out.

**Verdict legend:** STRONG = premium-ready · OK = works, needs refinement · WEAK =
works but feels plain/incomplete (redesign target) · MISSING = not built.

**Shared vocabulary (preserve):** `Panel`, `DataTable` (client-sort + server-page),
`PageHeader`, `EmptyState`, `ErrorState` (kind-aware), `StatusBadge` (single colour
authority), `StatCard`, `Hitl` (`DraftBadge`/`SourceBadge`/`ConfidenceBadge`/
`HitlBanner`), `NineBoxGrid`, `Stepper`/`Timeline`, `FeatureGate`, dark-sidebar shell.

---

## 1. Auth & MFA — `/login` · all roles · **OK**
- **Purpose:** tenant-qualified login (+ MFA challenge/enrol; SSO handoff).
- **Actions:** sign in; submit TOTP; enrol MFA; (SSO — disabled CTA).
- **Data:** none until `me`.
- **Components:** split-panel (brand left, form right), `Field`, `Input`.
- **States:** form · invalid-creds (401) · MFA-required→TOTP · enrolment (QR) · SSO
  redirect · authenticated→route by role. **Missing:** forgot-password/recovery;
  inline validation before submit; the SSO button is a dead end.
- **Gaps:** first-impression is generic; no recovery flow; demo shortcuts are dev-only.

## 2. Dashboard / role cockpit — `/` · all roles (employees land here, no nav) · **WEAK** ⭐
- **Purpose:** role-true landing — metrics + work items + alerts, composed client-side.
- **Actions:** "Ask AI"; tile "View all" links; (no quick/bulk actions).
- **Data:** reviews, approvals inbox count, goals/scores, nudges, feedback requests,
  succession coverage (HRBP+), entitlements, roadmap snapshot — many sources.
- **Components:** `PageHeader` + `StatCard` grid + `Panel` tiles + feature-lock tiles.
- **States:** loading skeletons · empty · error-retry · feature-lock upsell — handled.
- **Gaps (Tier-1 redesign):** flat hierarchy (every tile equal weight; RED roles /
  CRITICAL nudges don't stand out); tiles truncate at ~6 rows with no drill-in; "View
  all" gives no destination hint; dense HRBP/Manager cockpits = long scroll, no
  customization; **counts not insight** (no trends, no "recommended next actions", no
  one-click "approve 3 / release 2"); feature-lock tiles clutter (belong in a banner);
  employee cockpit feels like an afterthought.

## 3. Goals & KPIs — `/goals` · Manager+ (own = mobile) · **WEAK** ⭐
- **Purpose:** create/weight goals + KPIs, record actuals, approve, recompute.
- **Actions:** New goal (dialog); Record actual (inline per KPI); Approve; Recompute.
- **Data:** goals grouped by employee; KPI target/actual/weight; CycleScore + risk.
- **Components:** employee-section card grid; create dialog with a KPI sub-grid.
- **States:** empty · draft vs active · scores-not-computed · weight-sum badge · 422
  weight error — handled. **Validation:** KPI weights = 100 and active-goal weights =
  100 (mirror `weights.ts`).
- **Gaps:** card layout flat (no active/draft/approved distinction); weight verified by
  a text badge not a progress bar; **no live running-sum as you type** in the dialog;
  actuals are one-by-one (no batch, no unit context); recompute is opaque (no "what
  changed"); no goal→review linkage; no visual progress-to-target.

## 4. Reviews — `/reviews` (list) + `/reviews/<id>` (detail) · Manager+ (own read = mobile) · **OK** (arch STRONG)
- **Purpose:** author → AI-draft → 🔒approve → finalize a review through the state machine.
- **Actions:** New review; Request AI draft; Start-edit/Submit; Approve; Reject(reason);
  Finalize; submit assessments (SELF/MANAGER/…).
- **Data:** Review {state, draft/final body, source, confidence, citations,
  human_reviewer}; evidence (goals+KPIs+T-score); assessments; approval route; timeline.
- **Components:** list `DataTable` + cycle filter → 3-col detail (editor · sidebar:
  details/route/assessments/history), `Stepper`, `Timeline`, `HitlBanner`, `ReviewEvidence`.
- **States:** all 7 review states · AI_DRAFTING (poll/"updates automatically") · PENDING
  (HITL: Approve/Reject/Edit + draft badge + confidence) · 409 illegal · 503 no agent1 ·
  403 no FULL_AI — handled.
- **Gaps:** AI draft feels async/janky ("check back" — no streaming/optimistic);
  evidence panel is badge-dense, no target-vs-actual viz; assessments cramped (hard to
  tell SELF vs MANAGER; no timestamps); reject has no canned reasons; **no bulk
  "review all reports this cycle"**; no draft-vs-final / self-vs-manager side-by-side;
  no comment threads.

## 5. 360 Feedback — `/feedback` (tabs: For me · My 360 · Cycles · Summaries-to-release) · Manager+ (give/My-360 = mobile) · **OK**
- **Purpose:** give feedback; see own released summary; run cycles; HRBP release summaries.
- **Actions:** Give (dialog); Decline; Create/Open/Invite/Close cycle; Re-summarize;
  Release summary.
- **Data:** invitations; FeedbackCycle; anonymised payload (pseudonyms, volumes,
  insufficient_groups, **no giver ids**); FeedbackSummary (4 sections|null + status +
  anonymity_passed + confidence). My 360 uses the new `/my-cycles` discovery (no pasted id).
- **Components:** tabs + `Panel` lists + `GiveFeedbackDialog` + `CycleSheet` (manage) +
  `SummaryView` (sections + safety badges + HITL).
- **States:** cycle DRAFT/COLLECTING/CLOSED · pending invitations · giver-less received ·
  anonymised view (CLOSED) · summary PENDING/HRBP_HOLD/RELEASED · 403 SUMMARY_NOT_RELEASED
  · sections NULL = "not generated" — handled.
- **Gaps:** give dialog lacks context (who/why); **no response-rate per cycle** ("4/5
  responded") or reminders; My-360 PENDING just says "not released yet"; release is
  one-button (no edit-before-release, no per-relationship gating); summary confidence
  shown but unexplained.

## 6. Approvals — `/approvals` (tabs: Inbox · Workflow designer) + route tracker · Manager+ (config HRBP/Admin) · **OK**
- **Purpose:** act on assigned approval steps; design/activate workflows; watch routes.
- **Actions:** Approve/Reject(comment) a step; Create/Edit(=re-create)/Activate/Deactivate
  a workflow.
- **Data:** inbox (artifact, step#, role, due, status); ApprovalRoute + step instances;
  ApprovalWorkflow + steps.
- **Components:** tabs, `Panel` lists, `RouteTracker` (vertical `Timeline`), `RouteSheet`.
- **States:** inbox empty/items (SEQUENTIAL = only active step) · tracker stepper
  (status/due/escalated) · 409 out-of-order/decided · 403 not-the-assignee — handled.
- **Gaps:** inbox approval opens a sheet (not inline); tracker doesn't highlight "your
  step" / time remaining; designer is a numbered list (no drag-drop, no conditions); no
  email/Slack notification setup (approvers only see it on login); no bulk.

## 7. JD Library — `/jd` (list + Requests tab) + `/jd/<id>` (detail) · Manager+ browse / HRBP+ author · **OK**
- **Purpose:** author/generate/approve/publish JDs; handle JD requests.
- **Actions:** New JD; Save-draft; Submit; Approve & publish; Generate with AI; Revise
  (new version); Archive; Fulfil/Decline a request.
- **Data:** JobDescription {status, source, current_version}; JDVersion {body sections,
  confidence, is_published}; JDRequest.
- **Components:** list `DataTable` + tabs → detail (editor left, version history right),
  `SourceBadge`/`HitlBanner`/`ConfidenceBadge`, generate dialog (brief → inputs → generate).
- **States:** all 5 JD states · generate 503/422 INVALID_JD_INPUT/403 no FULL_AI ·
  request OPEN/FULFILLED/DECLINED — handled.
- **Gaps:** editor is plain textareas (one item/line; no rich text; hard >10 items); AI
  generate is one-shot (no streaming, no re-generate-with-prompt); version history is a
  frozen list (no diff/compare); request detail is thin (no link to resulting JD); no
  co-authoring.

## 8. Org Chart — `/org` (tabs: Tree · Positions · Vacancies) · Manager+ scoped (manage HRBP/Admin) · **OK**
- **Purpose:** view the reporting tree; manage positions; track vacancies.
- **Actions:** Create/Fill/Close position; Link/Unlink PUBLISHED JD; Reassign line;
  Create user.
- **Data:** tree nodes (user + headcount + vacancies); Position {status, filled_by,
  published_jd}; vacancies.
- **Components:** `OrgTreeView` (nested), positions `DataTable`, vacancies list, `PersonSheet`.
- **States:** scoped tree (Employee line / Manager subtree / tenant) · person 404
  out-of-scope · 409 illegal position · 422 REPORTING_CYCLE — handled.
- **Gaps:** tree has no connector lines / no search / no horizontal-scroll affordance;
  fill dialog has no in-dialog person search; vacancies are static (no time-to-fill); **no
  succession/readiness context on a vacancy** ("who can backfill?"); no org analytics
  (headcount by dept, bench depth).

## 9. Succession — `/succession` (Coverage · 9-box) · **Desktop only, MANAGEMENT-ONLY (employee → 404)** · **WEAK**
- **Purpose:** critical-role coverage + 9-box talent assessment + plan generate→publish.
- **Actions:** Mark critical role; Knowledge-risk; Add bench; Set readiness; Assess
  9-box; Generate plan; Add action-item; Publish; Enrich (Agent 4).
- **Data:** CriticalRole {criticality, knowledge_risk, coverage}; BenchCandidate
  {readiness}; NineBoxPlacement; SuccessionPlan {status, ranked_bench, coverage RED/AMBER/
  GREEN, red_flags, source, confidence}.
- **Components:** role card grid, `NineBoxGrid`, `RoleSheet`, assess dialog, `HitlBanner`.
- **States:** **employee → 404 everywhere** · Manager own-tier (out-of-tier 404) · plan
  PENDING (action-item + publish) · enrich 503 · coverage badge — handled.
- **Gaps:** role cards lack a successor-pool/bench-depth preview; 9-box cells cap at 5 +
  "+X" with **no click-to-drill**; no reassess from the grid; **no plan detail view**
  (only a "published" badge); no "covered in 3 years?" scenario; assess dialog gives no
  band guidance.

## 10. Career Roadmap — `/career` (tabs: My development · My team) · Manager+ (own = mobile) · **WEAK** ⭐ (new this run)
- **Purpose:** target role → advisory roadmap (skill gap + tiers) + per-tier progress +
  AI enrich.
- **Actions:** Choose/Change target (dialog); Generate (deterministic); Refresh; Enrich
  with AI (FULL_AI); Set tier progress.
- **Data:** DevelopmentRoadmap {tiers, skill_gap (band→band, weak_categories), source,
  advisory, confidence}; RoadmapProgress; live skill-gap.
- **Components:** tabs + roadmap card (badges + skill-gap panel + tier list with progress
  `Select`) + target dialog + `HitlBanner`.
- **States:** no-target (prompt) · ACTIVE roadmap · AI DRAFT · enrich 503 · Full-AI
  upgrade tooltip — handled.
- **Gaps:** target dialog lists JDs with no preview of role requirements; **no
  progress-to-target visualization**; tiers are abstract (no learning resources / mentors
  / next step); enrich is all-or-nothing (no merge/cherry-pick); ⚠ **no "accept AI
  roadmap → ACTIVE" endpoint** (it coexists as DRAFT — see frontend-spec §11); employee
  can't reach `/career` in the hub (Manager+ route) — own view is mobile.

## 11. Analytics — `/analytics` (Individual · Department · Calibration) · Manager+ (own = mobile) · **WEAK**
- **Purpose:** performance trend (individual), department cohort (suppressed <5),
  calibration 9-box.
- **Actions:** select employee/head/cycle; (export = JSON/text).
- **Data:** individual trend (per-cycle t/raw/risk/pace); department aggregate +
  `suppressed` + individuals[] (empty when suppressed); calibration grid.
- **Components:** tabs + selectors + simple bar charts + tables + `NineBoxGrid`.
- **States:** own trend · **department <5 → suppressed (aggregate only) + marker** ·
  Employee→department 403 · calibration HRBP/Admin only · cross-tenant empty — handled.
- **Gaps:** bars only (no sparkline, no goal line, no trend arrow); T-score axis 0–100 but
  scores can exceed 100 (confusing); risk distribution as badges not a stacked bar; no
  YoY/cohort comparison; no "what changed" narrative; no anomaly flags.

## 12. Admin · Users & Roles — `/admin/users` · ADMIN · **OK**
- **Purpose:** create users, set role/reporting-line/display-name, (de)activate.
- **Components:** `DataTable` + per-row dropdown + action dialogs.
- **States:** list · create form · 422 EMAIL_TAKEN/UNKNOWN_ROLE · 404 cross-tenant — handled.
- **Gaps:** no bulk/CSV import, no SCIM/SSO provisioning; no role-capability guidance; no
  onboarding-email/password-reset flow; reporting-line errors are technical; no visual
  reporting chain; no MFA-enforcement policy.

## 13. Admin · Tenant Config — `/admin/tenant` · ADMIN · **WEAK**
- **Purpose:** edit tenant settings.
- **Components:** a single raw-JSON textarea + Save/Reset.
- **States:** loading · JSON parse error · unsaved-changes warning — handled.
- **Gaps:** **raw JSON, no schema/fields/hints/defaults**; parse errors lack line numbers;
  unsaved indicator easy to miss. A premium config screen would be typed form fields.

## 14. Admin · Billing / Entitlements — `/admin/billing` · ADMIN · **OK**
- **Purpose:** view plan/seats/feature matrix; upgrade to FULL_AI; set seats.
- **Components:** `StatCard` grid + feature matrix + seats editor + upgrade modal
  (`upgrade-prompt`).
- **States:** STARTER (locked list) · FULL_AI · seats editor · upgrade modal · 403 non-admin
  — handled.
- **Gaps:** seat picker has no utilization/forecast ("50 active users, 10 seats left"); no
  per-feature description; upgrade modal has no pricing/terms/confirmation; no AI-usage/
  TokenLedger cost story surfaced here (it should be — the AI cost narrative).

## 15. Audit Console — `/audit` · HRBP + Admin · READ-ONLY · **OK**
- **Purpose:** immutable, filterable action history.
- **Components:** filter bar + `DataTable` (paginated). **No mutation controls (by design).**
- **States:** empty · filtered · paginated · 403 non-HRBP/Admin — handled.
- **Gaps:** filters lack a **date range**; raw `action` strings (not humanised); target id
  not linked to the artifact; justification often empty; no export; no anomaly/watch alerts.

## 16. Integrations — `/admin/integrations` · ADMIN · **WEAK**
- **Purpose:** configure Jira/Slack (enable + non-secret config + `secret_ref` NAME).
- **Components:** alert banner + a `Panel` per integration.
- **States:** not-configured (404) · enabled/disabled · 400 unknown kind · 403 non-admin
  — handled.
- **Gaps:** assumes the admin knows "env-var name"; thin help/examples; **no "test
  connection"**; no event log ("review approved → Jira comment"); Slack is channel-only.

## 17. AI Chat panel — global (Topbar "Ask AI") · all (entitlement `chat`) · **WEAK**
- **Purpose:** read-only, RBAC-bound natural-language assistant.
- **Components:** right `Sheet` + chat bubbles + input + 2 suggested questions.
- **States:** answer (read-only) · write-intent → blocked · 503 not-configured · 429 budget
  · feature-lock — handled.
- **Gaps:** **no streaming** (full-response wait feels slow); only 2 generic suggestions
  (no role/data-personalised prompts); no session history; "blocked"/scope not explained;
  reads as a placeholder, not a differentiator.

---

## Build-state summary (the redesign priority list)

**WEAK (Tier-1 redesign targets, ⭐):** Dashboard cockpits · Goals & KPIs · Career
roadmap. **WEAK (Tier-2/3):** Succession · Analytics · Tenant Config · Integrations ·
Chat panel. **OK (refine):** Reviews (arch strong, UX async/janky) · 360 Feedback ·
Approvals (designer weak) · JD Library · Org Chart · Users · Billing · Audit · Login.
**STRONG (preserve):** the shared component library, the kind-aware error handling, the
HITL architecture, RBAC/scope gating, the explicit state machines, the audit trail.

**No screens are functionally MISSING** (every contract screen exists and is wired —
confirmed by `scripts/smoke.py`, 47/47). The gap is **elevation, not coverage**: the
product is complete but reads as a utilitarian admin panel. The redesign is about
insight (vs data dumps), guided workflows (vs form-dump modals), and a premium visual
language — detailed in `ux-spec.md` (Phase 8).
