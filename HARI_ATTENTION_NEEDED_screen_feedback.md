# HARI_ATTENTION_NEEDED — Feedback / 360 recompose (File D, screen 3)

**Status:** NOT recomposed this run — deliberately (visual recompose needs your eyes). Plan handed over.

**Branch to cut:** `hari/feedback-recompose`.

## Current
`frontend/src/features/feedback/FeedbackPage.tsx` uses an accessible Radix **`Tabs`**: For me · My 360 ·
Cycles (Manager+) · Summaries to release (HRBP+).

## Target composition — from `overnight/OVERNIGHT_D_HIGH_IMPACT_SCREENS.md`
- **In-screen pill sub-nav** instead of loud tabs: `For me · From me · Cycles`.
- **"For me"** — asks + released summaries as sections (not two identical tables).
- **Released summaries** as designed theme sections (strengths / development / patterns) — **no raw
  markdown**; keep HITL release intact.
- **"Cycles" (HR only)** — the existing table as list-rows with clear state, reviewer counts, one
  primary action per row.
- Employees never see cycles/manage — respect existing RBAC.

## Why it wasn't blind-shipped
The safe way to get "pills" is to **restyle the existing `Tabs` primitive** (keep its keyboard a11y /
roving-tabindex — don't hand-roll pills and lose it). That restyle is a visual-taste call best made
with your eyes on it. The RBAC gating (`atLeast("MANAGER")` / `atLeast("HRBP")`) must stay exactly.

**Files:** `frontend/src/features/feedback/FeedbackPage.tsx` (+ the tab components it renders).
