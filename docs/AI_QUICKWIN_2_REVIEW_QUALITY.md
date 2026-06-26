# AI quick win 2 — review bias/quality flag (report + UI follow-up spec)

Built overnight, **backend-only + additive** (D36). An ASSISTIVE check over a draft review's text — it
flags possible recency bias, harsh wording, missing evidence, or vagueness. It **never blocks** the
review and **persists nothing**; it's advisory.

## What shipped (backend)

- **Agent** `apps/ai/agents/review_quality.py::flag_review_quality(user, text)` — via the `LLMGateway`.
  Schema = `{flags: list}`; each flag `{type, note}` where type ∈ recency_bias | harsh_wording |
  missing_evidence | vague | other. An empty list means "clean".
- **Endpoint** `POST /api/ai/review-quality` (`ReviewQualityView`) — body `{"text": str}` → `{status,
  flags, confidence}`. Gated by `MANAGE_REVIEWS` (reviewers, Manager+); AI-throttled. 200 / 503 / 429;
  400 on empty text. Stateless — the caller passes the draft text they're editing; nothing is saved.
- **Prompt** `agent_config.py::"review_quality"`. Reuses `MANAGE_REVIEWS`; no auth/SSO/shared/deploy/nav/
  matrix change.

## Verification

- **[test]** `apps/ai/tests/test_review_quality.py` (3): advisory flags returned (FakeLLMProvider); no
  provider → `not_configured`; endpoint gated to reviewers (manager 200, employee 403), empty-text 400.
  Full backend suite green; frontend untouched + green. **No live OpenAI.**

## UI follow-up (for review — NOT built overnight)

1. `shared`: `aiApi.reviewQuality = (text) => unwrap<{flags:{type:string;note:string}[]}>(api.post(
   "/ai/review-quality", { text }))` + a `ReviewQualityFlag` type.
2. In the **review editor** (existing `reviews` screen — a do-not-touch module overnight), add a "Check
   with AI" button beside the draft body that calls the endpoint and shows the flags as dismissable,
   non-blocking advisory chips (the review can still be submitted regardless). Touching that screen needs
   your review since it's an existing passing module.
