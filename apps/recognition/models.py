"""
Recognition (kudos) — a deliberately SIMPLE peer-recognition card + feed
(RW_BUILD_2). Anyone may recognise anyone else in their tenant; the one
load-bearing safety property is that **visibility is enforced server-side** (the
feed query in ``services.recognition_feed`` — a PRIVATE/MANAGER_ONLY card must
never reach a feed it isn't permitted to), and tenant isolation rides on the
``TenantScopedManager`` as everywhere else.

No new design system, no over-building: a card has a sender, a recipient, a
company value, a message, an optional badge, and a visibility level; reactions
are a tiny related model (toggle-per-emoji).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantScopedModel

#: The tenant's company values a recognition can cite. A fixed default list for
#: now (per-tenant customisation is a documented follow-up — see QUESTIONS Q7);
#: the create path validates the value against this list so the data stays clean.
COMPANY_VALUES: list[str] = [
    "Teamwork",
    "Leadership",
    "Innovation",
    "Ownership",
    "Customer Focus",
    "Problem-Solving",
    "Learning",
    "Execution",
    "Helping Others",
    "Above & Beyond",
]

#: The fixed reaction palette (toggle one per emoji per user).
REACTION_EMOJIS: list[str] = ["👍", "❤️", "🎉", "🚀", "👏"]


class Recognition(TenantScopedModel):
    """One peer recognition. ``visibility`` governs who can see it in the feed
    (enforced in ``services.recognition_feed``, never trusted from the client)."""

    class Visibility(models.TextChoices):
        PRIVATE = "PRIVATE", "Private (just the two of us)"
        MANAGER_ONLY = "MANAGER_ONLY", "Manager only"
        TEAM = "TEAM", "Team"
        COMPANY = "COMPANY", "Company"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recognitions_sent"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recognitions_received"
    )
    value = models.CharField(max_length=40)  # one of COMPANY_VALUES
    message = models.TextField(max_length=1000)
    badge = models.CharField(max_length=40, blank=True, default="")
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.TEAM
    )

    class Meta:
        db_table = "recognition"
        ordering = ["-created_at"]
        indexes = [
            # The feed reads the tenant's recent cards, and filters by the
            # recipient/sender relationship for TEAM/MANAGER_ONLY visibility.
            models.Index(fields=["tenant", "-created_at"], name="ix_recog_tenant_recent"),
            models.Index(fields=["tenant", "recipient"], name="ix_recog_recipient"),
            models.Index(fields=["tenant", "sender"], name="ix_recog_sender"),
        ]

    def __str__(self):
        return f"Recognition({self.sender_id}->{self.recipient_id}, {self.value}, {self.visibility})"


class RecognitionReaction(TenantScopedModel):
    """A single user's reaction (one emoji) on a recognition. Toggled in the
    service: re-reacting with the same emoji removes it (hard delete — a reaction
    carries no history value)."""

    recognition = models.ForeignKey(
        Recognition, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recognition_reactions"
    )
    emoji = models.CharField(max_length=8)

    class Meta:
        db_table = "recognition_reaction"
        constraints = [
            models.UniqueConstraint(
                fields=["recognition", "user", "emoji"], name="uniq_recognition_reaction"
            )
        ]
        indexes = [models.Index(fields=["tenant", "recognition"], name="ix_recogreact_card")]

    def __str__(self):
        return f"RecognitionReaction({self.user_id}, {self.emoji})"
