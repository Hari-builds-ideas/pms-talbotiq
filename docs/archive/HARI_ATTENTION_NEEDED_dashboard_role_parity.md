# HARI_ATTENTION_NEEDED — dashboard role parity (File C)

Three `hari` branches recompose the HRBP / Admin / Employee dashboards to the **manager mockup's
`DashboardKpiCard` hero row** — killing the "old StatCard grid under a new header" cliff flagged in
`PROJECT_STATE_JULY3.md §2`. Each is **green** (`tsc` + `eslint` + `vite build` + `vitest 107`), on
**real endpoints only**, **no new endpoints, no fabricated data**, honest empties preserved. **None is
visually verified** (my eyes can't see pixels) — that's your gate.

| Branch | Role | KPI row (all real) | Login to review |
|---|---|---|---|
| `hari/dash-hrbp` | HRBP | Summaries to release · Coverage gaps · Pending approvals · At-risk people · Critical roles | `priya@acme.test` |
| `hari/dash-admin` | Admin | Active users · Seats used (progress) · Plan · Critical roles · Total users | `admin@acme.test` |
| `hari/dash-employee` | Employee | My goals · My performance (T-score+risk) · Feedback requests · Review status | `emp006@acme.test` |

Password: `Passw0rd!demo`. Each branch has its own `REVIEW_NOTES.md` with the click-path + deviations.

## Recommended cherry-pick order
1. **`hari/dash-employee`** — most-seen role; lowest risk (4 clean personal KPIs).
2. **`hari/dash-hrbp`** — highest-value for the HR persona in the demo.
3. **`hari/dash-admin`** — nice seats-progress touch.

All three edit only their own function in `frontend/src/features/dashboard/cockpit-roles.tsx`, so they
cherry-pick independently. If you take more than one, expect a trivial import-line merge (each branch
prunes different now-unused lucide icons) — resolve by keeping the union of icons each remaining role
still uses.

## Deviation (all three)
Only the **KPI hero row** was recomposed (that's where the cliff was). The lower-zone tiles were left
as-is — they're already real, sectioned cards. A deeper lower-zone recompose (HR coverage heatmap,
admin audit stream styling) is a follow-up if you want full mockup fidelity below the fold.
