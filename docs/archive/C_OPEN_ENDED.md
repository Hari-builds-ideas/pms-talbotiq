# C_OPEN_ENDED.md — answer open-ended, compositional questions

This is the payoff: the assistant answers questions we never explicitly coded, by composing the A tools
with backend aggregation. No new "intent" per question — the agent reasons about which tools to call.

## Question classes to make work (examples, not an exhaustive hardcoded list)
The point is generality, but verify these representative shapes end-to-end:

- **Improvement / trend:** "who improved most since last cycle?", "did Aarav get better?", "is my team
  trending up?" → compose get_cycle_scores / compute_improvement over the scoped team, backend computes
  deltas, model ranks-by-returned-number and explains.
- **Ranking:** "who's my top performer?", "rank my team by goal attainment", "who are my two weakest?" →
  rank_team(metric), backend sorts, model presents with the real numbers.
- **Risk / diagnosis:** "who's at risk and why?", "summarise my team's biggest risks" → team_aggregate +
  per-person overview/kpis, model synthesises a grounded summary citing the specific weak signals.
- **Readiness / judgement framed on data:** "who's ready for promotion?", "who should I focus on this
  week?" → compose scores + pace + KPIs; the model reasons over the REAL data and is explicit that it's a
  data-informed suggestion, not a decision — never inventing criteria or numbers.
- **Aggregation:** "how many of my reports are behind pace?", "what's my team's average score?" →
  team_aggregate, exact backend count/average.
- **Comparison:** "compare my two weakest performers", "how does Aarav compare to the team average?" →
  rank/aggregate + per-person, model presents both sides grounded.
- **Cross-entity / follow-up:** "of those, who also has an open review?" → compose over the previous
  result set (held in memory) + get_person_reviews.

## Rules
- The model chooses which tools to compose — do NOT add a bespoke hardcoded handler per question. The
  generality comes from good tools + a good system prompt, not from anticipating every phrasing.
- Every number in the answer comes from a backend compute/aggregate tool. The model never does the math.
- Judgement questions ("who should I promote?") answer from real data with reasoning, explicitly framed as
  a data-informed input to the human's decision — never a fabricated verdict, never invented criteria.
- All within scope: aggregates/rankings cover only the caller's permitted set; out-of-scope people are
  excluded, and asking about them is refused honestly.
- If the data genuinely can't answer it, say so plainly rather than guessing.

## System-prompt shaping
Add few-shot examples that teach composition: an improvement question → the sequence of tool calls →
grounded answer citing computed deltas. Teach the "no data / out of scope → say so" behaviour. Teach that
promotion/readiness answers are data-informed suggestions, not decisions.

## Tests
- "who improved most since last cycle" → routes through compute_improvement, correct top person vs a
  hand-checked fixture, cites the real delta.
- "how many of my reports are behind pace" → exact count vs fixture.
- "who's at risk and why" → grounded summary, only scoped people, real weak signals.
- "who's ready for promotion" → reasons over real data, framed as a suggestion, no invented numbers.
- an open-ended question about an OUT-OF-SCOPE person/team → refused honestly.
- a question with no supporting data → "no data", nothing invented.

## Done when
The assistant answers a broad range of open-ended, compositional questions by composing scoped tools with
backend math, grounded and scope-safe, without a hardcoded handler per question, tests green. Logged in
PROGRESS.md.
