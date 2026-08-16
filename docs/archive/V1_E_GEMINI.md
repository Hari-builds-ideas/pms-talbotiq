# V1_E_GEMINI.md — wire Gemini as the AI provider (enterprise key)

**Why:** the company provided an enterprise **Gemini API key**. Today only an OpenAI provider is wired,
so there is no place to put the Gemini key and the app still uses OpenAI. Fix that: write a Gemini
provider, add a clear key placeholder, and use Gemini's best model for the best output.

## 1. Write a Gemini provider class
- Add a `GeminiProvider` (e.g. `apps/ai/gemini_provider.py`) implementing the same
  `apps.ai.providers.LLMProvider.generate` contract as `apps/ai/openai_provider.py` — same input/output
  shape, same JSON-mode handling, same error/degradation behavior (never raise, never fabricate).
- Use Google's Gemini API (the `google-generativeai` SDK or the REST endpoint). Add the dependency to
  requirements if needed.
- Register it so `LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider` selects it, exactly like the
  OpenAI/Groq providers. The agents, prompts, schemas, budgets, and gateway do NOT change — only the
  provider swaps.

## 2. Use Gemini's BEST model
- It's an enterprise key — configure the model map to use Gemini's strongest current model for the
  human-read agents (review / JD / career / feedback / succession), and a fast Gemini model for
  chat/default. Make each overridable by env var (mirror the existing `LLM_MODEL_*` pattern) so the exact
  model name can be changed without a code change. Pick the best-quality Gemini model available as the
  default for the human-read agents.

## 3. Add the key placeholder so Hari can just paste it
- Add to `.env.example` (and document in DEPLOY/handoff):
  ```
  # --- AI provider: Gemini (enterprise) ---
  LLM_PROVIDER=apps.ai.gemini_provider.GeminiProvider
  GEMINI_API_KEY=your-gemini-key-here
  # optional model overrides:
  # LLM_MODEL_REVIEW=<best-gemini-model>
  # LLM_MODEL_CHAT=<fast-gemini-model>
  ```
- Read the key from `GEMINI_API_KEY` (fall back to `LLM_API_KEY` if that's the existing generic seam).
- So Hari's whole action is: paste the key into `.env` next to `GEMINI_API_KEY`, restart web + worker,
  done. Document that one step plainly.

## 4. Verify it actually works
- After wiring, run a real end-to-end check on Gemini (a review draft or a chat plan) and confirm the AI
  responds through the gateway, is metered, and lands PENDING (HITL intact). Note the result in the
  report. If the key isn't present at build time, make the wiring correct and clearly document that Hari
  pastes the key and runs the one verification command.

## Rules
- Never commit the key. Only the placeholder goes in `.env.example`.
- Keep OpenAI + Groq providers intact (switchable by config) — just add Gemini alongside and make it the
  configured default for the demo.
- Keep tests green; add a provider test mirroring the OpenAI provider test.

## Done when
- `GeminiProvider` exists and is selectable, `.env.example` has the `GEMINI_API_KEY` placeholder + best
  model configured, OpenAI/Groq still switchable, and Gemini is verified working end to end (or the exact
  one-step verify is documented for Hari). Logged in PROGRESS_V1.md.
EOF
echo "E written"