"""
Feedback anonymity constants (all tunable).

MIN_FEEDBACK_VOLUME — the minimum number of responses a relationship group must
reach before it is included in the anonymised payload. Applied PER RELATIONSHIP
GROUP that carries de-anonymisation risk (PEER and UPWARD), NOT across the whole
cycle: one peer response among many others is still trivially identifiable.
SELF and MANAGER are inherently attributed/expected and are not subject to the
threshold.

3 is the floor for a demoable MVP; 5 is the more conservative industry default.
A per-cycle override lives on ``FeedbackCycle.min_volume`` (e.g. a tenant whose
teams are large enough to demand 5).
"""
MIN_FEEDBACK_VOLUME = 3

#: Relationship groups subject to the per-group anonymity threshold.
ANONYMITY_GATED_GROUPS = ("PEER", "UPWARD")
