#!/usr/bin/env bash
#
# backup_db.sh — one consistent, compressed, verified MySQL dump.
#
#   ./scripts/backup_db.sh                      # -> ./backups/pms-YYYYmmdd-HHMMSS.sql.gz
#   BACKUP_DIR=/mnt/backups ./scripts/backup_db.sh
#   S3_BUCKET=s3://acme-pms-backups ./scripts/backup_db.sh    # also copies offsite
#
# Run it from cron/systemd on the host, or as a scheduled job on your platform:
#   0 2 * * *  cd /srv/pms && S3_BUCKET=s3://acme-pms-backups ./scripts/backup_db.sh >> /var/log/pms-backup.log 2>&1
#
# Design notes, because the details are what make a backup restorable:
#
#   --single-transaction  dumps inside one consistent snapshot WITHOUT locking the
#                         app out. Every table here is InnoDB, so this is safe; on
#                         MyISAM it would silently produce a torn dump.
#   --routines --triggers --events
#                         a schema-only dump that omits these restores a database
#                         that is subtly not the one you had.
#   --set-gtid-purged=OFF keeps the dump replayable into a fresh server that has its
#                         own GTID history (the usual restore target).
#   NO --databases        so the dump has no CREATE DATABASE/USE, and can therefore
#                         be restored into a DIFFERENTLY NAMED database — which is
#                         exactly what a restore drill needs, and what you want when
#                         restoring production into a scratch DB to look at it first.
#
# The dump is gzip-tested and checked for mysqldump's own completion marker before it
# is allowed to count as a backup. An unverified backup is a guess.
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"
# GCS is the configured offsite target for this deployment (GCP VM + compose).
#   GCS_BUCKET=gs://axiom-backups
GCS_BUCKET="${GCS_BUCKET:-}"

# ── alert on failure (C5) ────────────────────────────────────────────────────
# A backup job that fails silently is worse than no backup job, because it
# produces the BELIEF that backups exist. Any non-zero exit is reported: to
# stderr always, and to Sentry when a DSN is configured.
fail() {
  python3 "$(dirname "$0")/backup_alert.py" "$*" || true
  exit 1
}
trap 'fail "unexpected error at line $LINENO"' ERR

# Credentials come from the environment (same names the app uses). Never inline.
DB_NAME="${DB_NAME:-pms}"
DB_USER="${DB_USER:-pms}"
# NB: no apostrophes in a ${VAR:?message} — bash parses the message for quoting, so
# one stray ' breaks the whole script with a syntax error 40 lines further down.
DB_PASSWORD="${DB_PASSWORD:?set DB_PASSWORD to the application database password}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"

# Run mysqldump inside the compose mysql service unless a client is on the host —
# so this works on a bare server with nothing but Docker installed.
MYSQL_DOCKER_SERVICE="${MYSQL_DOCKER_SERVICE:-mysql}"
# MYSQL_PWD keeps the password out of the process list (`ps` is world-readable);
# mysqldump's own --password= would publish it. It must be EXPORTED, and when the
# client runs inside the container it must be forwarded explicitly — a variable set
# on the host shell is not visible to `docker compose exec`, which is what produced
# "Access denied … (using password: NO)". `-e MYSQL_PWD` passes it by name, so the
# value never appears in the docker command line either.
export MYSQL_PWD="$DB_PASSWORD"
if command -v mysqldump >/dev/null 2>&1; then
  RUNNER=(mysqldump)
else
  RUNNER=(docker compose exec -T -e MYSQL_PWD "$MYSQL_DOCKER_SERVICE" mysqldump)
  DB_HOST_EFFECTIVE=127.0.0.1   # inside the container the server is local
fi
DB_HOST_EFFECTIVE="${DB_HOST_EFFECTIVE:-$DB_HOST}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/${DB_NAME}-${STAMP}.sql.gz"

echo "▶ dumping ${DB_NAME} -> ${OUT}"

"${RUNNER[@]}" \
  --host="$DB_HOST_EFFECTIVE" --port="$DB_PORT" --user="$DB_USER" \
  --single-transaction --quick --routines --triggers --events \
  --set-gtid-purged=OFF --default-character-set=utf8mb4 \
  --no-tablespaces \
  "$DB_NAME" | gzip -9 > "$OUT"

# ── verify, or it is not a backup ────────────────────────────────────────────
gzip -t "$OUT" || { rm -f "$OUT"; fail "${OUT} is not a valid gzip stream"; }

# mysqldump writes this marker only after a clean finish. Without the check, a dump
# truncated by a disk-full or a killed connection looks like a perfectly good file.
if ! gunzip -c "$OUT" | tail -5 | grep -q "Dump completed"; then
  rm -f "$OUT"
  fail "${OUT} has no 'Dump completed' marker — the dump was truncated"
fi

SIZE="$(du -h "$OUT" | cut -f1)"
TABLES="$(gunzip -c "$OUT" | grep -c '^CREATE TABLE' || true)"
echo "✓ ${OUT} (${SIZE}, ${TABLES} tables)"

# ── offsite ──────────────────────────────────────────────────────────────────
# A backup on the same disk as the database is not a backup: it dies with the host.
if [ -n "$S3_BUCKET" ]; then
  if command -v aws >/dev/null 2>&1; then
    echo "▶ uploading to ${S3_BUCKET}"
    aws s3 cp "$OUT" "${S3_BUCKET%/}/$(basename "$OUT")" --only-show-errors
    echo "✓ offsite copy stored"
  else
    echo "⚠ S3_BUCKET is set but the aws CLI is not installed — LOCAL COPY ONLY"
  fi
fi

if [ -n "$GCS_BUCKET" ]; then
  if command -v gsutil >/dev/null 2>&1; then
    echo "▶ uploading to ${GCS_BUCKET}"
    # -n: never overwrite an existing object. Filenames carry a UTC timestamp, so
    # a collision means the clock moved backwards or a job ran twice — either way
    # silently replacing yesterday's good backup is the wrong response.
    gsutil -q cp -n "$OUT" "${GCS_BUCKET%/}/$(basename "$OUT")" \
      || fail "gsutil upload to ${GCS_BUCKET} failed"
    echo "✓ offsite copy stored in ${GCS_BUCKET}"
  else
    fail "GCS_BUCKET is set but gsutil is not installed — the backup is LOCAL ONLY"
  fi
fi

if [ -z "$S3_BUCKET" ] && [ -z "$GCS_BUCKET" ]; then
  echo "⚠ no offsite bucket configured — this backup lives on the same host as"
  echo "  the database, so it dies with the host. Set GCS_BUCKET."
fi

# ── retention (local only; lifecycle rules own the bucket) ────────────────────
find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -print -delete \
  | sed 's/^/  pruned /' || true

echo "✓ backup complete"
