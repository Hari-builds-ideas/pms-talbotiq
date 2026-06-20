"""
Celery entry point for the Agent-3 (Feedback Summarization) seam.

``summarize_feedback`` is the single way a cycle summary is produced: it runs
the deterministic pipeline (anonymise -> threshold -> breach guard -> summary
record) and only then hands the anonymised payload to whatever provider
``apps.feedback.agent3.get_provider`` resolves. It is a ``@shared_task`` so
production calls ``.delay()``, but it is also directly callable synchronously
(``services.close_cycle`` and the tests call it inline).

With no provider configured it logs a clear warning and skips the AI step
cleanly — the summary record still exists with its volumes/gates, but
``sections`` stays NULL; theme text is NEVER fabricated. On an anonymity
breach the provider is never even resolved: nothing that failed the
deterministic guard may reach an LLM (the Doc 2 / Agent-3 diagram order).
"""
import logging

from celery import shared_task
from django.utils import timezone

from apps.audit.services import record
from apps.tenancy.context import tenant_context

from .agent3 import FeedbackSummarizerNotConfiguredError, get_provider
from .anonymize import build_anonymized_payload, scan_for_identity_leaks
from .models import FeedbackCycle, FeedbackSummary

logger = logging.getLogger("pms.feedback.agent3")


@shared_task
def summarize_feedback(tenant_id, cycle_id, actor_id=None):
    """Summarise cycle ``cycle_id`` (within ``tenant_id``), anonymity-gated.

    ``actor_id`` is the human who closed the cycle (None for scheduled runs —
    the audit rows then carry a system actor). Returns a summary dict;
    ``{"summarized": False, "reason": ...}`` on any skip.

    The order is fixed by the Agent-3 diagram: the anonymised payload and the
    deterministic breach guard ALWAYS run first, and the summary row is
    upserted (one per cycle — re-running refreshes the same row) BEFORE any
    provider logic. A breach or a sensitive flag holds the summary HRBP_HOLD;
    a clean run leaves it PENDING_HUMAN_REVIEW — human release is required in
    every path (the HITL discipline).
    """
    with tenant_context(tenant_id):
        cycle = FeedbackCycle.objects.filter(id=cycle_id).first()
        if cycle is None:
            logger.warning(
                "Agent-3 summarize skipped for tenant=%s: cycle=%s not found.",
                tenant_id,
                cycle_id,
            )
            return {"summarized": False, "reason": "not_found"}

        actor = None
        if actor_id is not None:
            from apps.identity.models import User

            actor = User.objects.filter(id=actor_id).first()

        # The ONLY artifact that may leave the sensitive store — built ALWAYS,
        # before any provider logic. Volumes/threshold come with it for free.
        payload = build_anonymized_payload(cycle)
        volume_total = sum(payload["volumes"].values())
        insufficient_groups = payload["insufficient_groups"]
        insufficient_volume = payload["insufficient_volume"]

        # Deterministic pre-LLM breach guard + the giver-flagged sensitivity.
        findings = scan_for_identity_leaks(cycle, payload)
        sensitive = any(
            item["marked_sensitive"]
            for group in payload["groups"].values()
            for item in group
        )

        defaults = {
            "tenant_id": cycle.tenant_id,
            "subject": cycle.subject,
            "sections": None,  # written ONLY by a configured Agent 3 below
            "volume_total": volume_total,
            "insufficient_groups": insufficient_groups,
            "insufficient_volume": insufficient_volume,
            "sensitive": sensitive,
            "generated_at": timezone.now(),
        }

        if findings:
            # Audit BEFORE the held summary takes effect, then STOP: nothing
            # that failed the anonymity guard may reach a provider.
            record(
                action="summary.held_for_hrbp",
                actor=actor,
                target_type="feedback_cycle",
                target_id=cycle.id,
                metadata={"findings": findings},
                tenant=cycle.tenant_id,
            )
            defaults["anonymity_passed"] = False
            defaults["status"] = FeedbackSummary.Status.HRBP_HOLD
            summary, _ = FeedbackSummary.objects.update_or_create(
                cycle=cycle, defaults=defaults
            )
            logger.warning(
                "Agent-3 summarize held for tenant=%s cycle=%s: %d anonymity "
                "finding(s); summary HRBP_HOLD, provider never invoked.",
                tenant_id,
                cycle_id,
                len(findings),
            )
            return {
                "summarized": False,
                "reason": "anonymity_breach",
                "findings": len(findings),
                "summary_id": str(summary.id),
            }

        # No breach: audit BEFORE creating/updating the summary row.
        record(
            action="summary.generated",
            actor=actor,
            target_type="feedback_cycle",
            target_id=cycle.id,
            metadata={
                "volume_total": volume_total,
                "insufficient_groups": insufficient_groups,
            },
            tenant=cycle.tenant_id,
        )
        defaults["anonymity_passed"] = True
        if sensitive:
            # Decision 7: a giver-flagged-sensitive cycle is held for an HRBP
            # before release, even with the anonymity guard clean.
            record(
                action="summary.held_for_hrbp",
                actor=actor,
                target_type="feedback_cycle",
                target_id=cycle.id,
                metadata={"reason": "sensitive"},
                tenant=cycle.tenant_id,
            )
            defaults["status"] = FeedbackSummary.Status.HRBP_HOLD
        else:
            defaults["status"] = FeedbackSummary.Status.PENDING_HUMAN_REVIEW
        summary, _ = FeedbackSummary.objects.update_or_create(
            cycle=cycle, defaults=defaults
        )

        provider = get_provider()
        if not getattr(provider, "configured", False):
            logger.warning(
                "Agent-3 summarize skipped for tenant=%s cycle=%s: no Feedback "
                "Summarizer provider configured (Agent 3 lands in Module 10); "
                "summary %s left in %s with sections NULL.",
                tenant_id,
                cycle_id,
                summary.id,
                summary.status,
            )
            return {
                "summarized": False,
                "reason": "no_provider",
                "summary_id": str(summary.id),
                "status": summary.status,
            }

        try:
            result = provider.summarize(payload)
        except FeedbackSummarizerNotConfiguredError:
            # A configured-looking provider that still can't serve.
            logger.warning(
                "Agent-3 summarize skipped for tenant=%s cycle=%s: provider "
                "reported not configured (Agent 3 lands in Module 10).",
                tenant_id,
                cycle_id,
            )
            return {
                "summarized": False,
                "reason": "no_provider",
                "summary_id": str(summary.id),
                "status": summary.status,
            }
        except Exception as exc:  # noqa: BLE001 - a provider bug must not crash the worker
            reason = (
                "budget_exceeded"
                if getattr(exc, "gateway_status", None) == "BUDGET_EXCEEDED"
                else "provider_error"
            )
            logger.error(
                "Agent-3 provider failed for tenant=%s cycle=%s; summary %s "
                "left as-is (sections NULL) for ops to inspect.",
                tenant_id,
                cycle_id,
                summary.id,
                exc_info=True,
            )
            return {
                "summarized": False,
                "reason": reason,
                "summary_id": str(summary.id),
            }

        # Persist the AI sections; the status gate is untouched — HRBP_HOLD
        # stays held, PENDING_HUMAN_REVIEW stays pending. Human release is
        # still required (the HITL discipline).
        summary.sections = result["sections"]
        summary.confidence_score = result.get("confidence_score")
        update_fields = ["sections", "confidence_score", "updated_at"]
        # Agent 3's POST-LLM anonymity-breach check (Module 10) is load-bearing:
        # the Module-4 pre-LLM guard is email-only and ran on the source bodies, so
        # a leak in the GENERATED text is caught now -> HOLD for an HRBP (the summary
        # is never auto-released). Absent the key (the no-provider / Module-4 fake
        # paths), this is a clean no-op.
        if result.get("anonymity_breach"):
            record(
                action="summary.held_for_hrbp",
                actor=actor,
                target_type="feedback_cycle",
                target_id=cycle.id,
                metadata={"reason": "post_llm_breach"},
                tenant=cycle.tenant_id,
            )
            summary.status = FeedbackSummary.Status.HRBP_HOLD
            summary.anonymity_passed = False
            update_fields += ["status", "anonymity_passed"]
        summary.save(update_fields=update_fields)
        return {
            "summarized": True,
            "summary_id": str(summary.id),
            "status": summary.status,
        }
