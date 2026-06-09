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

# Build deps for mysqlclient (compiled C extension) + runtime mysql client.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        default-mysql-client \
        pkg-config \
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

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
