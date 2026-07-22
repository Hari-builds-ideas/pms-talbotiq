# AI Assistant — Intelligence Report (milestone: increment 8)

Branch: `hari/agent-intelligence-v2`. The read-only, RBAC-bound chat assistant has
gone from keyword→canned-reply to a memory-aware, reasoning assistant that phrases
its answers in natural language via Gemini — **without ever widening access**.

## What it can now do

| Capability | Example | Behaviour |
|---|---|---|
| **Memory + coreference** | "how is Akhil?" → "does he need help?" | "he" resolves to Akhil; a pronoun binds to the last person mentioned, re-checked for scope every turn |
| **Diagnosis (reasoned + phrased)** | "does she need help?" | reasons over real cycle status/pace + weakest KPI vs target, phrased naturally by Gemini, grounded only in permitted data |
| **Status** | "how is Mei Patel?" | REASONED + Gemini-phrased (cycle status + weakest KPI vs target), grounded — no longer a flat list |
| **Team scan** | "who's behind on my team?" | scoped to the caller's OWN reports; "at risk" (rating) vs "behind" (pace); capped list |
| **Team comparison** | "who's doing best/worst on my team?" | ranked top/bottom 5 by cycle score |
| **Two-person compare** | "how are Akhil and Mei doing?" / "compare X and Y" | each resolved + scoped independently, both diagnosed; a mixed pair answers the in-scope one and names the other as out-of-access |
| **Aggregation** | "how many of my reports are behind?" | a count summary, not a name dump |
| **Capability** | "what can you do?" | tailored to the caller's role/scope |
| **Ambiguity** | "how is Leon Petrova?" (two exist) | lists both with emails; "the first one" then resolves the pick |
| **Name typos** | "how is Anastaesia doing?" | scope-limited "did you mean Anastasia?" (never a name out of scope) |
| **Out of scope** | employee asks about a peer | honest refusal + who they CAN ask about; never leaks |

## Before → after (real, live)

- **"does he need help?"** (after "how is Akhil Menon doing")
  - before: *"Akhil has 2 goal(s): …"* (ignored the question)
  - after: *"Akhil Menon is currently on track and keeping pace this cycle… his
    'Roadmap features delivered' KPI is at 90% of target, the only area slightly
    below expectations. Overall, Akhil does not appear to need additional help."*
- **"who is doing best on my team?"**
  - before: *"I couldn't find anyone by that name"* (dead)
  - after: *"Your top performers this cycle: 1. Akhil Menon (On track); 2. Mateo
    Santos…"*
- **"how many of my reports are behind?"** → *"Of your 14 report(s): 5 on track, 3
  at risk, 9 behind pace."*
- **"what can you do?"** → role-specific (manager hears team insight; employee hears
  "I can only see your own data").

## Safety (unchanged, re-verified)

- **Read-only**; every data read goes through `actor_can_access` + tenant-scoped
  managers. The LLM phrasing layer is handed ONLY the caller's permitted facts and a
  strict "never invent data / never mention anyone else" prompt; on any error/no-key
  it falls back to the deterministic grounded draft. It cannot reach past RBAC.
- Employee→peer, manager→other-team, cross-tenant: all refused, no leak.
- Prompt injection / SQL / gibberish / empty input → safe redirect, never a dump.
- Self-test harness: **32/32 checks** across employee/manager/HRBP/admin. Backend:
  **276 AI tests** green.

## Remaining weaknesses (next increments)

- No explicit **"go back to the first person"** / re-refer an earlier-grounded person
  by role ("my report") after switching topics.
- **Aggregation over two named people** ("how many goals do X and Y have") routes to
  diagnosis, not counts.
- Phrasing adds one LLM call per reasoned answer (latency/quota) — flag-gated
  (`AGENT_INTEL_LLM_PHRASING`); the self-test harness is therefore quota-heavy (reset
  `llm:global:calls` before each run).
- Self-test suite (36–39 checks) is solid but not exhaustive; keep growing it.

## How to test it yourself (morning)

1. `docker compose up`; open http://localhost:8090 (demo logins in `docs/TESTING_GUIDE.md`).
2. As **manager** `ada@acme.test`: "how is Akhil Menon doing?" → "does he need help?"
   → "who's behind on my team?" → "who's doing best?" → "how many are behind?".
3. As **employee** `akhil@acme.test`: "do I need help?"; then try "how is Aarav Rossi
   doing?" and "what about his reviews?" — you should stay refused, never see other
   data.
4. Run the harness anytime: `python scripts/agent_intel_suite.py` (exit 0 = all good).
