# Archive

**Nothing in this directory is instructions.** It is history: superseded plans,
build-session prompts, one-off reports and deployment configs for platforms this
product no longer uses.

If a file here contradicts something in `docs/BUILD/`, `docs/RUNBOOK.md` or the
root `README.md`, the other one is right. Read these to understand *why* a
decision was made, never to find out *what to do*.

---

## Planning and build-session documents

The repository root accumulated 33 loose markdown files across a series of build
sessions — phase plans, agent-build briefs, hand-over checklists, a demo video
script, test reports. They were untracked, so they were invisible to anyone who
cloned the repo and impossible to tell apart from current documentation for
anyone who did not.

They are kept rather than deleted because several record a decision that is still
in force and whose reasoning exists nowhere else. They are moved rather than left
in place because a root directory with 39 markdown files has no signal in it: a
new engineer cannot tell `V1_MASTER.md` from `PROD_MASTER.md` from `FINAL.md`, and
the honest answer is that none of them is current.

| Group | Files | What they were |
| --- | --- | --- |
| Agent build briefs | `AGENT_MASTER.md`, `AGENT_INTEL_V2.md`, `AGENT_V3_MASTER.md`, `A_*.md`, `B_*.md`, `C_*.md`, `D_*.md`, `E_REPORT.md` | Phase briefs for the AI-agent work (Module 10) and its eval harness |
| V1 push | `V1_MASTER.md`, `V1_A_SIMPLIFY.md`, `V1_B_POLISH.md`, `V1_C_DEPLOY_DEMO.md`, `V1_D_HANDOFF_DOCS.md`, `V1_E_GEMINI.md` | The V1 simplification and demo-readiness plan |
| Production push | `PROD_MASTER.md`, `PROD_A_BRANDING.md`, `PROD_B_ONBOARDING_SSO.md`, `PROD_C_PAYMENTS.md`, `PROD_D_AI_ROBUSTNESS.md`, `PROD_E_HANDOVER.md`, `PRODUCTION_REQUIREMENTS.md` | The production-readiness plan that preceded the current hardening work |
| Reports and one-offs | `BUILD_8_REPORT.md`, `PHASE2_BUILD.md`, `PRE_HANDOVER_CHECKLIST.md`, `FINAL.md`, `MYTEST.md`, `DEMO_VIDEO_SCRIPT.md`, `testing_report.md`, `testing_answers.md` | Point-in-time status reports and scratch notes |

**Where the current version of each lives now:**

| If you came here looking for | Read instead |
| --- | --- |
| How to run or operate the stack | `docs/RUNBOOK.md`, root `README.md` |
| Deployment, TLS, backups, email | `docs/BUILD/` |
| What is actually built and what is staged | root `README.md` |
| Why a piece of the current hardening work looks the way it does | `docs/BUILD/PROGRESS.md` |
| Architecture decisions | `DECISIONS.md` (root — still current) |

---

## Deployment configs for platforms no longer used

Deployment is **GCP: a VM running `docker-compose.prod.yml`**. The repo carried
four overlapping deployment stories, which is three more than one team can keep
true — and a stale config that still looks live is worse than no config, because
someone eventually follows it.

| File | Was for | Why it moved |
| --- | --- | --- |
| `railway.json` | Railway web service | Not the deployment target. Kept rather than deleted because the history shows a Railway deploy did exist, so the exact build/start/healthcheck config is worth being able to read. |
| `railway.worker.json` | Railway celery worker | Same. |
| `railway.beat.json` | Railway celery beat | Same. |

### Deleted outright, not archived

| File | Why |
| --- | --- |
| `vercel.json` | It hardcoded a production API hostname with no env indirection, so **any** preview deployment pointed at production. Archiving a file whose only distinctive content is a live URL aimed at prod is not worth the risk of it being copied back. |
| `render.yaml` | A free-tier demo path that set `CELERY_TASK_ALWAYS_EAGER=true`, running AI jobs inline in the web process. Not a production posture, and keeping it invites someone to deploy it. |

### What is live

- `docker-compose.prod.yml` — the stack
- `Caddyfile` — the public edge (`docs/BUILD/ENABLE_TLS.md`; TLS switches on with
  `DOMAIN`)
- `Dockerfile`, `frontend/Dockerfile` — the images
- `gunicorn.conf.py` — the app server
- `deploy/systemd/` — the backup and restore-drill timers

If Railway is ever revived, move these back rather than rewriting them.
