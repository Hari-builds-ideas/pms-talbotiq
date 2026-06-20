"""
Production settings posture (BUILD_4 4.1).

``config.settings.prod`` must FAIL CLOSED: a prod process can never boot without a
real SECRET_KEY / ALLOWED_HOSTS (no insecure defaults), and when it does boot it
must be secure (DEBUG off, secure cookies, HSTS). We assert this in a SUBPROCESS
because the failure is at settings import — the running test process is already on
test settings.
"""
import os
import subprocess
import sys

_SMOKE = (
    "import django; django.setup(); from django.conf import settings; "
    "assert settings.DEBUG is False; "
    "print('OK', settings.SESSION_COOKIE_SECURE, settings.SECURE_HSTS_SECONDS > 0, "
    "settings.CSRF_COOKIE_SECURE)"
)


def _setup(extra_env=None, *, drop=()):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(extra_env or {})
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    return subprocess.run(
        [sys.executable, "-c", _SMOKE], env=env, capture_output=True, text=True
    )


def test_prod_fails_closed_without_secret_key():
    r = _setup(drop=("DJANGO_SECRET_KEY",))
    assert r.returncode != 0
    assert "DJANGO_SECRET_KEY" in (r.stderr + r.stdout)


def test_prod_fails_closed_without_allowed_hosts():
    r = _setup({"DJANGO_SECRET_KEY": "x" * 60}, drop=("DJANGO_ALLOWED_HOSTS",))
    assert r.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in (r.stderr + r.stdout)


def test_prod_loads_secure_with_required_env():
    r = _setup(
        {
            "DJANGO_SECRET_KEY": "a-long-random-production-secret-" + "0" * 40,
            "DJANGO_ALLOWED_HOSTS": "app.example.com",
        }
    )
    assert r.returncode == 0, r.stderr
    # DEBUG off + secure session cookie + HSTS on + secure CSRF cookie.
    assert "OK True True True" in r.stdout
