from rest_framework.exceptions import APIException


class InvalidCredentials(APIException):
    """401 for failed login / MFA.

    DRF downgrades ``NotAuthenticated``/``AuthenticationFailed`` to 403 when the
    view exposes no authenticator (and therefore no ``WWW-Authenticate`` header).
    The login and MFA-challenge endpoints intentionally have no authenticators,
    so we raise this plain APIException to return a true 401 as the spec's login
    workflow requires ("Reject - 401")."""

    status_code = 401
    default_detail = "Invalid credentials."
    default_code = "invalid_credentials"
