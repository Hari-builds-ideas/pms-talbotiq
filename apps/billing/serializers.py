"""
Billing serializers.

``EntitlementSerializer`` is read-only output for the admin billing endpoints. It
surfaces the two commercial axes (``seat_count``, ``feature_packs``) plus two
derived, presentation-friendly fields: ``unlocked_agents`` (the computed set the
packs grant) and ``tier_label`` (DISPLAY ONLY — never an enforcement input).
"""
from __future__ import annotations

from rest_framework import serializers

from .models import Entitlement


class EntitlementSerializer(serializers.ModelSerializer):
    unlocked_agents = serializers.SerializerMethodField()
    tier_label = serializers.SerializerMethodField()

    class Meta:
        model = Entitlement
        fields = ["seat_count", "feature_packs", "unlocked_agents", "tier_label"]

    def get_unlocked_agents(self, obj) -> list[str]:
        return sorted(obj.unlocked_agents())

    def get_tier_label(self, obj) -> str:
        # Display only — derived from packs; never used to gate access.
        return obj.tier_label
