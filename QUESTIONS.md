# QUESTIONS.md — open questions for Hari (never blocking)

> Each entry: the question · why it matters · the default taken to continue ·
> what choosing differently would change. Defaults are recorded in DECISIONS.md.

---

### Q1 (BUILD_1/1.4) — Two list endpoints left unpaginated by design; chart lazy-load deferred

**Question.** Three large-tenant items were scoped OUT of BUILD_1 because the
clean fix is a UI/UX change, not an ORM one — confirm these belong in BUILD_5:
1. `GET /api/admin/users` (admin user table) — paginate + add server-side search
   + page controls (UI work).
2. `GET /api/cycles/<id>/scores` (team scores) — add a scoped single-employee
   score lookup so `ReviewEvidence` doesn't fetch the whole cohort.
3. Org chart expand-on-demand lazy-loading for the HRBP/Admin full-tenant view.

**Why it matters.** For a 2k-employee tenant these three still ship more rows
than strictly needed to the broadest-scope users. None is a correctness or
isolation risk today (the tree is scope-bounded; the dashboard no longer pulls
the user list).

**Default taken (to continue).** Left as-is for BUILD_1; the headline anti-pattern
(dashboard downloading the user list) was fixed server-side. Recorded as BUILD_5
(WEB_UX) candidates. Choosing differently (do them now) would mean UI changes
beyond an ORM build's remit. See DECISIONS.md D3.

---

### Q2 (WEB_COE/W1) — Should a tenant's SAML IdP be allowed to drive (sync) the user's role?

**Question.** When a tenant configures a SAML `role_map`, the SP maps the IdP's
role/group attribute to one of our Roles and **JIT-syncs it onto the user's DB role**
(RBAC enforces the DB role, so this is what makes the mapping actually take effect),
writing an `identity.saml.role_synced` audit row. Do you want IdP-driven role sync at
all, and if so should the synced role be **capped so it can never exceed** the
admin-provisioned role (no IdP-driven privilege escalation)?

**Why it matters.** It's the federation trade-off: IdP-authoritative roles are standard
enterprise SSO, but they let a (tenant-administered) IdP attribute elevate someone to
Admin. RBAC enforcement itself is unchanged either way; this is only about where the
*role value* originates.

**Default taken (to continue).** Conservative + opt-in: with an **empty `role_map`
(the default) the IdP drives NO roles** — the Admin Hub stays authoritative, identical
to the OIDC path. Sync only happens when a tenant explicitly fills `role_map`, and an
absent/unknown attribute never escalates. See DECISIONS.md D25; proven in
`apps/identity/tests/test_saml.py`.

**Choosing differently** (e.g. add a rank-cap so a mapped role can't exceed the
provisioned one, or disable DB sync entirely and keep role mapping advisory) is a small,
localised change in `apps/identity/saml/service.py::_resolve_and_sync_role`.

**✅ RESOLVED (2026-06-22).** Hari: keep sync opt-in (empty role_map = no sync) **and add
the rank-cap** so a synced role can NEVER exceed the admin-provisioned role — no
IdP-driven privilege escalation. Implemented + tested; see DECISIONS.md D27.

---

### Q3 (RW_BUILD_1) — `PRODUCT_REWEIGHTING_PLAN.md` referenced but not present in the repo

**Question.** The paste + RW_BUILD_1 reference `PRODUCT_REWEIGHTING_PLAN.md` (Decisions 3 & 4) as the
product-direction source, but only `docs/NEW/{PASTE_THIS_RW.md, RW_BUILD_1..3}` exist — no plan file.
**Why it matters.** The plan would be the authoritative per-role nav + the demote list. **Default taken:**
executed from the explicit spec inside `RW_BUILD_1_NAV_AND_RBAC.md` (Phase 1.2 per-role nav, Phase 1.3
demote list) + `PASTE_THIS_RW.md`, cross-checked against the real RBAC matrix. **Different choice would
change:** if the plan specifies a different per-role nav, adjust `nav.ts` minRoles + sections accordingly.

### Q4 (RW_BUILD_1) — Plan's "HR set" includes Settings/Integrations, but the backend gates them Admin-only

**Question.** The plan gives HR/HRBP a "Settings" + an Advanced group that includes integrations/tenant
config; the backend gates `MANAGE_INTEGRATIONS`/`MANAGE_TENANT_CONFIG`/`MANAGE_ENTITLEMENTS`/
`MANAGE_USERS_ROLES` to **Admin only**. **Why it matters.** Showing them to HRBP would be a dead link
(403). **Default taken:** kept those four **Admin-only** (Administration group); HRBP's Advanced group is
succession/org/JD/audit (all HRBP-capable). **Different choice would change:** if HRBP should manage
tenant settings/integrations, that's a backend RBAC change (widen the capability to HRBP) — out of
RW_BUILD_1's "no new backend" scope; would need its own decision.

### Q5 (RW_BUILD_1) — Intra-screen action gating on the newly employee-exposed screens

**Question.** Exposing Goals/Reviews/Feedback to employees means a few manager-only actions sit inside
those screens (e.g. Goals "New goal"/"Recompute"; Feedback "Cycles" tab). **Why it matters.** Leaving
them clickable for employees is a shown-then-denied *within* a screen. **Default taken:** gate just those
obvious actions to Manager+ in Phase 1.2 (the employee primary read + own-actuals stay); a full
intra-screen action-gating sweep across every screen is deferred to the finish-the-web track.
**Different choice would change:** a dedicated pass to role-gate every action/button app-wide.

### Q6 (RW_BUILD_1) — Manager succession visibility (dashboard entry point removed)

**Question.** The re-weighting demotes succession to an HR/Admin "Advanced" area "not visible to
employee/manager" (RW_BUILD_1 Phase 1.3). The manager dashboard previously had a "Coverage gaps"
stat + a Succession-risk tile linking into `/succession`. **Why it matters.** The backend DOES grant
managers `VIEW_SUCCESSION` (own report tier), so managers *can* use succession — but the plan keeps it
off their everyday surface. **Default taken:** removed the manager cockpit's succession stat + tile
(and the nav item) per the explicit Phase 1.3 text; **backend access is unchanged** (a manager who
deep-links to `/succession` still gets their tier). **Different choice would change:** if managers
should keep coverage visibility, re-add the "Coverage gaps" StatCard + `SuccessionRiskTile` to
`ManagerCockpit` (trivial revert) and/or add Succession back to the Team nav group at `minRole: MANAGER`.

### Q7 (RW_BUILD_2) — Recognition company values are a fixed list (per-tenant customisation deferred)

**Question.** The brief says recognition cites "the tenant's configurable company values"; I shipped a
**fixed default list** (`apps.recognition.models.COMPANY_VALUES`) validated on create. **Why it matters.**
A tenant may want its own values. **Default taken:** fixed list now (a per-tenant values model is
over-building for the MVP and not needed to demo the feature). **Different choice would change:** add a
small per-tenant `CompanyValue` config (admin-managed) and validate against it instead of the constant.

### Q8 (RW_BUILD_3) — Check-in optional extras deferred (AI summary, cadence nudge, custom questions)

**Question.** The outline lists optional check-in extras: a manager-side AI summary + suggested
follow-ups (HITL), a cadence-configurable "due" nudge reusing the nudge surface, and rotating custom
questions. **Why it matters.** They add polish but aren't the core loop. **Default taken:** shipped the
core (write / read-scoped / respond / goal-pull / priorities) and deferred the extras — the AI summary to
RW_BUILD_4/5 (keeps RW_BUILD_3 LLM-free per the quota rule), the cadence-nudge + custom questions as
follow-ups. **Different choice would change:** add an AI summary endpoint via the LLMGateway (proposed,
HITL, FakeLLMProvider in tests), a per-tenant cadence setting + a beat-driven "due" nudge, and a
rotating-question config.

### Q9 (RW_BUILD_4) — Assistant action catalogue (started with one)

**Question.** The outline suggests 1–2 safe action types; I shipped one (`approve_goals`) behind an
extensible registry. **Why it matters.** More proposable actions = more admin-work saved. **Default
taken:** one well-built action + the full safety machinery (propose→confirm→execute→audit, re-checked at
execution); "keep it small and safe first, then extend." **Different choice would change:** add registry
entries (e.g. "nudge reports with no progress in 30 days", "remind people with no check-in this week"),
each mapping to an existing audited, permission-checked endpoint, with its own confirm card.
**Update (overnight QW5):** shipped the 2nd action — `approve_reviews` — proving the registry takes
another action without loosening the contract. It reuses `state_machine.approve` (the human
ReviewApproveView's exact call: re-checks APPROVE_REVIEW + row scope + HITL state, audits once), so the
assistant and human paths can't drift. See `docs/AI_QUICKWIN_5_ASSISTANT_ACTIONS.md`.

### Q10 (RW_BUILD_5) — AI quick wins: shipped the goal-writer; the others are follow-ups

**Question.** The outline lists five quick wins; I shipped (a) the goal-writer. **Why it matters.** Each
of the rest reduces admin work too. **Default taken:** one well-built, gateway-routed, HITL win + the
machinery others can reuse (the outline says "build whichever you value most first; each small +
self-contained"). **Different choice would change:** add (b) 1-on-1/meeting summary, (c) review
bias/quality flag, (d) stale-goal nudge (fits the RW_BUILD_4 propose-confirm registry), (e) NL search —
each via the LLMGateway, HITL, with FakeLLMProvider tests. Also: decide which entitlement pack gates the
goal-writer (currently capability + gateway-budget, not pack-gated — see D35).

**✅ DONE (overnight 2026-06-26/27).** Shipped all five backend-only + additive (D36), each its own
green commit + per-feature `docs/AI_QUICKWIN_*.md`: (1) meeting summary `cc4d3dc`, (2) review-quality
flag `b253628`, (3) stale-goal nudge `eca8aeb`, (4) NL search `b8b290f`, (5) 2nd assistant action
`approve_reviews`. **Still open for your call:** (i) the entitlement-pack gating above; (ii) the UI
wiring for each (specs in the docs — they touch the shared layer / nav, which were off-limits overnight).
