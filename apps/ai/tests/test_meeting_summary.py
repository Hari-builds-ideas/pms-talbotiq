"""
RW_BUILD_5 — AI 1-on-1 / meeting summary. Stateless DRAFT through the LLMGateway:
notes in → {summary, action_items} out, persists nothing, degrades to 503 with no
provider. FakeLLMProvider — no network.
"""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.agents.meeting_summary import summarize_meeting  # registers the fake
from apps.identity.tokens import issue_tokens_for_user
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

FAKE = "apps.ai.providers.FakeLLMProvider"
NOTES = "Talked about the launch blocker and Q3 goals; Ada to escalate the design review."


@override_settings(LLM_PROVIDER=FAKE)
def test_summarize_returns_summary_and_action_items(org):
    with tenant_context(org.tenant):
        out = summarize_meeting(org.manager, NOTES)
    assert out["status"] == "ok"
    assert out["summary"]["summary"]
    assert isinstance(out["summary"]["action_items"], list)


def test_no_provider_degrades(org):
    with tenant_context(org.tenant):
        assert summarize_meeting(org.manager, NOTES)["status"] == "not_configured"


def _client(user):
    access, _ = issue_tokens_for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return c


@override_settings(LLM_PROVIDER=FAKE)
def test_endpoint_summarises_and_validates(org):
    # Any authenticated user may summarise their own notes (USE_CHAT).
    resp = _client(org.report).post("/api/ai/meeting-summary", {"notes": NOTES}, format="json")
    assert resp.status_code == 200
    assert resp.json()["summary"]["summary"]
    # Empty notes → 400.
    bad = _client(org.report).post("/api/ai/meeting-summary", {"notes": "  "}, format="json")
    assert bad.status_code == 400


# ── D37 prompt-quality tuning ────────────────────────────────────────────────
# The fake can't judge LLM output quality, so we test the two things that DO
# determine it deterministically: (1) the notes reach the model VERBATIM (the
# precondition for preserving specifics), and (2) the system prompt carries the
# quality contract (preserve specifics, no filler, assigned action items). The
# actual output quality is judged by Hari's ONE live call.

EXAMPLES = [
    ("won: shipped the recognition feed slice; blocked: waiting on a design review for the check-in form",
     ["recognition feed slice", "design review for the check-in form"]),
    ("Lin flagged the data export is still flaky; she'll pair with Marco on it Thursday",
     ["data export", "Lin", "Marco"]),
    ("1:1 with Sam — happy with onboarding, asked for a stretch goal next quarter",
     ["Sam", "stretch goal"]),
]


@override_settings(LLM_PROVIDER=FAKE)
def test_example_notes_reach_model_verbatim_and_summarise_cleanly(org):
    from apps.ai import providers
    from apps.ai.agents import meeting_summary as ms

    seen = {}

    def _record(prompt, model):
        seen["prompt"] = prompt
        return ms._fake(prompt, model)

    providers.register_fake_output("meeting_summary", _record)
    try:
        with tenant_context(org.tenant):
            for notes, phrases in EXAMPLES:
                out = summarize_meeting(org.manager, notes)
                assert out["status"] == "ok"
                assert out["summary"]["summary"]
                assert isinstance(out["summary"]["action_items"], list)
                for phrase in phrases:  # the specific terms survive into the prompt
                    assert phrase in seen["prompt"], f"{phrase!r} not preserved in prompt"
    finally:
        providers.register_fake_output("meeting_summary", ms._fake)  # restore


def test_system_prompt_encodes_quality_contract():
    from apps.ai.agent_config import system_prompt_for

    sysp = system_prompt_for("meeting_summary").lower()
    assert "verbatim" in sysp            # preserve the specific terms
    assert "filler" in sysp              # no preamble / mood-setting
    assert "who does what" in sysp       # action items name WHO + WHAT
    assert "restating a blocker" in sysp  # not a restatement


def test_schema_locks_exact_shape():
    """Pin the meeting-summary contract so the prompt + schema can't drift apart again
    (this regression caused a live SCHEMA_INVALID). summary = string >= 12 chars;
    action_items = NON-EMPTY list of non-blank strings (Finding D)."""
    from apps.ai.schemas import validate_shape
    from apps.ai.agents.meeting_summary import SCHEMA, _fake

    # The registered fake itself satisfies the schema (so demos/tests never drift).
    assert validate_shape(_fake("", "default"), SCHEMA) == (True, [])
    # A real summary + one concrete action item → valid.
    assert validate_shape(
        {"summary": "Shipped the recognition feed slice.", "action_items": ["Marco to write the postmortem"]},
        SCHEMA,
    ) == (True, [])
    # A VALID TERSE answer (short-but-real summary + a single item) is NOT rejected.
    ok, _ = validate_shape({"summary": "Hired two engineers.", "action_items": ["Send the offer letters"]}, SCHEMA)
    assert ok
    # Empty action_items → SCHEMA_INVALID (Finding D — a hollow answer).
    assert validate_shape({"summary": "Shipped the slice.", "action_items": []}, SCHEMA)[0] is False
    # Missing action_items key → fails.
    assert validate_shape({"summary": "Shipped the slice."}, SCHEMA)[0] is False
    # action_items items that aren't strings (objects) → fails (UI never gets objects).
    assert validate_shape(
        {"summary": "Shipped the slice.", "action_items": [{"who": "Marco", "what": "x"}]}, SCHEMA
    )[0] is False
    # summary returned as a list (a likely drift) → fails.
    assert validate_shape({"summary": ["a", "b"], "action_items": ["do x"]}, SCHEMA)[0] is False
