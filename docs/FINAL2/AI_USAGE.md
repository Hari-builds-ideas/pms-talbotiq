# AI usage and cost

Every LLM call already wrote a `TokenLedger` row through the gateway — agent, model,
prompt and completion tokens, timestamp. Nobody was reading that meter. `ai_usage` does.

```bash
docker compose exec web python manage.py ai_usage                 # last 30 days, by agent
docker compose exec web python manage.py ai_usage --days 7
docker compose exec web python manage.py ai_usage --by model      # or --by tenant
docker compose exec web python manage.py ai_usage --tenant acme
docker compose exec web python manage.py ai_usage --json          # machine-readable
```

```
AI USAGE — last 3 day(s), since 2026-08-05 10:16
  model                 calls      tokens     est. cost
  gemini-2.5-flash       5926       6.62M         $2.50
  chat                   1146      411.0k       $0.4460
  gemini-pro-latest        27       22.5k       $0.0903
  default                  16        2.3k       $0.0016
  TOTAL                  7115       7.06M         $3.04
```

## The cost is an estimate, and the report says so every time

Prices live in `settings.LLM_PRICES` — USD per **million** tokens, split input/output:

```python
LLM_PRICES = {
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-pro":       {"in": 1.25, "out": 10.00},
    ...
}
```

Override without a code change:

```bash
LLM_PRICES_JSON='{"gemini-2.5-flash": {"in": 0.30, "out": 2.50}}'
```

Published prices move, free tiers and volume discounts are invisible from here, and only
the provider's invoice is authoritative. A confident total from a table checked into a
repo would be a made-up number, so the report labels the figure an estimate wherever it
prints one.

Model ids are matched **longest-prefix first**, so `gemini-2.5-flash-002` is priced like
`gemini-2.5-flash` rather than silently costing nothing. A model with no price at all is
listed in a warning — counted in the token totals, absent from the money — because an
unpriced model quietly costing $0 is how a total starts lying.

Some rows record a logical tier (`chat`, `default`) rather than a concrete id, when the
provider's response did not name a model. Those resolve through `GEMINI_MODEL_MAP` before
pricing; on this repo's own ledger, not doing so understated spend by about 15%.

## What it cannot tell you

**Per-user spend.** The ledger has no user column. Usage is recorded per tenant, agent
and model, and answering "who spent this" would need a migration and a backfill. Stated
here rather than left for somebody to discover from an empty column.

## Keeping the number down

The three levers, in the order they matter:

- **The cheap model does the routine work.** `GEMINI_MODEL_MAP` sends chat and the
  function-calling agent to `gemini-2.5-flash`; only the human-read agents (review,
  feedback, succession, JD, career) get the stronger tier. In the run above that is the
  difference between $2.50 and $0.09.
- **The agent loop is capped** at 6 rounds and 12 tool calls per turn, so one question
  can never become an unbounded conversation with the provider.
- **The deterministic paths cost nothing.** Team scans, counts, rankings, the capability
  answer and "who have we been talking about" are answered from the database with no
  model call at all. `chat_agent` is 1,769 of 7,115 calls above — the agent is the
  minority path, by design.

For regression testing without spending anything, use the replay eval
(`scripts/agent_eval.py --replay …`), which re-runs a recorded run's tool calls against
the live database with no API key.
