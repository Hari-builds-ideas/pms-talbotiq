"""
The anonymisation layer — Module 4's headline guarantee. DETERMINISTIC: no
randomness, no AI, fully reproducible.

Anonymisation happens at the EGRESS boundary, never in storage: the giver
identity stays on the Feedback row (dedup / audit / self-edit), and everything
that leaves the sensitive store — toward a recipient, an HRBP, or (Module 10)
Agent 3 — goes through :func:`build_anonymized_payload`, which:

* strips the giver UUID, name and email entirely (PROVABLE: the serialized
  payload contains zero giver identifiers — asserted by tests scanning the
  output, this module's analog of Module 3's CHECK-constraint proof);
* replaces each giver with an opaque per-cycle pseudonym ("PEER#1", "UPWARD#2")
  ordered by the feedback row's UUID hex — deterministic yet uncorrelated with
  identity or submission time, and never mapped back to a user via any API;
* applies the PER-GROUP minimum-volume threshold: PEER and UPWARD groups below
  ``cycle.effective_min_volume`` are EXCLUDED from the payload and recorded as
  insufficient (one identifiable peer response is never egressed alone). SELF
  and MANAGER are inherently attributed and bypass the threshold.

:func:`scan_for_identity_leaks` is the deterministic anonymity-breach guard
that runs BEFORE any LLM. Because the identity system stores emails only (User
has no name fields), the guard scans included bodies for (a) any tenant user's
full email and (b) ANY email-like pattern at all (conservative: an email
address inside feedback text is a de-anonymisation vector even if unknown).
Name-scanning activates if/when user profiles gain name fields — a
deterministic guard can only check identities the system knows. Agent 3 adds a
post-LLM breach check in Module 10; this pre-LLM guard is Module 4's job.
"""
import re

from apps.identity.models import User

from .constants import ANONYMITY_GATED_GROUPS
from .models import Feedback

#: Conservative RFC-ish email matcher for the generic leak scan.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE)

_GROUP_ORDER = ("SELF", "MANAGER", "PEER", "UPWARD")


def _cycle_items(cycle):
    """The cycle's 360 feedback, in deterministic (UUID-hex) order.

    Caller must hold the tenant context (request path or a bound task).
    """
    items = list(Feedback.objects.filter(cycle=cycle, kind=Feedback.Kind.THREE_SIXTY))
    return sorted(items, key=lambda f: f.id.hex)


def group_volumes(cycle):
    """Per-relationship-group response counts for the cycle's 360 feedback."""
    volumes = {group: 0 for group in _GROUP_ORDER}
    for item in _cycle_items(cycle):
        volumes[item.relationship] = volumes.get(item.relationship, 0) + 1
    return volumes


def insufficient_groups_for(cycle):
    """The anonymity-gated groups (PEER/UPWARD) below the cycle's threshold.

    Only groups with at least one response can be 'insufficient' — an empty
    group is simply absent, not a privacy risk.
    """
    threshold = cycle.effective_min_volume
    volumes = group_volumes(cycle)
    return [
        group
        for group in ANONYMITY_GATED_GROUPS
        if 0 < volumes.get(group, 0) < threshold
    ]


def build_anonymized_payload(cycle):
    """The ONLY artifact that may leave the sensitive store.

    Returns a JSON-serializable dict::

        {
          "cycle_id": "...", "subject_id": "...",
          "min_volume": 3,
          "volumes": {"SELF": 1, "MANAGER": 1, "PEER": 3, "UPWARD": 0},
          "insufficient_groups": ["UPWARD"],
          "insufficient_volume": false,
          "groups": {
            "SELF":    [{"pseudonym": "SELF#1", "body": ..., "marked_sensitive": ...}],
            "MANAGER": [...],
            "PEER":    [...],   # only when >= threshold
          },
        }

    Gated groups below threshold are OMITTED from ``groups`` and listed in
    ``insufficient_groups``. The subject id is retained (recipients know whose
    360 this is); every giver identifier is stripped.
    """
    threshold = cycle.effective_min_volume
    volumes = group_volumes(cycle)
    insufficient = insufficient_groups_for(cycle)

    groups = {}
    counters = {group: 0 for group in _GROUP_ORDER}
    for item in _cycle_items(cycle):
        group = item.relationship
        if group in insufficient:
            continue  # below threshold: never egressed
        counters[group] += 1
        groups.setdefault(group, []).append(
            {
                "pseudonym": f"{group}#{counters[group]}",
                "body": item.body,
                "marked_sensitive": item.giver_marked_sensitive,
            }
        )

    return {
        "cycle_id": str(cycle.id),
        "subject_id": str(cycle.subject_id),
        "min_volume": threshold,
        "volumes": volumes,
        "insufficient_groups": insufficient,
        "insufficient_volume": bool(insufficient),
        "groups": groups,
    }


def scan_for_identity_leaks(cycle, payload):
    """Deterministic pre-LLM anonymity-breach guard.

    Scans every body INCLUDED in the anonymised payload (the egress artifact)
    for identity leaks:

    * any tenant user's full email address (case-insensitive) — covers both
      naming someone else and a giver self-identifying;
    * any email-like pattern at all (conservative).

    Returns a list of findings ``{"group", "pseudonym", "pattern"}`` — findings
    NEVER carry the giver identity (they travel with the summary record, which
    an HRBP reads). Empty list = passed. Caller must hold the tenant context.
    """
    tenant_emails = [e.lower() for e in User.objects.values_list("email", flat=True)]
    findings = []
    for group, items in payload.get("groups", {}).items():
        for entry in items:
            body_lower = entry["body"].lower()
            for email in tenant_emails:
                if email and email in body_lower:
                    findings.append(
                        {"group": group, "pseudonym": entry["pseudonym"], "pattern": "tenant_user_email"}
                    )
                    break
            else:
                if _EMAIL_RE.search(entry["body"]):
                    findings.append(
                        {"group": group, "pseudonym": entry["pseudonym"], "pattern": "email_like"}
                    )
    return findings
