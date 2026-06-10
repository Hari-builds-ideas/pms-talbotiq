"""
Live Org Chart routes, mounted under ``/api/org/`` by the root urlconf.

Paths are declared WITHOUT a leading slash because they are appended to the
``api/org/`` mount point. The literal prefixes (``positions``, ``tree``,
``search``, ``export``, ``vacancies``, ``reassign``) are declared BEFORE the bare
``positions/<uuid:pk>`` detail / action routes so they match first. RBAC gating
lives on the views; position state legality / cycle rules live in the writes; the
§2 visibility rule lives in the services.
"""
from django.urls import path

from .views import (
    OrgExportView,
    OrgSearchView,
    OrgTreeView,
    PersonCardView,
    PositionCloseView,
    PositionDetailView,
    PositionFillView,
    PositionLinkJDView,
    PositionListCreateView,
    PositionUnlinkJDView,
    ReassignView,
    VacancyListView,
)

app_name = "org"

urlpatterns = [
    # Literal read prefixes.
    path("tree", OrgTreeView.as_view(), name="tree"),
    path("search", OrgSearchView.as_view(), name="search"),
    path("export", OrgExportView.as_view(), name="export"),
    path("vacancies", VacancyListView.as_view(), name="vacancies"),
    path("people/<uuid:pk>", PersonCardView.as_view(), name="person-card"),
    # Positions — list/create before the bare <uuid:pk> detail / action routes.
    path("positions", PositionListCreateView.as_view(), name="position-list-create"),
    path("positions/<uuid:pk>", PositionDetailView.as_view(), name="position-detail"),
    path(
        "positions/<uuid:pk>/fill",
        PositionFillView.as_view(),
        name="position-fill",
    ),
    path(
        "positions/<uuid:pk>/close",
        PositionCloseView.as_view(),
        name="position-close",
    ),
    path(
        "positions/<uuid:pk>/link-jd",
        PositionLinkJDView.as_view(),
        name="position-link-jd",
    ),
    path(
        "positions/<uuid:pk>/unlink-jd",
        PositionUnlinkJDView.as_view(),
        name="position-unlink-jd",
    ),
    # Reassignment.
    path("reassign", ReassignView.as_view(), name="reassign"),
]
