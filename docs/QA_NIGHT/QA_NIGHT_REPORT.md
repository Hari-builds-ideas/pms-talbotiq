# QA_NIGHT_REPORT — overnight QA-hardening pass

**Date:** 2026-07-14 (overnight) · **Scope:** the machine-checkable half — live HTTP
probes, RBAC/negative/isolation/integrity checks, bug fixes, regression tests. The
**visual/UX half is deliberately left for Hari** (list at the bottom).

## Headline

Two passes. **246 live HTTP checks green at end of night; 5 bugs found → all fixed + regression-tested.**

- **Pass 1 — 173 checks**: sweep A 63/63 · B 63/63 · C 18/18 · cross-tenant 29/29 ·
  Phase-2 49/49. Plus a `/security-review` of the branch.
- **Pass 2 — 73 checks** over the modules pass 1 skipped: sweep D
  (succession/career/1:1/notifications) 28/28 · sweep E (JD/review/feedback/approvals
  **lifecycle**) 34/34 · cross-tenant on new modules 11/11.
- **5 bugs found → fixed + regression-tested + committed** (details in
  [BUGS_FOUND.md](BUGS_FOUND.md)):
  - `8c0bce5` **HIGH** — invite flow let an HRBP mint a full ADMIN (privilege escalation; found by `/security-review`).
  - `9881297` **HIGH** — repeat finalize bypassed an in-flight approval route.
  - `f5cc539` **MEDIUM** — JD non-object save-draft body → 500 on submit/export (pass 2).
  - `478e3d2` **MEDIUM** — non-numeric KPI actual → 500 + ghost audit row.
  - `15c5dad` **LOW** — recognition accepted a 50k-char message.
- **2 low-severity observations written up, not changed** (403/404 consistency policy;
  a one-pass audit-before-write review) — see BUGS_FOUND.md.
- RBAC/HITL/tenant-isolation/audit **untouched by the fixes** — each fix *tightens* a gate.

## What was tested (per module)

### Pass 2 modules (previously uncovered)

| Module | Role matrix | Negative/edge | Cross-tenant |
|---|---|---|---|
| Succession (management-only) | ✅ employee shut out everywhere; VIEW=Mgr+, register/override/publish=HRBP+ | malformed/empty payloads clean 400 | ✅ 404 by id, no foreign rows |
| Career roadmaps | ✅ own-scope all; can't set/read a colleague's | target needs exactly one jd/position → 422 | ✅ |
| One-on-ones | ✅ participants-only object rule | — | ✅ |
| JD lifecycle (save-draft/submit/approve/versions/export/generate/request) | ✅ MANAGE=HRBP+, request=Mgr+, view=all | **BUG-N5 fixed**; out-of-order transitions clean 4xx | ✅ |
| Review sub-endpoints (comments/assessments/reject/calibration) | ✅ comments=own-review scope, calibration=HRBP+ | reject-without-reason 422, bad parent 4xx | — |
| Feedback extras (summary queue/requests/decline/received) | ✅ summary approve=HRBP+ | unknown id → clean 404 | — |
| Approvals lifecycle (workflow CRUD/step act) | ✅ configure=HRBP+, act=Mgr+ | invalid mode 400, unknown step 404 | — |

### Pass 1 modules

| Module | Role matrix | Negative/edge | Integrity | Cross-tenant |
|---|---|---|---|---|
| Login/auth (+ tokens, lockout) | ✅ 4 roles + globex | garbage/expired tokens, malformed body, wrong tenant, enumeration | revocation enforced at refresh | ✅ |
| Goals & OKRs | ✅ own/team/BU scopes | weights, titles, junk values, unknown ids, malformed JSON | create→read-back, actual→recompute, updates timeline | ✅ |
| Reviews (HITL) | ✅ | out-of-order transitions, double submit/approve/finalize | full DRAFT→EDITING→PENDING→APPROVED→FINALIZED walk + timeline | ✅ |
| 360/Feedback | ✅ | self-rating, give-after-close, employee-open | open/give/close reflected on read | ✅ |
| Check-ins | ✅ | duplicate week, missing fields, malformed | create→team view→respond | ✅ |
| Recognition | ✅ | self-kudos, bad value, bad emoji, oversized | give→feed→react | ✅ |
| Employees/org | ✅ (export scope verified) | absurd search, self-manager cycle | — | ✅ |
| JD library | ✅ (employee = PUBLISHED-only) | out-of-order approve, employee create | create→read-back | ✅ |
| Analytics | ✅ (dept ≠ employee; calibration = HRBP+) | missing cycle param, unknown employee | — | — |
| Approvals | ✅ | unknown step, param-less routes | step-approve integration exercised via reviews | — |
| Audit console | ✅ (HRBP/Admin only) | POST/DELETE → 405 (INSERT-only holds) | rows present for tonight's actions | ✅ |
| Admin/settings/billing | ✅ | SQLi-shaped search, bad email/role/plan/status | plan flip → flags flip | — |
| AI agent | ✅ schema role-filtered, session isolation | destructive ask refused, colleague ask → no leak | write→inert plan→approve gate; **Open-navigation fix holds live** | ✅ chat can't resolve foreign people |
| Phase-2 (profile/invites+resend/sessions/plans) | ✅ 49/49 re-run | (see VERIFY_PHASE2.md) | ✅ | ✅ |

## Automated-test delta (self-checking from now on)

Coverage audit of the priority flows: goal create/save, KPI record→update, review
draft→PENDING→finalize (incl. the HTTP walk), 360 states, invite accept (+resend),
plan gating, agent Open-navigation, chat session isolation, cross-user step approve —
**all already had pytest coverage**; no redundant tests added (simplicity rule).
**4 new regression tests added tonight** (one per fixed bug + earlier resend):
`test_second_finalize_cannot_bypass_an_in_flight_route`,
`test_non_numeric_actual_is_400_and_writes_nothing`,
`test_oversized_message_rejected`,
`test_resend_reissues_a_working_link_and_is_pending_only`.

Backend suite at end of night: **1480 passed, 0 failed** (full clean run) ·
demo_ready smoke **57/57 — DEMO READY**. (One mid-night suite run showed mass
failures — root-caused to demo_ready force-recreating containers concurrently
with the run, not to code; the isolated re-run is fully green.)

## Commits tonight

| Commit | What |
|---|---|
| `478e3d2` | fix(goals): non-numeric KPI actual is 400, not 500 + no ghost audit |
| `15c5dad` | fix(recognition): enforce 1000-char message cap in the service |
| `9881297` | fix(reviews): repeat finalize cannot bypass an in-flight approval route |
| (docs) | QA_NIGHT progress + this report + BUGS_FOUND |

## Leftover state (deliberate)

- **GLOBEX tenant** (`globex` — gadmin/gmgr/gemp@globex.test, demo password) stays in the
  dev DB as the standing cross-tenant probe fixture. Harmless; delete if you prefer.
- Probe artifacts in ACME (a QA goal for Vera, one walked review, probe kudos/check-ins)
  were cleaned by reseed; the one pre-fix corrupted review's stale route was CANCELLED.
- Probe scripts live in the session scratchpad (`sweep_a/b/c/xt.py`, `phase2_verify.py`) —
  disposable; the durable regression coverage is in pytest.

## What needs YOUR manual/visual check tomorrow

Machine checks can't see pixels. Walk `docs/HARI_FULL_TEST.md` (the full checklist) — in
particular the parts I could NOT verify:

1. **Layout/rendering per role** — sidebar, dashboards, tables, empty states, dark mode,
   mobile-width behavior of the goals cards + chat panel.
2. **Chat panel ergonomics** — resize handle feel, persistence across navigation + reload,
   the Open button/deeplink chip *visually* landing on the right page.
3. **Toasts & live updates** — KPI actual updating the bar without reload, review state
   chip flipping after approve/finalize, invite "re-sent" toast + link box.
4. **Anything with real email UX** — the reset/confirm/invite mails render fine in a real
   client (dev uses console backend; content verified, rendering not).
5. **The demo story on stage conditions** — "make a review for Vera" → approve → Open,
   on live Gemini, with the projector-size window.
6. **Charts** — analytics trend/calibration render sensibly (data verified server-side;
   axes/labels/legends not).

## Suggested next (not started, your call)

- Decide the 403-vs-404 policy (OBS-N1) and align the few OWN-check endpoints.
- One-pass review that every audit `record(...)` sits after input validation (OBS-N2).
- Optionally fold sweeps A/B/C/XT into a repeatable `scripts/qa_sweep.py` if you want them
  runnable by QA (tonight's versions are scratchpad scripts).
