#!/usr/bin/env bash
#
# qa_handover.sh — ONE command to fully test the PMS before handing it to QA.
#
# What it does, in order:
#   1. Preflight  — Docker up? web healthy? serve the SPA on :8090 (recreate the
#                   helper if missing).
#   2. Baseline   — reseed the rich ACME demo + run the demo smoke (57 checks).
#   3. Fixture    — ensure the GLOBEX second tenant exists (cross-tenant probes).
#   4. Verify     — run scripts/qa_verify.py: every module × 4 roles, negatives,
#                   cross-tenant, account features, the 5 fixed bugs, data hygiene.
#   5. Clean      — reseed once more so QA inherits pristine demo data.
#
# Then it prints the verdict and points you at the visual/UX checklist
# (docs/TESTING_GUIDE.md) for the half a script can't see.
#
#   ./scripts/qa_handover.sh                       # against http://localhost:8090
#   BASE=http://host:port ./scripts/qa_handover.sh
#   QA_SKIP_AI=1 ./scripts/qa_handover.sh          # skip the live-Gemini checks (fast)
#
set -uo pipefail
cd "$(dirname "$0")/.."

BASE="${BASE:-http://localhost:8090}"
FRONTEND_IMAGE="pms-talbotiq-frontend:latest"
HELPER="pms-frontend-8090"
NETWORK="pms-talbotiq_default"
BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
step() { echo "${BOLD}▶ $*${RESET}"; }
die()  { echo "${RED}${BOLD}✗ $*${RESET}"; exit 1; }

# ── 1. Preflight ──────────────────────────────────────────────────────────────
step "1/5  Preflight — Docker, web + nginx health, SPA on :8090"
docker info >/dev/null 2>&1 || die "Docker daemon isn't running. Start Docker Desktop, then re-run."
docker compose up -d >/dev/null 2>&1 || true   # frontend-1 (:8080) may conflict; harmless — we use :8090

# Ensure the :8090 SPA helper (nginx edge → web) is serving the latest built image.
if [ -z "$(docker ps -q -f "name=^${HELPER}$")" ]; then
  echo "  ${DIM}(re)starting the ${HELPER} helper on :8090…${RESET}"
  docker rm -f "${HELPER}" >/dev/null 2>&1 || true
  docker run -d --name "${HELPER}" --network "${NETWORK}" -p 8090:80 "${FRONTEND_IMAGE}" >/dev/null \
    || die "could not start the :8090 helper — is the frontend image built? (docker compose build frontend)"
fi

# Health via the host through nginx (proxies /healthz → web) — proves BOTH are up.
# This is exactly how demo_ready.sh checks, and it needs no curl inside the container.
ready=""
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/healthz" 2>/dev/null || true)
  if [ "$code" = "200" ]; then ready="yes"; break; fi
  sleep 2
done
[ -n "$ready" ] || die "app not healthy at ${BASE}/healthz. Check: docker compose logs web"
echo "  ${GREEN}app up at ${BASE}${RESET}"

# ── 2. Baseline reseed + demo smoke ──────────────────────────────────────────
step "2/5  Baseline — reseed demo + run the demo smoke (57 checks)"
if ! BASE="${BASE}" ./scripts/demo_ready.sh; then
  echo "${YELLOW}⚠ demo_ready smoke reported a failure — continuing to the full verify so you see everything.${RESET}"
fi

# ── 3. Cross-tenant fixture ──────────────────────────────────────────────────
step "3/5  Fixture — ensure the GLOBEX cross-tenant tenant exists"
docker compose exec -T web python manage.py shell < scripts/qa_seed_globex.py || \
  echo "${YELLOW}⚠ could not seed globex — cross-tenant checks will SKIP (not fail).${RESET}"

# ── 4. Full automated verify ─────────────────────────────────────────────────
step "4/5  Verify — full automated API suite (every module, all roles)"
set +e
BASE="${BASE}" QA_SKIP_AI="${QA_SKIP_AI:-}" python3 scripts/qa_verify.py
VERIFY_RC=$?
set -e

# ── 5. Clean up (fresh demo data for QA) ─────────────────────────────────────
step "5/5  Clean — reseed so QA inherits pristine demo data"
docker compose run --rm web python manage.py seed_demo_rich >/dev/null 2>&1 || \
  echo "${YELLOW}⚠ final reseed failed — run: docker compose run --rm web python manage.py seed_demo_rich${RESET}"

echo ""
if [ "$VERIFY_RC" -eq 0 ]; then
  echo "${GREEN}${BOLD}✓ AUTOMATED HANDOVER TEST PASSED${RESET}"
else
  echo "${RED}${BOLD}✗ AUTOMATED HANDOVER TEST FOUND FAILURES${RESET} — see the list above; fix, then re-run."
fi
cat <<EOF

${BOLD}Next — the manual/visual half a script can't see:${RESET}
  Open ${BASE} and walk ${BOLD}docs/TESTING_GUIDE.md${RESET} (layout, dark mode, toasts,
  live spinner resolving, chart labels, the demo story on screen). Log in with tenant
  ${BOLD}acme${RESET} / password ${BOLD}Passw0rd!demo${RESET} as admin@ / priya@ / ada@ / akhil@ (all @acme.test).
  Reset/invite/email links print in: ${DIM}docker compose logs web -f${RESET}
EOF
exit "$VERIFY_RC"
