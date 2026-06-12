"""
Analytics constants.

MIN_COHORT is the headline safety property of this module: any department/cohort
view with FEWER than this many members suppresses individual values and returns
aggregate-only, so a small team can never be de-anonymised by its manager.
"""
from __future__ import annotations

#: Minimum cohort size before individual values may be shown in a department /
#: cohort analytics view (per the Doc-2 §Module 12 min-cohort-suppression diagram).
#:
#: NOTE — this is a DIFFERENT, SEPARATE threshold from the Module-4 360-feedback
#: per-group minimum volume (``apps.feedback.constants.MIN_FEEDBACK_VOLUME = 3``).
#: They protect different surfaces (anonymous 360 aggregation vs. performance
#: analytics cohorts) and are deliberately not unified — keep both.
MIN_COHORT = 5
