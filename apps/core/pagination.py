"""
Shared list pagination — the single page shape used by every paginated list
endpoint (FE #1): ``{count, next, previous, results}``, 50 rows/page, caller may
raise to 200 via ``?page_size=``. Same shape the audit console already uses, so the
frontend handles one paginated envelope everywhere.

``PageNumberPagination.paginate_queryset`` works on a Django QuerySet OR a plain
Python list, so it wraps both the ORM-backed lists and the service-returned
list-of-dicts endpoints without changing their scoping/filtering.
"""
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
