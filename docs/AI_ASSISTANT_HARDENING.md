# AI Assistant — Reliability Hardening

Findings from a real tester pass (`testing_answers.md`, 4 roles) plus an adversarial
sweep, with the fixes applied. Everything below is verified **live** against the real
demo DB and locked by tests (`apps/ai/tests/`, 265 passing).

The assistant is **read-only** and **RBAC-bound**: every answer goes through the same
scope check (`actor_can_access`) a direct API read would. None of these fixes widen
access — they make the *behaviour at the boundary* correct and honest.

## Defects found & fixed

| # | Symptom (tester) | Root cause | Fix |
|---|---|---|---|
| 1 | Goals listed `Cycle objectives ×3` filler | old build listed goals across ALL cycles | goals scoped to the **active cycle** + de-duplicated (already shipped; data verified clean) |
| 2 | **Ask about someone out of scope, then "what about his reviews?" → your OWN data** | a pronoun resolved to the most-recent *accessible* ref, skipping the just-denied person back to the caller (self) | a pronoun now binds to the **most-recent person mentioned** (any scope); if that person is out of scope it stays **refused**, never falls back to self |
| 3 | "how is Leon Petrova doing?" → *"Several people match: Leon Petrova"* (says several, lists one) | identical display names collapsed in a `set` | disambiguation shows **`Name (email)`** for colliding names |
| 4 | "what about his reviews?" answered with **goals** | any performance query defaulted to a goals summary | a review/feedback follow-up now answers **reviews/feedback** |
| 5 | 3rd-person pronoun with nothing grounded → dumped the caller's own goals | pronoun fell through to self | now asks **"I'm not sure who you mean — tell me their name or email"** |
| 6 | Hard **`429` for 24h** after 60 calls ("assistant broke") | fixed 24h call-ceiling window | ceiling is now a **rolling window** (`LLM_CALL_WINDOW_SECONDS`, default 1h) that self-heals; message says when it resets; testing cap raised 60 → 400 |

## Guardrails (unchanged, re-verified)
- **Never widens access.** A stored session reference grants nothing — every read
  re-checks the caller's scope. Grounding an out-of-scope person only lets us keep
  *refusing consistently*, never reveal their data.
- **Honest refusals.** Out-of-scope → "you don't have access … only an admin or HR
  can see everyone" and, for a manager, **the list of people they CAN ask about**.
- **Prompt injection / SQL / gibberish** ("ignore your instructions…", "'; DROP
  TABLE…") → the safe read-only redirect, never a data dump.

## Verified live (real Gemini + demo DB)

**Employee (akhil):** self goals ✓ · ask about out-of-scope Aarav → refusal ✓ ·
"what about his reviews?" → **still refused (Aarav)** ✓ · "how is he doing?" →
**still refused (Aarav)** ✓ (previously leaked akhil's own data).

**Manager (ada):** report's goals ✓ · "what about his reviews?" → the report's
review count ✓ · out-of-scope Hugo → refusal + team list ✓ · pronoun after Hugo →
**stays on Hugo** (refused), not the earlier accessible report ✓.

**Admin:** two real "Leon Petrova" → disambiguation **with emails** ✓ · pronoun with
no referent → "not sure who you mean" ✓.

## How to re-test
1. `docker compose up` → open http://localhost:8090, log in (see `docs/TESTING_GUIDE.md`).
2. As an **employee**: ask about a teammate on another team, then "what about his
   reviews?" — you should stay refused, never see your own data.
3. As a **manager**: ask about a direct report, then "what about his reviews?".
4. As **admin**: ask about a name shared by two people — you get both, with emails.
