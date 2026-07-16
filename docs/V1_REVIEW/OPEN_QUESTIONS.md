# OPEN_QUESTIONS — product decisions & known unknowns (so they don't leave with the author)

Decisions that are PRODUCT calls (not code), plus accepted-for-v1 risks. Each: current behavior + the
decision needed.

## Security / auth (decisions for the deployment owner)
1. **Refresh token in localStorage** — current: 7-day rotating+blacklisted refresh in
   `localStorage["pms.refresh"]` (access is memory-only; revoked on logout AND on password reset).
   Decide: accept for v1, shorten `JWT_REFRESH_DAYS`, or fund the http-only-cookie/BFF rework (v2).
2. **No per-account login lockout** — only per-IP `THROTTLE_ANON=100/min`. Decide: add django-axes /
   an account counter before broad exposure.
3. **Manager self-approval** — the server permits a manager with capability+scope to approve a review
   where THEY are the subject (OWN scope passes). Decide: block self-approval in the state machine, or
   accept (some SMEs allow it). UI mirrors the server today.
4. **Gemini data egress** — employee performance data flows to Google's API for AI features. Needs the
   business/legal sign-off (or an approved endpoint via `LLM_PROVIDER`).

## Product scope
5. **UI stricter than server (lost capabilities, not bugs):** org chart + Analytics-individual +
   approvals tracker are nav-gated Manager+ though the read capabilities are EVERYONE (scoped);
   `GoalUpdates` add is own-only in UI though a manager-in-scope may POST; JD nav is HRBP while
   `request_jd` is Manager+. Decide per item whether to widen the UI in v2 (widening = product choice,
   deliberately not made unilaterally in this pass).
6. **Notifications** — Slack-only, silent no-op without a webhook; no in-app center. Decide the v2
   shape (in-app model + feed vs email digests vs both). This is the biggest UX gap for real tenants.
7. **v1 hidden features** (nine-box/calibration, succession, career, raw tenant config, T-score
   displays) — re-enable steps in `docs/handoff/V1_VS_V2.md`. Decide which return in v2 and for whom.
8. **Per-tenant LLM keys / entitlement-priced AI** — today one deployment-wide key + per-tenant call
   budgets. Decide if tenants bring their own keys (data governance) in v2.
9. **Goal status thresholds** — On-track ≥70% / Behind 40–69 / At-risk <40, pure-% (no time pacing).
   Decide whether v2 adds cycle-time pacing like Lattice.

## Rough edges (documented, non-blocking)
- JD "Generate" 422s (by design) on a DRAFT with no inputs snapshot — confirm the UI flow always fills
  inputs first (QA ◻ item).
- Chat plan cards rehydrate as text summaries after a reload (interactive checklist state isn't
  re-fetched) — acceptable; note for v2.
- Check-ins/audit have the lightest backend test coverage of the core loops.
- `HTTPLLMProvider` is an inert stub — remove or implement in v2.
