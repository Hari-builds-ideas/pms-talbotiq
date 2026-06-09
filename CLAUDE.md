# PMS — Talbotiq | Hari's Build Memory

## Who I Am
I am Hari. Sole developer and PM for the PMS bucket at Talbotiq.
This file is read by Claude Code at the start of every session.
Never ask me to re-explain the project. Read this file first.

## What We Are Building
AI-Powered Performance Management System (PMS) for SME market.
Multi-tenant, RBAC, AI-assisted, enterprise-grade.
Company: Talbotiq

## Deadlines
- July 7th: MY handoff to QA (Sanjay's team). Not go-live.
- 3 documents already delivered to CEO. Build is live now.

## Tech Stack (LOCKED — do not suggest changes)
- Backend: Python 3.11 + Django 4.2 + Django REST Framework
- Database: MySQL 8
- Cache + Queue: Redis 7 + Celery
- AI: LangGraph + LangSmith + LLM abstraction layer (no hardcoded provider)
- Frontend: React + TypeScript + Tailwind CSS + shadcn/ui
- Auth: JWT (simplejwt) + OAuth (django-allauth) + MFA (django-otp)
- Testing: pytest-django + factory_boy
- Passwords: Argon2

## Architecture Rules (NON-NEGOTIABLE)
1. Every model inherits TenantScopedModel (tenant_id FK, UUID pk)
2. TenantScopedManager filters every queryset by tenant_id — no exceptions
3. JWT tokens embed tenant_id + role on every request
4. Every AI output is saved as PENDING_HUMAN_REVIEW — HITL gate always
5. AuditLog is INSERT-only at DB level — no UPDATE, no DELETE ever
6. All LLM calls go through LLMGateway class only — never direct SDK calls
7. RBAC checked server-side on every endpoint — never trust frontend

## User Roles
- Employee: own data only
- Manager: own data + their team
- HRBP: business-unit wide
- Admin: full tenant control

## Git Rules
- Repo: private GitHub repo (pms-talbotiq)
- Commit after every module is complete and tests pass
- Never commit broken tests
- Commit message format: "Module X — [module name] complete"

## Build Order (follow this exactly)
1. Foundation (multi-tenancy + RBAC + auth) ← CURRENT
2. Goals & KPI engine
3. Reviews + HITL + audit log
4. 360° Feedback + anonymization
5. Approval matrix (sequential + parallel)
6. JD Generator + JD Library
7. Live Org Chart
8. Succession Planning (internal PMS data)
9. Career Roadmap LITE
10. AI Agents (1-4) via LangGraph
11. Entitlements + billing logic
12. Jira + Slack integrations
13. React frontend (desktop Admin Hub + responsive mobile-web)
14. Self-test sweep + QA PDF + handoff docs

## After Every Module
Append to docs/BUILD_NOTES.md:
- What was built
- Files created
- Tests written and passing
- Known risks or TODOs
- What next module needs from this one

## Sub-Agent Usage
Use sub-agents aggressively. Parallelize whenever possible.
Tokens refill every 4 hours — use them fully.

## Stop and Ask Rule
Before any architectural decision not covered above,
ask me ONE clear question and wait for my answer.
Do not assume. Do not proceed on guesses.

## Current Status
Foundation not started yet. Starting now.