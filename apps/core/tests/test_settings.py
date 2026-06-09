"""
Settings-hardening tests.

Security fix (Module 1 review): production must REFUSE to start without an
explicit DJANGO_SECRET_KEY, so it can never silently boot on the public dev
default and sign JWTs with a known key. We assert this by importing the prod
settings in a clean subprocess with the key removed.
"""
import os
import subprocess
import sys

from django.conf import settings


def _setup_in_subprocess(env):
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=str(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def test_prod_refuses_to_start_without_secret_key():
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DJANGO_ALLOWED_HOSTS"] = "example.com"  # satisfy the other required var
    env.pop("DJANGO_SECRET_KEY", None)

    result = _setup_in_subprocess(env)

    assert result.returncode != 0, "prod settings booted without DJANGO_SECRET_KEY"
    assert "SECRET_KEY" in (result.stdout + result.stderr)


def test_prod_boots_when_secret_key_is_present():
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DJANGO_ALLOWED_HOSTS"] = "example.com"
    env["DJANGO_SECRET_KEY"] = "x" * 50
    env["DJANGO_SECURE_SSL_REDIRECT"] = "false"

    result = _setup_in_subprocess(env)

    assert result.returncode == 0, result.stderr
