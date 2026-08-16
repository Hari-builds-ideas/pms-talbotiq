"""
Production settings posture (BUILD_4 4.1).

``config.settings.prod`` must FAIL CLOSED: a prod process can never boot without a
real SECRET_KEY / ALLOWED_HOSTS (no insecure defaults), and when it does boot it
must be secure (DEBUG off, secure cookies, HSTS). We assert this in a SUBPROCESS
because the failure is at settings import — the running test process is already on
test settings.
"""
import os
import pathlib
import subprocess
import sys

_SMOKE = (
    "import django; django.setup(); from django.conf import settings; "
    "assert settings.DEBUG is False; "
    "print('OK', settings.SECURE_SSL_REDIRECT, settings.SESSION_COOKIE_SECURE, "
    "settings.SECURE_HSTS_SECONDS > 0, settings.CSRF_COOKIE_SECURE)"
)

#: The env every prod boot needs, minus whatever the test is probing.
_REQUIRED = {
    "DJANGO_SECRET_KEY": "a-long-random-production-secret-" + "0" * 40,
    "DJANGO_ALLOWED_HOSTS": "app.example.com",
    "PUBLIC_APP_URL": "https://app.example.com",
}


def _setup(extra_env=None, *, drop=()):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(extra_env or {})
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    # Hermetic: do NOT inherit a developer's local .env (which would re-supply a
    # dropped DJANGO_SECRET_KEY / DJANGO_ALLOWED_HOSTS and mask the fail-closed check).
    env["PMS_DOTENV_PATH"] = "/nonexistent/.env"
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


def test_prod_fails_closed_without_public_app_url():
    """C4. Its base default is http://localhost:8080, which does not error — it
    SENDS. Every password-reset and invitation email would carry a dead link to
    the recipient's own machine, and the only signal would be users reporting it
    days later. Failing at startup is the strictly better failure."""
    r = _setup(
        {"DJANGO_SECRET_KEY": "x" * 60, "DJANGO_ALLOWED_HOSTS": "example.com"},
        drop=("PUBLIC_APP_URL",),
    )
    assert r.returncode != 0
    assert "PUBLIC_APP_URL" in (r.stderr + r.stdout)


def test_prod_loads_secure_with_required_env():
    r = _setup({**_REQUIRED, "DOMAIN": "app.example.com"})
    assert r.returncode == 0, r.stderr
    # DEBUG off + HTTPS redirect + secure session cookie + HSTS + secure CSRF cookie.
    assert "OK True True True True" in r.stdout


# ── the transport switch: one variable, both halves (C14) ────────────────────


def test_without_a_domain_the_stack_runs_http_only():
    """Let's Encrypt cannot issue a certificate for a bare IP, so a deployment
    with no DNS name is necessarily HTTP-only — and the TLS settings must follow,
    not merely be "on and ignored". SECURE_SSL_REDIRECT on plain HTTP is an
    infinite redirect loop, and Secure cookies are never sent at all, so the
    admin and the whole allauth SSO session stop working. Not less secure:
    not working, and it would look like the app's fault rather than DNS's."""
    r = _setup({**_REQUIRED, "PUBLIC_APP_URL": "http://34.1.2.3"}, drop=("DOMAIN",))
    assert r.returncode == 0, r.stderr
    assert "OK False False False False" in r.stdout


def test_setting_domain_turns_the_whole_posture_on_together():
    """The switch-on has to be one variable. Four separate ones means a deploy
    where the certificate exists and the cookies are still not Secure."""
    r = _setup({**_REQUIRED, "DOMAIN": "pms.example.com"})
    assert r.returncode == 0, r.stderr
    assert "OK True True True True" in r.stdout


def test_an_empty_override_means_follow_domain_not_false():
    """Compose passes these as ``${VAR:-}``, so they arrive as empty strings on
    every deploy that does not override them. ``env.bool`` raises on "", which
    would take the whole stack down because somebody declined to override a
    default — and reading "" as False would silently disable TLS instead."""
    r = _setup({
        **_REQUIRED,
        "DOMAIN": "pms.example.com",
        "DJANGO_SECURE_SSL_REDIRECT": "",
        "DJANGO_SESSION_COOKIE_SECURE": "",
        "DJANGO_CSRF_COOKIE_SECURE": "",
        "DJANGO_HSTS_SECONDS": "",
    })
    assert r.returncode == 0, r.stderr
    assert "OK True True True True" in r.stdout


def test_an_explicit_override_still_wins():
    """TLS terminated at a load balancer that does not forward to us over HTTPS
    is a real topology; the derived default must remain overridable."""
    r = _setup({
        **_REQUIRED,
        "DOMAIN": "pms.example.com",
        "DJANGO_SECURE_SSL_REDIRECT": "false",
    })
    assert r.returncode == 0, r.stderr
    assert "OK False True True True" in r.stdout


def test_the_caddyfile_and_django_read_the_same_variable():
    """Two switches that must be flipped together are one switch somebody will
    flip halfway. Caddy decides ACME from DOMAIN; prod.py decides the redirect,
    the cookies and HSTS from the same name."""
    caddyfile = pathlib.Path("Caddyfile").read_text()
    assert "{$DOMAIN::80}" in caddyfile, (
        "the Caddy site address must fall back to :80 so a bare-IP deploy serves "
        "plain HTTP instead of attempting ACME for an address"
    )
    prod = pathlib.Path("config/settings/prod.py").read_text()
    assert 'env.str("DOMAIN"' in prod


def _compose_default(path, key):
    """The fallback in ``KEY: ${KEY:-value}`` from a compose file, or None."""
    import pathlib
    import re

    text = pathlib.Path(path).read_text()
    m = re.search(rf"^\s*{re.escape(key)}:\s*\$\{{{re.escape(key)}:-([^}}]*)\}}", text, re.M)
    return m.group(1) if m else None


def test_compose_never_pins_the_token_budget_below_the_settings_default():
    """A fix in settings that the deployment silently overrides is not a fix.

    ``LLM_MAX_TOKENS`` was raised to 4096 in ``base.py`` — with a comment explaining
    that 900 truncates a Gemini "thinking" model mid-JSON — while both compose files
    went on pinning 900. Agent-1 review drafts therefore failed 100% of the time, in
    dev AND in the prod compose, reporting "returned non-JSON content": a message that
    points at the model when the cause was our own ceiling. Nothing caught it because
    the settings default and the deployment value were never compared.
    """
    from django.conf import settings

    for path in ("docker-compose.yml", "docker-compose.prod.yml"):
        pinned = _compose_default(path, "LLM_MAX_TOKENS")
        assert pinned is not None, f"{path} no longer sets LLM_MAX_TOKENS — update this test"
        assert int(pinned) >= settings.LLM_MAX_TOKENS, (
            f"{path} pins LLM_MAX_TOKENS={pinned}, below the settings default "
            f"{settings.LLM_MAX_TOKENS} — long-form drafts will be truncated mid-JSON"
        )


# ── the TLS edge (Caddy), and what putting a proxy in front changes ───────────


def test_prod_declares_how_many_proxies_front_it():
    """Behind the TLS edge, the per-IP limit on the login surface must still bind.

    Every request now reaches Django with REMOTE_ADDR set to Caddy, so DRF
    identifies anonymous clients from X-Forwarded-For instead. A proxy APPENDS to
    that header rather than replacing it, so with NUM_PROXIES unset DRF keys on the
    whole chain — and a client that sends its own X-Forwarded-For lands in a fresh
    bucket on every request, which is unlimited login attempts. See the companion
    test below for the behaviour this buys.
    """
    probe = (
        "import django; django.setup(); from django.conf import settings; "
        "print(settings.REST_FRAMEWORK.get('NUM_PROXIES'))"
    )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["PMS_DOTENV_PATH"] = "/nonexistent/.env"
    env.setdefault("DJANGO_SECRET_KEY", "x" * 50)
    env.setdefault("DJANGO_ALLOWED_HOSTS", "example.com")
    env.setdefault("PUBLIC_APP_URL", "https://example.com")
    out = subprocess.run([sys.executable, "-c", probe], env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert int(out.stdout.strip()) >= 1, (
        "prod must declare how many proxies front it, or the anon throttle is forgeable"
    )


def test_a_forged_forwarded_for_cannot_buy_a_fresh_throttle_bucket():
    from django.conf import settings
    from django.test import RequestFactory, override_settings
    from rest_framework.throttling import AnonRateThrottle

    real = "203.0.113.9"

    def req(forged):
        # What Caddy hands Django: the client's own header, then the address Caddy saw.
        return RequestFactory().get(
            "/api/auth/login",
            REMOTE_ADDR="172.18.0.5",
            HTTP_X_FORWARDED_FOR=f"{forged}, {real}",
        )

    with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}):
        throttle = AnonRateThrottle()
        assert throttle.get_ident(req("1.1.1.1")) == real
        assert throttle.get_ident(req("1.1.1.1")) == throttle.get_ident(req("2.2.2.2")), (
            "rotating a forged X-Forwarded-For still yields a different bucket"
        )


def test_only_the_tls_edge_publishes_a_host_port():
    """Caddy is the single public door. Anything else binding a host port is
    reachable without TLS and without the headers the edge adds."""
    import pathlib

    import yaml

    compose = yaml.safe_load(pathlib.Path("docker-compose.prod.yml").read_text())
    publishing = sorted(n for n, s in compose["services"].items() if s.get("ports"))
    assert publishing == ["caddy"], f"these services publish host ports: {publishing}"


def test_no_committed_file_carries_a_credential_shaped_string():
    """The templates are placeholders; a real key reaching git is the one mistake
    that cannot be undone by a later commit."""
    import re

    from django.conf import settings

    pattern = re.compile(
        r"AIza[0-9A-Za-z_-]{30,}|AQ\.[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|"
        r"sk_live_[A-Za-z0-9]{10,}|rzp_live_[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|"
        r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|whsec_[A-Za-z0-9]{20,}"
    )
    # Walk the tree rather than shelling out to git: the runtime image ships no git
    # binary, and a guard that skips in the only place it runs guards nothing.
    skip_dirs = {"node_modules", ".git", "staticfiles", "media", "dist", "__pycache__",
                 ".venv", "venv", ".mypy_cache", ".pytest_cache"}
    suffixes = (".py", ".md", ".yml", ".yaml", ".json", ".ts", ".tsx", ".sh",
                ".conf", ".example", ".env", ".toml", ".cfg")
    root = pathlib.Path(settings.BASE_DIR)
    offenders = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if skip_dirs & set(path.relative_to(root).parts):
            continue
        # The developer's own .env is gitignored and legitimately holds real keys.
        if path.name == ".env":
            continue
        try:
            if pattern.search(path.read_text(errors="ignore")):
                offenders.append(str(path.relative_to(root)))
        except OSError:
            continue
    assert not offenders, f"credential-shaped strings in committed files: {offenders}"


def test_local_secret_files_are_gitignored():
    from django.conf import settings

    # Read .gitignore directly — see the note above about git not existing here.
    rules = {
        line.strip()
        for line in (pathlib.Path(settings.BASE_DIR) / ".gitignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for name, covering in ((".env", {".env", "*.env"}),
                           ("env-for-testing.txt", {"env-for-testing.txt"})):
        assert rules & covering, f"{name} is not covered by .gitignore (looked for {covering})"


def test_the_caddyfile_bakes_in_no_hostname():
    """A committed domain is somebody else's certificate; both come from the env."""
    import pathlib
    import re

    text = pathlib.Path("Caddyfile").read_text()
    # `{$DOMAIN::80}` — the env var, falling back to the bare :80 listener when
    # there is no hostname yet (C14). Still no hostname in the file either way.
    assert "{$DOMAIN" in text
    assert "{$ACME_EMAIL}" in text
    assert not re.search(r"^[a-z0-9.-]+\.(com|io|net|org|dev)\s*\{", text, re.M | re.I)
