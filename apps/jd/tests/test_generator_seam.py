"""
JD Generator SEAM — the loud, never-fabricating boundary the real generator
(Module 10) plugs into.

The default provider is NotConfiguredProvider, so ``generate_jd``:
  * validates the generation inputs FIRST (422 INVALID_JD_INPUT) — we never ask a
    generator to invent a JD from nothing;
  * with valid inputs but no provider, skips cleanly returning
    ``{"generated": False, "reason": "no_provider"}`` and leaves the JD UNTOUCHED
    (no body written, status still DRAFT);
  * a configured provider's body is written and locked PENDING_HUMAN_REVIEW (HITL).
"""
import pytest
from decimal import Decimal

from django.test import override_settings

from apps.jd import lifecycle
from apps.jd.exceptions import InvalidJDInput
from apps.jd.generator import (
    JDGeneratorNotConfiguredError,
    NotConfiguredProvider,
    get_provider,
)
from apps.jd.models import JobDescription
from apps.jd.tasks import generate_jd
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

S = JobDescription.Status


def _jd_for_generation(org, inputs):
    jd = lifecycle.create_jd(
        title="Analytics Engineer", level="L4", actor=org.hrbp, body={},
        inputs=inputs,
    )
    return jd


# ── the seam itself ──────────────────────────────────────────────────────────


def test_default_provider_is_not_configured_and_raises():
    provider = get_provider()
    assert isinstance(provider, NotConfiguredProvider)
    assert provider.configured is False
    with pytest.raises(JDGeneratorNotConfiguredError):
        provider.generate(jd=None, inputs={})


# ── generate_jd task ─────────────────────────────────────────────────────────


def test_generate_validates_inputs_before_any_provider_call(org):
    # No inputs snapshot -> missing "inputs"; empty title would too. 422.
    jd = _jd_for_generation(org, inputs={})
    with pytest.raises(InvalidJDInput) as exc:
        generate_jd(str(org.tenant.id), str(jd.id), str(org.hrbp.id))
    assert exc.value.status_code == 422
    assert "inputs" in exc.value.detail["missing"]
    jd.refresh_from_db()
    assert jd.status == S.DRAFT  # untouched


def test_generate_with_no_provider_skips_cleanly_and_never_fabricates(org):
    jd = _jd_for_generation(org, inputs={"role_brief": "Owns dbt models."})
    result = generate_jd(str(org.tenant.id), str(jd.id), str(org.hrbp.id))
    assert result == {"generated": False, "reason": "no_provider"}
    jd.refresh_from_db()
    assert jd.status == S.DRAFT  # NOT advanced
    assert jd.source == JobDescription.Source.MANUAL
    with tenant_context(org.tenant):
        v = lifecycle.working_version(jd)
        assert v.body == {}  # NO fabricated content
        assert v.confidence_score is None and v.citations is None


def test_generate_not_found_is_reported(org):
    import uuid

    result = generate_jd(str(org.tenant.id), str(uuid.uuid4()), str(org.hrbp.id))
    assert result == {"generated": False, "reason": "not_found"}


def test_generate_with_configured_provider_writes_body_and_gates_pending(org):
    """A configured provider's body is written (source=AI) and locked
    PENDING_HUMAN_REVIEW — a generated JD is never published directly."""
    provider_path = "apps.jd.tests.test_generator_seam.FakeProvider"
    jd = _jd_for_generation(org, inputs={"role_brief": "Owns dbt models."})
    with override_settings(JD_GENERATOR_PROVIDER=provider_path):
        result = generate_jd(str(org.tenant.id), str(jd.id), str(org.hrbp.id))
    assert result["generated"] is True
    jd.refresh_from_db()
    assert jd.status == S.PENDING_HUMAN_REVIEW  # HITL gate, NOT published
    assert jd.source == JobDescription.Source.AI
    assert jd.current_version_id is None
    with tenant_context(org.tenant):
        v = lifecycle.working_version(jd)
        assert v.body["summary"].startswith("Generated")
        assert v.confidence_score == Decimal("0.9000")
        assert v.citations == ["evidence:1"]
        assert v.is_published is False


class FakeProvider:
    """A stand-in concrete provider used only by the configured-path test above
    (Module 10 ships the real LangGraph generator)."""

    configured = True

    def generate(self, *, jd, inputs):
        return {
            "body": {
                "summary": "Generated summary for " + jd.title,
                "responsibilities": ["Own the pipeline"],
                "must_haves": ["dbt"],
                "nice_to_haves": [],
            },
            "confidence_score": Decimal("0.9000"),
            "citations": ["evidence:1"],
        }
