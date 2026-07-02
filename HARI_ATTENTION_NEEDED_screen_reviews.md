# HARI_ATTENTION_NEEDED — Reviews recompose (File D, screen 1)

**Status:** NOT recomposed this run — deliberately. A deep visual recompose of a working, shipped
screen needs your eyes in the loop (the standing rule: *the agent can't see pixels; your eyes are the
gate*). Shipping it blind risks an invisible regression on a screen the demo uses. Handing you the
exact plan instead so it's a fast, one-screen-with-approval pass.

**Branch to cut when you do it:** `hari/reviews-recompose`.

## Target composition (Constitution Ch.11) — from `overnight/OVERNIGHT_D_HIGH_IMPACT_SCREENS.md`
- Hero: the **performance narrative** — the AI summary as ONE short human-tone paragraph.
- **Evidence timeline** (goals + KPIs + recognition + feedback moments, chronological).
- **Strengths / growth areas** as designed sections — **not raw `##` markdown** (the concrete win;
  mobile already does this, web doesn't).
- **Manager notes + employee reflection** side-by-side (respect existing HITL).
- **Development plan / next quarter.**
- Ratings last, or omitted if the flow allows — keep the real state machine intact.

## Non-negotiable (unchanged)
State machine (DRAFT → PENDING → APPROVED → FINALIZED) + all approval/HITL logic + every existing
button/endpoint. This is a **composition pass only**.

## The one concrete, testable sub-win to start with
`ReviewDetailPage` renders the AI body (`draft_body`/`final_body`) — render it as **designed sections**
by parsing the `##`/`**` headings into cards, instead of raw text. That's vitest-able (assert sections
render from a markdown body) and is the clearest quality gap. Do this first; it's low-risk.

**Files:** `frontend/src/features/reviews/` (ReviewDetailPage + the AI-summary render).
