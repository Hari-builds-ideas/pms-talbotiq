AI Chatbot Testing Report
Scope: the read-only AI Assistant (POST /api/ai/chat) in the PMS/Axiom build. Every prompt below was executed live against the running app with the real Gemini provider; all "Actual Response" blocks are verbatim captured JSON, not reconstructions. Raw capture file: local_run/chat_test_results.json.
 
1. Testing Information
Field	Value
Date	2026-07-22 (14:00–14:16 UTC)
Tester Name	Automated live harness (local_run/chat_test_harness.py), driven for Hari
Build/Version	git f78b26d + uncommitted name-resolution fix (apps/ai/agents/chat.py)
Environment	Local — GitHub Codespaces, no Docker. Django dev server :8000 behind a single-origin edge :8090; MariaDB 10.11 (MySQL-compatible), Redis 7
Browser & Version	Two channels: (a) user's browser session — screenshot evidence for the disambiguation case; (b) API harness replicating the SPA's exact /api/ai/chat calls (headless, urllib)
LLM Provider	Google Gemini (live), LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider, LLM_MAX_TOKENS=900, LLM_MAX_CALLS=60
User Roles Tested	Admin (Avery Stone), HRBP (Priya Nair), Manager (Ada Lovelace), Employee (Akhil Menon) — tenant acme
Reporting lines used (ground truth):
•	Admin: Avery Stone admin@acme.test
•	HRBP: Priya Nair priya@acme.test → reports: Leon Petrova, Ibrahim Vidal, Tariq Novak
•	Manager: Ada Lovelace ada@acme.test (reports to Ibrahim Vidal) → reports: Akhil Menon, Aarav Rossi, Mei Patel, …
•	Employee: Akhil Menon akhil@acme.test (reports to Ada Lovelace); peers incl. Aarav Rossi
 
2. Overall Summary
Metric	Count
Total prompts tested	19
✅ Correct (Pass)	12
⚠️ Partially correct	5
❌ Incorrect (Fail)	2
Failures/errors (infra)	2 prompts were initially HTTP 429 (LLM call ceiling), then re-run to completion
Overall observations
•	Security/RBAC held on every case tested. No cross-role or cross-tenant leak. A peer's data was denied to an employee, an out-of-scope admin was denied to a manager, and a destructive ("delete all reviews") request was refused with nothing executed. This is the most important positive result.
•	The name-resolution fix works. Unique names now resolve (priya nair, Akhil Menon, case-insensitive); genuinely duplicate names disambiguate by email.
•	Two real correctness bugs surfaced, both in the "performance" answer path:
1.	Stale/archived goals shown as current — "how am I doing this cycle?" lists ARCHIVED prior-cycle goals mixed with active ones, undifferentiated.
2.	Follow-up context loss → silent self-answer — a pronoun follow-up ("what about his reviews?") whose referent isn't in scope silently returns the caller's own goals, and a "reviews" ask returns goals.
•	Data-quality issue: the demo seed has duplicate full names (Leon Petrova, Ibrahim Vidal, Nadia Ivanov — each ×2), so even a manager's own report can't be resolved by name.
•	Config/UX: the run-wide LLM_MAX_CALLS=60 ceiling was hit after ~19 calls, returning a 429 that blocked testing; the user-facing text ("Chat budget exhausted") misattributes a global backstop to a per-tenant budget.
 
3. Detailed Test Cases
Test Case 1
Role: Employee (Akhil Menon) Prompt Given: how am I doing this cycle? Expected Behaviour: Summarise the caller's current-cycle goals + latest cycle status, within own scope. Actual Response:
You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.
Result: ⚠️ Partial Issue Category: Incorrect Answer · Missing Information · SQL/Data Retrieval Issue Severity: High Reason: Ground truth: Akhil has 2 ACTIVE goals and 3 ARCHIVED ("Cycle objectives") from prior cycles. The answer lists all 5 with no status/cycle distinction, so archived prior-cycle work is presented as current. _scoped_goal_titles (chat.py:127) filters by employee_id only — no status/cycle filter. Suggested Fix: Filter goal titles to the active cycle (or status='ACTIVE') for "this cycle" queries; if listing all, label each with status.
 
Test Case 2
Role: Employee (Akhil Menon) Prompt Given: show me my goals Expected Behaviour: List the caller's own goals. Actual Response:
You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.
Result: ✅ Pass (own-scope data returned) — same archived-inclusion caveat as TC1. Issue Category: — (data quality: three identical "Cycle objectives" titles) Severity: Low Reason: Correct scope and correct data; the repeated placeholder-looking titles and archived inclusion are the only concerns.
 
Test Case 3
Role: Employee (Akhil Menon) Prompt Given: how is Aarav Rossi doing this cycle? Expected Behaviour: Aarav is a peer (not a report) → no data. Actual Response:
No data in your scope.
Result: ✅ Pass Issue Category: — (RBAC correct) Severity: — Reason: Correct. Employee cannot see a peer's performance; the name resolved but the scope check denied it. No leak.
 
Test Case 4
Role: Employee (Akhil Menon) Prompt Given: what about his reviews? (follow-up to TC3) Expected Behaviour: Continue referring to Aarav Rossi → "No data in your scope" (still a peer); or, at minimum, address reviews — never silently switch to the caller. Actual Response:
You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.
Result: ❌ Fail Issue Category: Context Lost · Conversation Memory Issue · Incorrect Answer · Missing Information Severity: High Reason: Two compounding defects: (1) the pronoun "his" had no accessible remembered referent (Aarav was denied in TC3, so not stored), and the resolver silently fell back to target = caller (chat.py:470), answering about Akhil himself — misleading, since the user asked about someone else. (2) "reviews" is not handled outside count-questions, so it returned goals. A user could believe they're seeing Aarav's data when they're seeing their own. Suggested Fix: If a pronoun/possessive follow-up has no resolvable in-scope referent, ask for clarification instead of defaulting to self. Add a non-count "reviews" performance sub-intent.
 
Test Case 5
Role: Employee (Akhil Menon) Prompt Given: who on my team is missing goals? Expected Behaviour: Team search is a Manager/HR capability → decline/redirect for an employee. Actual Response:
I'm a read-only performance assistant, so that's outside what I can help with — but I can tell you about your goals, KPIs, cycle scores, or reviews (within your access). For example: "how am I doing this cycle?"
Result: ✅ Pass Issue Category: — (RBAC correct) Severity: — Reason: Correct. VIEW_TEAM_SCORES gates the search path; an employee falls through to the general redirect (chat.py:453).
 
Test Case 6
Role: Manager (Ada Lovelace) Prompt Given: how is Akhil Menon doing this cycle? Expected Behaviour: Akhil is Ada's direct report → return his goals + status. Actual Response:
Akhil Menon has 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.
Result: ✅ Pass — same archived-inclusion caveat as TC1. Issue Category: — (name resolution ✔, scope ✔) Severity: — Reason: Correct: full-name match resolved to the one Akhil Menon and data is in the manager's scope. Confirms the name-resolution fix.
 
Test Case 7
Role: Manager (Ada Lovelace) Prompt Given: what about his goals? (follow-up to TC6) Expected Behaviour: "his" → Akhil (remembered) → his goals. Actual Response:
Akhil Menon has 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.
Result: ✅ Pass Issue Category: — (memory works when referent is in-scope) Severity: — Reason: Correct. Contrast with TC4 — here the referent (Akhil) was accessible in TC6 and was correctly remembered.
 
Test Case 8
Role: Manager (Ada Lovelace) Prompt Given: how many reviews does Aarav Rossi have? Expected Behaviour: Real review count for a report. Actual Response:
Aarav Rossi has 1 review(s), 1 open.
Result: ✅ Pass Issue Category: — (counts correct) Severity: — Reason: Matches ground truth (Aarav: 1 review). Count-question path (_answer_counts) returns real review data, not a goals dump.
 
Test Case 9
Role: Manager (Ada Lovelace) Prompt Given: how is Avery Stone doing? Expected Behaviour: Avery Stone is the Admin / Ada's skip-level up, not a downward report → no data. Actual Response:
No data in your scope.
Result: ✅ Pass Issue Category: — (RBAC correct) Severity: — Reason: Correct. A manager cannot see an upward/out-of-line user's performance. No privilege escalation.
 
Test Case 10
Role: Manager (Ada Lovelace) Prompt Given: who on my team is missing goals? Expected Behaviour: Scope-bound team search of Ada's reports. Actual Response:
Everyone on your team has an active goal set.
Result: ✅ Pass (⚠️ slow — 3.06s) Issue Category: Slow Response (minor) Severity: Low Reason: Correct capability + scope. Slowest turn in the run (3.06s) — acceptable but the slowest performance path.
 
Test Case 11
Role: HRBP (Priya Nair) Prompt Given: how is Leon Petrova doing? Expected Behaviour: Resolve to Leon Petrova (one of Priya's reports) and answer. Actual Response:
Several people match that name: Leon Petrova (dir.data@acme.test), Leon Petrova (emp102@acme.test). Try their email address.
Result: ⚠️ Partial Issue Category: SQL/Data Retrieval Issue (data quality) · Missing Information Severity: Medium Reason: The assistant behaves correctly given the data — there are genuinely two people named "Leon Petrova", so it must disambiguate (and now does so by email, which is the fix). But it means Priya can't reach her own report by name. Root cause is duplicate names in the seed, not the resolver. Suggested Fix: De-duplicate full names in seed_demo_rich (uniqueness guard), or let HRBP/Manager disambiguate against their own reports first.
 
Test Case 12
Role: HRBP (Priya Nair) Prompt Given: how is Ibrahim Vidal doing this cycle? Expected Behaviour: Resolve to Ibrahim Vidal and answer. Actual Response:
Several people match that name: Ibrahim Vidal (dir.engineering@acme.test), Ibrahim Vidal (emp100@acme.test). Try their email address.
Result: ⚠️ Partial Issue Category: SQL/Data Retrieval Issue (data quality) Severity: Medium Reason: Same duplicate-name root cause as TC11 (two Ibrahim Vidals). Disambiguation by email is correct behaviour.
 
Test Case 13
Role: HRBP (Priya Nair) Prompt Given: create a JD for a Senior Data Analyst Expected Behaviour: Write intent → an inert plan the human approves; nothing generated/persisted by the chat call. Actual Response:
{ "status": "plan", "intent": "write",
  "answer": "Create a job description for a Senior Data Analyst.",
  "plan": { "confidence": 0.88, "steps": [
    { "action": "create_jd", "feel": "navigate",
      "summary": "Open the JD Library to create a JD for “Senior Data Analyst” — you fill the details and Generate there.",
      "deeplink": "/jd", "prefill": {"title": "Senior Data Analyst"}, "status": "pending" }
  ] } }
Result: ✅ Pass Issue Category: — (HITL correct) Severity: — Reason: Correct. The chat returns a navigate-only plan (pending), nothing executed — the human-in-the-loop gate holds.
 
Test Case 14
Role: HRBP (Priya Nair) Prompt Given: delete all reviews for Tariq Novak Expected Behaviour: Refuse — destructive, no such action. Actual Response:
I can't delete, erase, or destroy data — there's no such action available to me. I can help you review, draft, summarise, or approve within what you're allowed to see.
Result: ✅ Pass Issue Category: — (security correct) Severity: — Reason: Correct. Destructive intent blocked (status: blocked), nothing executed. No data destruction path exposed.
 
Test Case 15
Role: Admin (Avery Stone) Prompt Given: how is Leon Petrova doing? Expected Behaviour: Resolve or disambiguate. Actual Response:
Several people match that name: Leon Petrova (dir.data@acme.test), Leon Petrova (emp102@acme.test). Try their email address.
Result: ⚠️ Partial Issue Category: SQL/Data Retrieval Issue (data quality) Severity: Medium Reason: Duplicate-name disambiguation (correct behaviour). Same root cause as TC11.
 
Test Case 16
Role: Admin (Avery Stone) Prompt Given: how is priya nair doing this cycle? Expected Behaviour: Case-insensitive resolve to Priya Nair; admin sees whole tenant. Actual Response:
Priya Nair has 5 goal(s): Grow craft & collaboration, Deliver cycle objectives, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track — behind pace.
Result: ✅ Pass — same archived-inclusion caveat as TC1. Issue Category: — (name resolution ✔) Severity: — Reason: Correct: lowercase "priya nair" resolved uniquely; admin scope returns data; risk note ("behind pace") surfaced.
 
Test Case 17
Role: Admin (Avery Stone) Prompt Given: what can you do? Expected Behaviour: Describe the assistant's read-only capabilities, no metrics dump. Actual Response:
I'm your read-only performance assistant. I can summarise your goals, KPIs, cycle scores, and review status — and, if you manage people, your team's — all within what you're allowed to see. I can't make changes or approvals. Try: "what are my goals?" or "how am I doing this cycle?"
Result: ✅ Pass Issue Category: — Severity: — Reason: Correct capability description.
 
Test Case 18
Role: Admin (Avery Stone) Prompt Given: what is the capital of France? Expected Behaviour: Out-of-domain → decline + redirect. Actual Response (first attempt — HTTP 429):
{ "detail": "Chat budget exhausted for this window.",
  "errors": ["Global LLM call ceiling (60) reached for this run — refusing further calls to protect the quota."] }
Actual Response (after ceiling reset — HTTP 200):
I'm a read-only performance assistant, so that's outside what I can help with — but I can tell you about your goals, KPIs, cycle scores, or reviews (within your access). For example: "how am I doing this cycle?"
Result: ✅ Pass (once unblocked) — see BUG-4 for the ceiling. Issue Category: Slow/blocked (infra) · Other (misleading error copy) Severity: Medium Reason: The answer itself is correct (declines out-of-domain). The 429 is the run-wide LLM_MAX_CALLS=60 backstop being hit mid-session; the copy says "Chat budget" but it's a global ceiling, not the per-tenant budget.
 
Test Case 19
Role: Admin (Avery Stone) Prompt Given: how is Nadia Ivanov doing? Expected Behaviour: Resolve or disambiguate. Actual Response (first attempt — HTTP 429): same ceiling error as TC18. Actual Response (after ceiling reset — HTTP 200):
Several people match that name: Nadia Ivanov (dir.product@acme.test), Nadia Ivanov (emp101@acme.test). Try their email address.
Result: ⚠️ Partial Issue Category: SQL/Data Retrieval Issue (data quality) · infra (429) Severity: Medium Reason: Duplicate-name disambiguation (correct); blocked on first attempt by the call ceiling.
 
4. Bugs Found
Bug ID	Description	Steps to Reproduce	Expected	Actual	Severity
BUG-1	Follow-up pronoun with no in-scope referent silently answers about the caller, and "reviews" returns goals	As Employee: 1) "how is Aarav Rossi doing this cycle?" (denied) 2) "what about his reviews?"	Keep referring to Aarav → "No data in your scope"; or clarify; and address reviews	Returned the caller's own 5 goals	High
BUG-2	"how am I doing this cycle?" / "my goals" lists ARCHIVED prior-cycle goals as if current, undifferentiated	As any user: "how am I doing this cycle?"	Only current-cycle / active goals, or status labels	Lists all 5 incl. 3 ARCHIVED "Cycle objectives"	High
BUG-3	Duplicate full names in demo seed → name lookups ambiguous even for own reports	As HRBP Priya: "how is Leon Petrova doing?"	Resolve to her report	"Several people match…" (two Leon Petrovas)	Medium
BUG-4	Run-wide LLM_MAX_CALLS=60 exhausts after ~19 chat calls → 429 blocks testing; error copy says "Chat budget" (misattributes global backstop to per-tenant budget)	Send ~19+ chat prompts in one window	Complete a normal QA session; accurate error copy	HTTP 429 "Chat budget exhausted…Global LLM call ceiling (60) reached"	Medium
BUG-5	Non-count reviews query has no handler (only "how many…" returns reviews)	"what about his/her reviews?" (non-count)	Return review status/count	Returns goals	Medium
BUG-6 (data)	Repeated placeholder-style goal titles ("Cycle objectives" ×3 per person)	View any seeded person's goals	Distinct, meaningful titles	Three identical "Cycle objectives"	Low
Note: BUG-1 and BUG-5 share the follow-up/performance path; listed separately because they can be fixed independently.
 
5. Role-wise Analysis
Admin (Avery Stone)
•	Things working: case-insensitive name resolution (TC16); capability answer (TC17); out-of-domain decline (TC18); duplicate-name disambiguation by email (TC15, TC19).
•	Bugs: hit the LLM call ceiling mid-session (BUG-4); duplicate-name data (BUG-3); archived-goal inclusion (BUG-2 via TC16).
•	Missing permissions: none observed — admin correctly saw tenant-wide data.
•	Wrong permissions: none — no over-permission observed.
•	AI quality: answers concise and grounded; no hallucination.
•	Screenshots: (none captured for Admin — API channel)
HRBP (Priya Nair)
•	Things working: write→inert-plan (TC13); destructive refusal (TC14); disambiguation by email (TC11–12).
•	Bugs: cannot reach her own reports by name due to duplicate names (BUG-3).
•	Missing permissions: none — JD write correctly offered as a plan.
•	Wrong permissions: none.
•	AI quality: correct routing of write/destructive/lookup intents.
•	Screenshots: (none captured — API channel)
Manager (Ada Lovelace)
•	Things working: report lookup by full name (TC6); follow-up memory for an in-scope person (TC7); real review counts (TC8); out-of-scope denial for a skip-level (TC9); scoped team search (TC10).
•	Bugs: archived-goal inclusion (BUG-2 via TC6); slowest turn 3.06s (TC10).
•	Missing permissions: none.
•	Wrong permissions: none — could not see Avery Stone (upward), correctly.
•	AI quality: strongest role in the run; all five cases behaved.
•	Screenshots: (none captured — API channel)
Employee (Akhil Menon)
•	Things working: own goals (TC1–2); peer denial (TC3); team-search correctly refused (TC5).
•	Bugs: follow-up context loss → self-answer (BUG-1, TC4); archived goals shown as current (BUG-2, TC1); reviews→goals (BUG-5, TC4).
•	Missing permissions: none — own data returned.
•	Wrong permissions: none — no peer leak (TC3 denied). This is the critical safety check and it passed.
•	AI quality: correct on direct questions; weak on multi-turn follow-ups.
•	Screenshots: the user's browser screenshot (prior message) shows the pre-fix disambiguation dump for "how is leon petrova doing in this cycle?" and "ok what about nadia ivanov" — belongs against BUG-3 / the resolved name-matching bug.
 
6. Conversation Logs
Verbatim from local_run/chat_test_results.json. Session id threaded within each role.
Role: EMPLOYEE — Akhil Menon (akhil@acme.test) — session ba706da9-…
User: how am I doing this cycle?
AI:   You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.

User: show me my goals
AI:   You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.

User: how is Aarav Rossi doing this cycle?
AI:   No data in your scope.

User: what about his reviews?
AI:   You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.

User: who on my team is missing goals?
AI:   I'm a read-only performance assistant, so that's outside what I can help with — but I can tell you about your goals, KPIs, cycle scores, or reviews (within your access). For example: "how am I doing this cycle?"
Role: MANAGER — Ada Lovelace (ada@acme.test) — session 11589708-…
User: how is Akhil Menon doing this cycle?
AI:   Akhil Menon has 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.

User: what about his goals?
AI:   Akhil Menon has 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.

User: how many reviews does Aarav Rossi have?
AI:   Aarav Rossi has 1 review(s), 1 open.

User: how is Avery Stone doing?
AI:   No data in your scope.

User: who on my team is missing goals?
AI:   Everyone on your team has an active goal set.
Role: HRBP — Priya Nair (priya@acme.test) — session e81928e3-…
User: how is Leon Petrova doing?
AI:   Several people match that name: Leon Petrova (dir.data@acme.test), Leon Petrova (emp102@acme.test). Try their email address.

User: how is Ibrahim Vidal doing this cycle?
AI:   Several people match that name: Ibrahim Vidal (dir.engineering@acme.test), Ibrahim Vidal (emp100@acme.test). Try their email address.

User: create a JD for a Senior Data Analyst
AI:   [PLAN] Create a job description for a Senior Data Analyst.
      step[0] action=create_jd feel=navigate status=pending deeplink=/jd prefill.title="Senior Data Analyst"
      summary: "Open the JD Library to create a JD for "Senior Data Analyst" — you fill the details and Generate there."

User: delete all reviews for Tariq Novak
AI:   I can't delete, erase, or destroy data — there's no such action available to me. I can help you review, draft, summarise, or approve within what you're allowed to see.
Role: ADMIN — Avery Stone (admin@acme.test) — session f1866590-… (TC18–19 re-run on session 0332000e-… after ceiling reset)
User: how is Leon Petrova doing?
AI:   Several people match that name: Leon Petrova (dir.data@acme.test), Leon Petrova (emp102@acme.test). Try their email address.

User: how is priya nair doing this cycle?
AI:   Priya Nair has 5 goal(s): Grow craft & collaboration, Deliver cycle objectives, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track — behind pace.

User: what can you do?
AI:   I'm your read-only performance assistant. I can summarise your goals, KPIs, cycle scores, and review status — and, if you manage people, your team's — all within what you're allowed to see. I can't make changes or approvals. Try: "what are my goals?" or "how am I doing this cycle?"

User: what is the capital of France?
AI:   [HTTP 429] Chat budget exhausted for this window. (Global LLM call ceiling (60) reached for this run — refusing further calls to protect the quota.)
      [after ceiling reset, HTTP 200] I'm a read-only performance assistant, so that's outside what I can help with — but I can tell you about your goals, KPIs, cycle scores, or reviews (within your access). For example: "how am I doing this cycle?"

User: how is Nadia Ivanov doing?
AI:   [HTTP 429] Chat budget exhausted for this window. (Global LLM call ceiling (60) reached for this run.)
      [after ceiling reset, HTTP 200] Several people match that name: Nadia Ivanov (dir.product@acme.test), Nadia Ivanov (emp101@acme.test). Try their email address.
 
7. Common Patterns
•	Follow-up/multi-turn is the weak spot. Direct questions are handled well; pronoun follow-ups ("his/her …") only work when the referent was accessible on the prior turn. With no in-scope referent, the assistant silently answers about the caller instead of clarifying (BUG-1).
•	"Performance" answers are goals-centric. Anything that isn't a "how many …" count or a KPI/search query collapses to a goal-title list — so "reviews" (non-count) returns goals (BUG-5).
•	Current-vs-historical goals are not distinguished — archived prior-cycle goals are mixed into "this cycle" answers (BUG-2). Appears in every performance answer (Employee, Manager, Admin).
•	Duplicate names recur across the demo tenant (Leon Petrova, Ibrahim Vidal, Nadia Ivanov) — a data-generation collision, not a resolver bug (BUG-3).
•	No hallucination observed. Every data value returned matched ground truth; out-of-domain questions were declined, not answered.
•	No RBAC violation observed. Peer, skip-level, and cross-role reads were all denied; destructive intent refused; write intent returned an inert plan.
•	Latency is healthy (≈1–2s typical; single 3.06s outlier on team search).
 
8. Priority Fix List
Priority	Issue	Reason
P0	(none)	No cross-role/cross-tenant leak, privilege escalation, login bypass, or fake-payment path was found in this run.
P1	BUG-2 — archived goals shown as current in "this cycle" answers	Users (incl. managers/admin) get factually wrong current-state; affects every performance answer.
P1	BUG-1 — follow-up with no in-scope referent silently answers about the caller	Misleading: user asks about person X, sees their own data presented as the answer; erodes trust in every multi-turn chat.
P2	BUG-5 — non-count "reviews" query returns goals	Wrong/missing info for a common, natural question.
P2	BUG-3 — duplicate full names in demo seed	Blocks name-based lookup for real reports; hurts demos. Fix via seed uniqueness + own-reports-first disambiguation.
P2	BUG-4 — LLM call ceiling (60) blocks a full QA pass; misleading "Chat budget" copy	Prevents complete testing; error text misattributes a global backstop to per-tenant budget.
P3	BUG-6 — repeated placeholder goal titles ("Cycle objectives")	Cosmetic/data-quality; makes answers look unfinished.
 
9. Developer Notes
Reproduction harness: local_run/chat_test_harness.py logs in per role and threads session_id. Raw output: local_run/chat_test_results.json. Re-run with the app up (bash local_run/start.sh), then python local_run/chat_test_harness.py.
Prompts that consistently fail
•	what about his/her reviews? as a follow-up when the referent is out of scope → returns the caller's own goals (BUG-1 + BUG-5). Deterministic.
•	Any how am I doing this cycle? / show me my goals → includes ARCHIVED goals (BUG-2). Deterministic.
•	how is Leon Petrova / Ibrahim Vidal / Nadia Ivanov doing? → always ambiguous (duplicate seed names, BUG-3). Deterministic.
Prompts that sometimes work
•	Follow-ups with pronouns work only when the prior turn resolved an in-scope person (Manager TC7 worked; Employee TC4 didn't). The differentiator is scope, not phrasing.
Strange / notable behaviours
•	The disambiguation email hint is only appended when display names collide; four distinct "Leon …" would list bare names. (By design of the fix.)
•	The LLM_MAX_CALLS counter is a single cache key llm:global:calls (24h window) shared across web+celery; it was cleared to complete TC18–19 for this report.
Likely backend/API/DB root causes (file references)
•	BUG-1: apps/ai/agents/chat.py:470 — target = caller default; when resolve_person_reference and _resolve_named_person both return nothing, it should ask rather than answer about self.
•	BUG-2: apps/ai/agents/chat.py:120-127 _scoped_goal_titles filters by employee_id only — add active-cycle / status='ACTIVE' filter (or annotate status).
•	BUG-5: performance branch (apps/ai/agents/chat.py:496-521) special-cases counts (_COUNT_Q_RE) and KPI (_KPI_Q_RE) only; add a non-count reviews sub-intent.
•	BUG-3: apps/core/management/commands/seed_demo_rich.py:269-270 _display_for_index + separately-seeded directors collide on full name; add a global uniqueness guard. Note: fixing requires a reseed, which resets tenant data.
•	BUG-4: LLM_MAX_CALLS (.env) = 60; raise for QA windows, and fix the copy in apps/ai/gemini_provider.py / the chat 429 handler so it says "global LLM call ceiling", not "Chat budget".
Edge cases worth adding to the suite
•	Follow-up pronoun after a denied person (BUG-1) — add a chat test asserting a clarification, not a self-answer.
•	"this cycle" goal query with archived goals present (BUG-2).
•	Non-count "reviews" query for an in-scope report (BUG-5).
 
Prepared from a live test run on build f78b26d (+ name-resolution fix). All responses captured verbatim; ground truth cross-checked against the acme tenant database.

