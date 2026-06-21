"""
Custom DRF exception handler.

The default DRF handler doesn't recognise Django's ``ValidationError`` (the
``django.core.exceptions`` one, distinct from DRF's), so when it escapes a view
it becomes a 500. The most common way that happens here is a malformed UUID in a
query param that filters a ``UUIDField`` (e.g. ``?cycle=notauuid``): the ORM
coerces it during queryset evaluation and raises Django ``ValidationError``.

A Django ``ValidationError`` is, by definition, an input/validation failure — a
client error (400), never a server bug. Genuine server bugs raise other exception
types and still surface as 500, so mapping ONLY the otherwise-unhandled Django
``ValidationError`` to 400 fixes the malformed-input 500s without masking real
errors. Domain validators that already convert to a DRF error upstream
(serializers/services) never reach this fallback.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response  # DRF already handled it (DRF ValidationError, APIException, …)

    if isinstance(exc, DjangoValidationError):
        detail = list(exc.messages) if hasattr(exc, "messages") else [str(exc)]
        return Response(
            {"detail": "Invalid input.", "code": "INVALID_INPUT", "errors": detail},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None  # fall through to Django's default 500 for genuine server errors
