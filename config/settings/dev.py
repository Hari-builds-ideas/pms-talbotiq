"""Development settings."""
from .base import *  # noqa: F401,F403
from .base import LOGGING

DEBUG = True

# Human-readable logs in development.
LOGGING["handlers"]["console"]["formatter"] = "plain"

# allauth callbacks need a working host in dev.
ALLOWED_HOSTS = ["*"]
