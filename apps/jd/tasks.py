"""
Celery entry point for the JD Generator seam.

``generate_jd`` is the single way an AI body is produced. It is a
``@shared_task`` so production can call ``.delay()``, but it is also directly
callable synchronously (tests and the API view call it inline).

Order of operations (the locked Module-6 contract):

  (a) bind the tenant — off-request code; the scoped manager fails closed
      otherwise (the lesson from Modules 2/3/4).
  (b) VALIDATE the generation inputs BEFORE any provider call. Missing
      title/level/inputs raises ``InvalidJDInput`` (HTTP 422 INVALID_JD_INPUT) —
      we never ask a generator to invent a JD from nothing.
  (c) resolve the provider. With none configured it logs a clear warning and
      returns ``{"generated": False, "reason": "no_provider"}`` — the JD is left
      UNTOUCHED and NO fake body is ever written. The API view surfaces this as a
      loud 503 ("the generator lands in Module 10").

A configured provider's body is written to the working DRAFT version and locked
PENDING_HUMAN_REVIEW via the lifecycle — the HITL gate; a generated JD is never
published directly.
"""
import logging

from celery import shared_task

from apps.tenancy.context import tenant_context

from . import lifecycle
from .generator import JDGeneratorNotConfiguredError, get_provider
from .models import JobDescription

logger = logging.getLogger("pms.jd.generator")


@shared_task
def generate_jd(tenant_id, jd_id, actor_id=None):
    """Generate the body for ``jd_id`` (within ``tenant_id``), HITL-gated.

    ``actor_id`` is the requesting human (the HRBP hitting the API). Returns a
    summary dict; ``{"generated": False, "reason": ...}`` on any skip. Raises
    ``InvalidJDInput`` (422) when the JD lacks the inputs a generator needs.
    """
    with tenant_context(tenant_id):
        jd = JobDescription.objects.filter(id=jd_id).first()
        if jd is None:
            logger.warning(
                "JD generation skipped for tenant=%s: jd=%s not found.",
                tenant_id,
                jd_id,
            )
            return {"generated": False, "reason": "not_found"}

        if jd.status not in (JobDescription.Status.DRAFT,):
            return {"generated": False, "reason": f"bad_state:{jd.status}"}

        version = lifecycle.working_version(jd)

        # (b) Validate inputs BEFORE touching a provider — raises 422 if missing.
        lifecycle.validate_generation_inputs(jd, version)

        # (c) Resolve the provider. Unconfigured -> skip cleanly, JD untouched.
        provider = get_provider()
        if not getattr(provider, "configured", False):
            logger.warning(
                "JD generation skipped for tenant=%s jd=%s: no JD Generator "
                "provider configured (lands in Module 10); JD left in %s.",
                tenant_id,
                jd_id,
                jd.status,
            )
            return {"generated": False, "reason": "no_provider"}

        if actor_id is None:
            logger.warning(
                "JD generation refused for tenant=%s jd=%s: no actor_id; an "
                "accountable human requester is required.",
                tenant_id,
                jd_id,
            )
            return {"generated": False, "reason": "actor_required"}

        from apps.identity.models import User

        actor = User.objects.filter(id=actor_id).first()
        if actor is None:
            logger.warning(
                "JD generation refused for tenant=%s jd=%s: actor=%s not found.",
                tenant_id,
                jd_id,
                actor_id,
            )
            return {"generated": False, "reason": "actor_not_found"}

        try:
            result = provider.generate(jd=jd, inputs=version.inputs_snapshot)
        except JDGeneratorNotConfiguredError:
            logger.warning(
                "JD generation skipped for tenant=%s jd=%s: provider reported "
                "not configured; JD left in %s.",
                tenant_id,
                jd_id,
                jd.status,
            )
            return {"generated": False, "reason": "no_provider"}
        except Exception as exc:  # noqa: BLE001 - a provider bug must not crash the worker
            reason = (
                "budget_exceeded"
                if getattr(exc, "gateway_status", None) == "BUDGET_EXCEEDED"
                else "provider_error"
            )
            logger.error(
                "JD generator failed for tenant=%s jd=%s; JD left in %s for ops "
                "to inspect.",
                tenant_id,
                jd_id,
                jd.status,
                exc_info=True,
            )
            return {"generated": False, "reason": reason}

        # Write the generated body onto the working DRAFT version (source=AI),
        # then lock it PENDING_HUMAN_REVIEW via the audited lifecycle (HITL gate).
        version.body = result["body"]
        version.confidence_score = result.get("confidence_score")
        version.citations = result.get("citations")
        version.save(
            update_fields=["body", "confidence_score", "citations", "updated_at"]
        )
        jd.source = JobDescription.Source.AI
        jd.save(update_fields=["source", "updated_at"])
        lifecycle.submit_for_review(jd, actor)
        return {"generated": True, "jd_id": str(jd.id), "status": jd.status}
