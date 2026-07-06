# COE_REQUIREMENTS_MAP.md — the brief as the rubric (read before WEB/MOBILE builds)

> This maps every line of the COE "Project Brief: Performance Management System" to our current state,
> so the WEB and MOBILE build files target the rubric exactly. Status: ✅ done · ⚠ partial/unproven ·
> ❌ gap to build · 🔑 infra/business action (not a code task). Claude Code: read this first, then the
> relevant build file. Do NOT mark anything ✅ until it is verified per BUILD_0's "done = real" rule.

## Implementation Matrix → our state

| Brief requirement | Our state | Where it's handled |
|---|---|---|
| **Web Front-end (Desktop) — responsive Admin Hub: AI JD gen, Dept Calibration/Moderation, Org Chart, System/KPI Config** | ✅ built; ⚠ **WCAG 2.1 AA NOT verified** | WEB build Phase W2 (accessibility) |
| **WCAG 2.1 Level AA compliant** | ❌ unverified | WEB build Phase W2 |
| **Back-end: strict RBAC** | ✅ done (matrix + scope, server-side) | already built |
| **Back-end: SSO (SAML/OAuth)** | ⚠ OAuth/OIDC wired (allauth), **SAML + a proven round-trip NOT done** | WEB build Phase W1 |
| **Back-end: multi-tier approval routing (sequential + parallel)** | ✅ done | already built |
| **Back-end: comprehensive audit logging** | ✅ done (INSERT-only) | already built |
| **Mobile: Continuous Feedback** | ✅ endpoints; mobile screen in progress | MOBILE build |
| **Mobile: 1:1 Meeting Notes** | ❌ **NO backend, NO screen — must build** | MOBILE build Phase M1 (backend) + M-screen |
| **Mobile: Goal Tracking** | ✅ endpoints; mobile screen in build | MOBILE build |
| **Mobile: 360 Quick Assessments** | ✅ endpoints; mobile screen in build | MOBILE build |
| **Mobile: 1-Click Approvals** | ✅ endpoints; mobile screen in build | MOBILE build (manager) |
| **AI: server-side LLM call for JD gen (Claude/GPT/home-grown)** | ✅ done via LLMGateway (provider-agnostic) | already built; 🔑 prod key |
| **Functional Testing: cycle transitions, notifications, KPI weight = 100%, approval escalations, desktop + mobile** | ⚠ backend tested; mobile-web + cross-surface not formalised | both builds + a test pass |
| **Security: pen-test, TLS 1.2+, AES-256 at rest, MFA** | MFA ✅; TLS/AES/pen-test 🔑 (infra/external) | 🔑 your action; documented |
| **Manuals: <2hr-training UI + technical docs** | ❌ not produced | a deliverable (separate from code) |

## The build-task gaps these files close
- **SSO/SAML proven** (W1), **WCAG 2.1 AA** (W2) — WEB build.
- **1:1 Meeting Notes** backend + mobile screen (M1) — MOBILE build, the clear brief gap.
- Cross-surface functional verification (KPI=100%, escalations, transitions on desktop AND mobile-web).

## Explicitly NOT code tasks (🔑 — flag, don't fake)
TLS 1.2+ / AES-256-at-rest (infra/DB config), third-party penetration testing (external vendor), the
production LLM key (Gemini/Groq), and the user manuals (a written deliverable). Claude Code documents
what's needed for each in the report; it does NOT pretend to deliver them.
