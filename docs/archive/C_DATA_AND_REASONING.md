# C_DATA_AND_REASONING.md — real data, real reasoning, scope-safe, no templates

The assistant must answer with the SPECIFIC information asked for, reasoned from live database data —
never a generic template, never a canned "here's what I can do" when a real answer was requested.

## 1. Retrieve real data through scoped queries
For any data question ("how is X", "who's behind", "compare X and Y", "how many of my reports are at
risk"), fetch from the database through the EXISTING permission-scoped queries, resolved via the A
resolver + the data-access gate. The person is found company-wide; the DATA is returned only if the caller
is allowed to see it, otherwise an honest scope refusal.

## 2. Reason, don't template
- The answer must reflect the actual numbers/state pulled: cycle status, pace, the specific weak KPI and
  its attainment %, which goal, etc. "Aarav is on track but behind pace — Roadmap features delivered is at
  49% of target" — grounded in that person's real row, not a fixed sentence.
- Comparisons produce a genuine side-by-side of both people's real data with a reasoned conclusion.
- "Does X need help?" reasons over risk + pace + weakest KPI and answers yes/no with the reason.
- Aggregations ("how many of my reports are behind?") compute over the real team set.
- Use the LLM (Gemini) to PHRASE the grounded facts naturally, but it may only use data actually fetched;
  never invent. If a value is missing, say so.

## 3. Never answer a real question with the capability blurb
The generic "I'm your read-only assistant, I can summarise…" text is ONLY for a genuine "what can you do?"
question or a truly unparseable message — never as a fallback when the user asked a real, answerable
question. If a question is answerable, answer it. If a name didn't resolve, say that specifically (Bug in
A). Do not deflect to the capability list.

## 4. Scope safety (unchanged, re-verified)
- Data access re-checked every turn; out-of-scope performance data refused honestly.
- Directory actions (recognition etc.) remain company-wide.
- No fabrication; injection/social-engineering still refused.

## Tests
- "how is <person>" returns their real status + specific KPI, for an in-scope person.
- "compare A and B" returns both, reasoned.
- "does X need help?" reasons correctly.
- aggregation counts match the real team data.
- a real answerable question NEVER returns the capability blurb.
- out-of-scope data still refused; no fabrication.

## Done when
Answers are specific and reasoned from live data, the capability blurb only appears for capability
questions, scope holds, no fabrication, tests green. Logged in PROGRESS.md.
