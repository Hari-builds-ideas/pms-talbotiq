#!/usr/bin/env bash
#
# demo_ready.sh (OVERNIGHT_J3) — one command to confirm the PMS is demo-safe.
#
# Recreates the app containers on fresh code, seeds the rich ACME demo, waits for
# health, then runs the full end-to-end smoke (every surface as each role + the
# agent V2 plan→approve flow + the refusal beat). Prints a green/red summary and
# exits non-zero if anything a demo relies on is broken.
#
#   ./scripts/demo_ready.sh              # against http://localhost:8080
#   BASE=http://host:port ./scripts/demo_ready.sh
#
# The smoke uses the stack's configured LLM provider. The running stack uses live
# gpt-4o-mini (a few cheap calls for the agent plan). For a zero-spend, fully
# deterministic run, set LLM_PROVIDER=apps.ai.providers.FakeLLMProvider in .env
# before running (the fake planner splits multi-step asks deterministically).
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="${BASE:-http://localhost:8080}"
BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'

echo "${BOLD}▶ 1/4  Recreating web + celery-worker (fresh code + key)…${RESET}"
docker compose up -d --force-recreate web celery-worker >/dev/null

echo "${BOLD}▶ 2/4  Seeding the rich ACME demo data…${RESET}"
docker compose run --rm web python manage.py seed_demo_rich >/dev/null

echo "${BOLD}▶ 3/4  Waiting for the app to be healthy at ${BASE}…${RESET}"
ready=""
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/healthz" 2>/dev/null || true)
  if [ "$code" = "200" ]; then ready="yes"; break; fi
  sleep 2
done
if [ -z "$ready" ]; then
  echo "${RED}✗ App did not become healthy at ${BASE}/healthz — is the stack up?${RESET}"
  exit 1
fi

echo "${BOLD}▶ 4/4  Running the end-to-end smoke…${RESET}"
if BASE="${BASE}" python3 scripts/smoke.py; then
  echo ""
  echo "${GREEN}${BOLD}✓ DEMO READY${RESET} — safe to show:"
  echo "  ${DIM}• the six-step journey (login → dashboard → goals → reviews → feedback → recognition) as each role${RESET}"
  echo "  ${DIM}• the agent plan flow (Ask AI → Plan → approve a step) with session memory${RESET}"
  echo "  ${DIM}• the refusal beat (an injection plans only real actions and executes nothing)${RESET}"
  exit 0
else
  echo ""
  echo "${RED}${BOLD}✗ NOT DEMO READY${RESET} — a check above failed. Fix before demoing; do not merge review branches until green."
  exit 1
fi
