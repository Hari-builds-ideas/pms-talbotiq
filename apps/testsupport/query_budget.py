"""
Query-budget test helpers (BUILD_1).

The point: every paginated LIST endpoint must run in a query count that is
BOUNDED — independent of the number of rows returned. An N+1 has the signature
``queries ≈ rows × k``; a healthy endpoint is ``queries ≈ constant``.

``measure_scaling`` runs a request-producing callable at two row counts and
returns both query counts so a test can assert the delta is ~0 (bounded). It
resets the seeded rows between the two measurements via the supplied ``seed``
callable so the only variable is row volume.

These helpers make no assumptions about auth/tenant — the caller wires those
(via the project's APIClient + factories inside ``tenant_context``).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import connection, reset_queries
from django.test.utils import CaptureQueriesContext


def count_queries(fn) -> int:
    """Run ``fn`` and return how many DB queries it issued."""
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


@dataclass
class ScalingResult:
    small_rows: int
    large_rows: int
    small_queries: int
    large_queries: int

    @property
    def delta(self) -> int:
        """Extra queries incurred by the extra rows. ~0 ⇒ no N+1."""
        return self.large_queries - self.small_queries

    @property
    def is_bounded(self) -> bool:
        """Bounded if the extra rows added at most a small constant of queries
        (we allow a tiny slack for e.g. a count query), NOT one-per-row."""
        extra_rows = self.large_rows - self.small_rows
        # An N+1 would add ≈ extra_rows queries; bounded adds a small constant.
        return self.delta <= max(2, extra_rows // 4)

    def __str__(self):
        sig = "BOUNDED" if self.is_bounded else "N+1 (scales with rows)"
        return (
            f"{self.small_rows} rows → {self.small_queries} q; "
            f"{self.large_rows} rows → {self.large_queries} q; "
            f"Δ={self.delta} [{sig}]"
        )


def measure_scaling(*, seed, request, small: int, large: int) -> ScalingResult:
    """Measure a list endpoint's query scaling.

    ``seed(n)`` ADDS ``n`` new rows to the list (factories create fresh rows on
    each call); ``request()`` performs the HTTP call and returns the response.
    We seed ``small`` rows, measure, then seed ``large - small`` more (so the
    second measurement sees ``large`` rows total) and measure again. Both run
    inside the caller's DB/tenant context.
    """
    seed(small)
    sq = count_queries(request)
    seed(large - small)
    lq = count_queries(request)
    return ScalingResult(small_rows=small, large_rows=large, small_queries=sq, large_queries=lq)
