"""
The Agent-2 trigger seam (Fast AI · F1 · Proactive Nudge).

After the deterministic scoring engine (re)computes and stores a cycle's scores,
it fires ``cycle_scores_recomputed`` carrying the structured risk data. Module 10
(Agent 2 — KPI Intelligence) will connect a receiver here to classify the signal,
compose a nudge, and surface it (dashboard / Slack). THIS module composes and
sends NOTHING — the risk_status is deterministic and core; the nudge layer is the
Fast-AI lane and is gated by ``apps.billing.gate.requires_entitlement("agent2")``
on Agent 2's own surface, NOT on scoring.

Signal kwargs:
    sender     — the scoring engine module/callable
    tenant_id  — str
    cycle_id   — str
    scores     — list[dict]: {employee_id, raw_score, z_score, t_score,
                 risk_status, pace_behind, insufficient_cohort, cohort_size}
"""
import django.dispatch

cycle_scores_recomputed = django.dispatch.Signal()
