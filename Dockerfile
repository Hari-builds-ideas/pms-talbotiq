# syntax=docker/dockerfile:1
# Single image used for web, celery-worker, celery-beat and the test runner.
# Code is bind-mounted in docker-compose for dev/test so iterating does not
# require an image rebuild — only a dependency change does.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.dev

WORKDIR /app

# Build deps for mysqlclient (compiled C extension) + runtime mysql client, plus
# the XML security libs that python3-saml's xmlsec/lxml bindings compile + link
# against (SAML 2.0 SP signature validation — see DECISIONS D25).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        default-mysql-client \
        pkg-config \
        libxml2-dev \
        libxmlsec1-dev \
        libxmlsec1-openssl \
        xmlsec1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching. INSTALL_DEV=true pulls the
# test toolchain too (the default for the compose-built image).
ARG INSTALL_DEV=true
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip \
    && if [ "$INSTALL_DEV" = "true" ]; then \
         pip install -r requirements-dev.txt; \
       else \
         pip install -r requirements.txt; \
       fi

COPY . .

# Collect static AT BUILD TIME, not at deploy time.
#
# STORAGES uses whitenoise's CompressedManifestStaticFilesStorage, which resolves
# every {% static %} through staticfiles.json and raises "Missing staticfiles
# manifest entry" when that file is absent — so under prod settings the allauth
# SSO pages (/accounts/) and the DRF browsable API 500 without this step. The JSON
# API never renders a template, which is why the test suite stays green either way.
#
# It belongs in the image rather than a release command because a PaaS one-off job
# runs in its own throwaway container: files written there never reach the web
# process. Baking it in also gives worker and beat the identical filesystem.
# Uses the image's default dev settings, so no secret is needed to build.
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Production app server: gunicorn driven by gunicorn.conf.py (workers/threads/
# timeouts/recycling). NOT runserver — the web tier runs as N stateless replicas.
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
