"""
Career Development (Roadmap LITE) routes, mounted under ``/api/career/`` by the
root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/career/`` mount point. The literal singular ``roadmap`` (the caller's own
roadmaps) and ``target`` routes are declared distinctly from the ``roadmaps``
collection; the ``roadmaps/<uuid:pk>`` detail route and its literal action suffixes
(``skill-gap`` / ``regenerate`` / ``enrich`` / ``progress``) each carry a distinct
trailing segment so they match unambiguously.

Career is employee-visible: RBAC capability gating is on the views; row scope
(out-of-scope / cross-tenant → 404) lives in the services.
"""
from django.urls import path

from .views import (
    MyRoadmapsView,
    RoadmapDetailView,
    RoadmapEnrichView,
    RoadmapListView,
    RoadmapProgressView,
    RoadmapRegenerateView,
    RoadmapSkillGapView,
    TargetSelectView,
)

app_name = "career"

urlpatterns = [
    # Target selection + deterministic roadmap generation.
    path("target", TargetSelectView.as_view(), name="target"),
    # The caller's OWN roadmaps (singular) — declared before the collection.
    path("roadmap", MyRoadmapsView.as_view(), name="my-roadmaps"),
    # Scoped roadmap collection.
    path("roadmaps", RoadmapListView.as_view(), name="roadmap-list"),
    # One roadmap + its actions (each a distinct trailing segment).
    path("roadmaps/<uuid:pk>", RoadmapDetailView.as_view(), name="roadmap-detail"),
    path(
        "roadmaps/<uuid:pk>/skill-gap",
        RoadmapSkillGapView.as_view(),
        name="roadmap-skill-gap",
    ),
    path(
        "roadmaps/<uuid:pk>/regenerate",
        RoadmapRegenerateView.as_view(),
        name="roadmap-regenerate",
    ),
    path(
        "roadmaps/<uuid:pk>/enrich",
        RoadmapEnrichView.as_view(),
        name="roadmap-enrich",
    ),
    path(
        "roadmaps/<uuid:pk>/progress",
        RoadmapProgressView.as_view(),
        name="roadmap-progress",
    ),
]
