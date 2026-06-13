# V0 Handoff — your step-by-step checklist

A plain checklist for building the **Admin Hub** in v0 from the brief, then bringing
it back here to wire to the real API. (No React is written until the wiring step,
and Claude Code does that part.)

---

## (a) Design research in ChatGPT — and what to bring back
Use ChatGPT (or any design tool) for **look-and-feel only**, not data/logic (the data
contract is already nailed down in `V0_ADMIN_HUB_BRIEF.md`). Ask it for:
- 2–4 reference products/dashboards to emulate (e.g. modern HR/SaaS admin consoles) —
  collect **screenshots**.
- A short **visual language**: palette, typography, density (data-dense vs roomy),
  table vs card patterns, how to show status chips / steppers / empty states.
- Optional: a one-paragraph **brand voice** for microcopy.

**Bring back:** a short paragraph + a few screenshots/links you'll paste as the
"DESIGN DIRECTION" in v0. Do NOT bring back data shapes, field names, or API ideas
from ChatGPT — those come ONLY from the brief (so the result stays wire-compatible).

## (b) What to paste into v0
1. Paste the **entire** `docs/frontend-contract/V0_ADMIN_HUB_BRIEF.md`.
2. Replace the **`DESIGN DIRECTION: [...]`** placeholder at the top with your
   references/screenshots/brand from step (a).
3. (Optional) Iterate in v0 screen-by-screen — but keep telling it: **mock data only,
   match the field names + enum values + pagination envelope in the brief, no real API
   calls.** Don't let v0 invent new fields or rename enums.

## (c) What to download from v0
- Download the **full project export** (the Next.js/React + Tailwind + shadcn/ui
  source), not just snippets.
- Make sure the **mock data module** (the `lib/mock/...` the brief asks for) is in the
  export — that's what Claude Code swaps for real `fetch` calls.

## (d) Drop it into the repo
- Put the download in a new top-level **`frontend/`** folder:
  `pms-talbotiq/frontend/` (the Django backend stays untouched at the repo root).
- Don't commit `node_modules/` — confirm `frontend/node_modules/` is gitignored (add
  it to `.gitignore` if needed). Commit the source + `package.json`/lockfile.
- It's fine to commit it as-is first ("v0 Admin Hub export") so there's a clean
  baseline before wiring.

## (e) Come back to Claude Code to wire it
Tell Claude Code: *"the v0 Admin Hub is in `frontend/` — wire it to the real API."*
Claude will then, per the **WIRING NOTES** (§6 of the brief):
- replace the mock `fetchMock()` layer with a real API client (base URL + the
  `Authorization: Bearer` header + token refresh);
- map each screen's mock to its real endpoint + method (the §6 table);
- implement real auth/login + MFA + the role-gated routing;
- enforce the cross-cutting rules against live responses (the 4xx/5xx handling,
  feature-flag locking, HITL affordances, pagination envelope, management-only gating);
- run the screens against the live Docker backend and fix any shape drift.

Nothing else is needed from you between (d) and (e) — the brief + WIRING NOTES give
Claude everything to connect the download to the backend.
