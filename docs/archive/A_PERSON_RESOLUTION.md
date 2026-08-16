# A_PERSON_RESOLUTION.md — one company-wide, scalable, DB-backed person resolver

**Problem:** person lookup for actions is team-scoped, so anyone outside the caller's reporting line is
"not found" — a manager can only recognise their own reports. And it must work at 5,000+ people, not just
the demo set. No hardcoded names anywhere.

## Build ONE canonical resolver used by the whole agent
Create a single function, e.g. `resolve_person(tenant, query_text, *, purpose)` in the agent/insight
layer, that EVERY intent uses. No intent may do its own ad-hoc name matching. It queries the database over
the whole tenant and returns a ranked result (or a disambiguation set, or nothing).

### Matching order (first non-empty wins)
1. **Exact full-name match** (case-insensitive, trimmed) → resolve immediately, NEVER disambiguate.
2. **Exact email match** → resolve.
3. **Unique first-name or last-name match** → resolve.
4. **Partial / contains match** (first+last in either order) → if one result, resolve; if several, offer a
   ranked disambiguation list (name + email + team) capped at ~5.
5. **Fuzzy match** for typos (bounded edit distance / trigram similarity) → suggest "did you mean…",
   scope-limited.
6. **Nothing** → honest "I can't find anyone named X in your company."

- Exact full-name match must NEVER trigger a "who do you mean?" prompt. This is a hard requirement.
- Disambiguation only for genuinely ambiguous input (real duplicate names), and it lists the candidates.

### Scale (must work at 5,000+)
- The query must be an INDEXED database query, not loading the table into Python. Add DB indexes on the
  name/email columns used for lookup if missing (additive migration).
- Cap result sets; never return thousands of rows to rank in memory. Use DB-side filtering (icontains /
  trigram / functional index) so 5,000 or 50,000 people perform the same.
- Confirm the query count is constant regardless of tenant size (no N+1, no full scan).

## Separate DIRECTORY lookup from DATA access — the key architectural fix
Two different questions, two different scopes:
- **Directory (name → person identity: id, name, email, team, role):** COMPANY-WIDE. Anyone in the tenant
  can be resolved. This is what recognition, feedback-requests, 1:1s, "do the same for X" use — because
  you can legitimately recognise or request feedback from a colleague in another team.
- **Performance data (goals, KPIs, reviews, cycle scores, pace):** PERMISSION-SCOPED, unchanged. Reading
  this still runs the existing access check (self / my-team / HRBP-unit / admin). Re-checked every turn.

`resolve_person(..., purpose=DIRECTORY)` returns identity for anyone in the tenant.
`resolve_person(..., purpose=DATA)` resolves identity company-wide BUT the caller then hits the existing
access gate before any performance data is read — out of scope → honest refusal, exactly as today.

**Resolving a name must never, by itself, reveal performance data.** Prove it with a test: an employee can
resolve a colleague's name for a directory action, but "how is <that colleague> doing?" is still refused.

## Remove all hardcoding
Grep the agent/insight code for any literal person names, seed-specific ids, or "Vera"/"Aarav"/"Mei"-type
special cases in the resolution or answer path. Remove them. Nothing may depend on specific seed people.

## Tests
- Exact full name resolves with no disambiguation, for a person OUTSIDE the caller's team.
- Email resolves.
- Typo ("Priya Niar") → fuzzy suggests Priya Nair.
- Real duplicate names → disambiguation list with emails.
- Unknown name → honest not-found.
- Directory resolve of an out-of-scope person succeeds; DATA read of that person is still refused.
- Performance is constant-query regardless of tenant size (assert query count on a large seed).

## Done when
One resolver, used everywhere, resolves any tenant person from the DB at any scale, exact-match never
disambiguates, directory vs data scopes are cleanly separated, no hardcoded names, all tests green.
Logged in PROGRESS.md.
