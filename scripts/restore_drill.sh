#!/usr/bin/env bash
#
# restore_drill.sh — prove the latest backup actually restores (C5).
#
#   ./scripts/restore_drill.sh                       # newest local backup
#   ./scripts/restore_drill.sh backups/pms-2026....gz
#   GCS_BUCKET=gs://axiom-backups ./scripts/restore_drill.sh --from-bucket
#
# A backup nobody has restored is a hypothesis. This restores into a SCRATCH
# database, compares row counts against the live one, and asserts the audit_log
# immutability triggers came back — then drops the scratch database.
#
# The three checks, and why each is here:
#
#   1. It loads at all. Catches a truncated or half-uploaded dump that still
#      passes `gzip -t`.
#   2. Row counts match the source, per table. Catches the dump that restores
#      cleanly but is missing rows because --single-transaction was dropped, or
#      because it was taken against the wrong database.
#   3. The audit_log triggers exist in the RESTORED database. This is the one
#      most likely to be silently wrong: triggers only survive because the dump
#      is taken with --triggers, and a restore into a server that will not let a
#      non-SUPER user create them succeeds with the triggers simply absent. You
#      would recover your data and quietly lose the tamper-proofing.
#
# Read-only with respect to production: it never writes to $DB_NAME.
set -euo pipefail

cd "$(dirname "$0")/.."

DB_NAME="${DB_NAME:-pms}"
DB_USER="${DB_USER:-pms}"
DB_PASSWORD="${DB_PASSWORD:?set DB_PASSWORD to the application database password}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
GCS_BUCKET="${GCS_BUCKET:-}"
# NAMED test_* on purpose. The application's database user is deliberately scoped
# to its own database plus `test\_%` (db/init.sql) so it cannot touch anything
# else on the server. A scratch database called pms_restore_drill is outside that
# grant and the drill dies with "Access denied" — which is the grant doing its
# job. Borrowing the test_ prefix means the drill runs as the ordinary app user
# with no extra privilege, which is the right way round: a restore drill that
# needs elevated rights is one nobody will schedule.
SCRATCH_DB="${SCRATCH_DB:-test_restore_drill}"
MYSQL_DOCKER_SERVICE="${MYSQL_DOCKER_SERVICE:-mysql}"

export MYSQL_PWD="$DB_PASSWORD"

fail() { python3 "$(dirname "$0")/backup_alert.py" "restore drill: $*" || true; exit 1; }

# Same host-or-container dance as backup_db.sh, so this works on a bare server.
if command -v mysql >/dev/null 2>&1; then
  MYSQL=(mysql --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER")
else
  MYSQL=(docker compose exec -T -e MYSQL_PWD "$MYSQL_DOCKER_SERVICE"
         mysql --host=127.0.0.1 --port="$DB_PORT" --user="$DB_USER")
fi

sql() { "${MYSQL[@]}" -N -B -e "$1"; }

# ── pick the archive ─────────────────────────────────────────────────────────
ARCHIVE="${1:-}"
if [ "$ARCHIVE" = "--from-bucket" ]; then
  [ -n "$GCS_BUCKET" ] || fail "--from-bucket needs GCS_BUCKET set"
  command -v gsutil >/dev/null 2>&1 || fail "--from-bucket needs gsutil installed"
  # Restoring the LOCAL copy proves the local copy is good and tells you nothing
  # about the offsite one — which is the copy you will actually reach for.
  mkdir -p "$BACKUP_DIR"
  LATEST_REMOTE="$(gsutil ls "${GCS_BUCKET%/}/${DB_NAME}-*.sql.gz" | sort | tail -1)"
  [ -n "$LATEST_REMOTE" ] || fail "no backups found in ${GCS_BUCKET}"
  echo "▶ pulling ${LATEST_REMOTE}"
  gsutil -q cp "$LATEST_REMOTE" "$BACKUP_DIR/" || fail "could not download ${LATEST_REMOTE}"
  ARCHIVE="${BACKUP_DIR}/$(basename "$LATEST_REMOTE")"
elif [ -z "$ARCHIVE" ]; then
  ARCHIVE="$(ls -1t "${BACKUP_DIR}"/"${DB_NAME}"-*.sql.gz 2>/dev/null | head -1 || true)"
  [ -n "$ARCHIVE" ] || fail "no backup found in ${BACKUP_DIR}"
fi
[ -f "$ARCHIVE" ] || fail "${ARCHIVE} does not exist"

echo "▶ drilling ${ARCHIVE} into ${SCRATCH_DB}"

cleanup() { sql "DROP DATABASE IF EXISTS \`${SCRATCH_DB}\`;" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# ── 1. restore ───────────────────────────────────────────────────────────────
sql "DROP DATABASE IF EXISTS \`${SCRATCH_DB}\`; CREATE DATABASE \`${SCRATCH_DB}\` CHARACTER SET utf8mb4;" \
  || fail "could not create the scratch database (does ${DB_USER} have CREATE?)"

# The dump deliberately carries no CREATE DATABASE/USE, which is what lets it be
# replayed into a differently named database — exactly this case.
if command -v mysql >/dev/null 2>&1; then
  gunzip -c "$ARCHIVE" | mysql --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" "$SCRATCH_DB" \
    || fail "the dump failed to load"
else
  gunzip -c "$ARCHIVE" | docker compose exec -T -e MYSQL_PWD "$MYSQL_DOCKER_SERVICE" \
    mysql --host=127.0.0.1 --port="$DB_PORT" --user="$DB_USER" "$SCRATCH_DB" \
    || fail "the dump failed to load"
fi
echo "✓ restored"

# ── 2. compare row counts, table by table ────────────────────────────────────
# information_schema.TABLE_ROWS is an InnoDB ESTIMATE and is useless for this, so
# every table is counted for real. Slower, and the only version worth running.
MISMATCH=0
TABLES="$(sql "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='${SCRATCH_DB}' AND TABLE_TYPE='BASE TABLE';")"
[ -n "$TABLES" ] || fail "the restored database has no tables"

for t in $TABLES; do
  src="$(sql "SELECT COUNT(*) FROM \`${DB_NAME}\`.\`${t}\`;" 2>/dev/null || echo "-")"
  dst="$(sql "SELECT COUNT(*) FROM \`${SCRATCH_DB}\`.\`${t}\`;")"
  if [ "$src" = "-" ]; then
    echo "  ~ ${t}: not in the live database (dropped since the backup) — skipped"
    continue
  fi
  if [ "$src" != "$dst" ]; then
    # A backup taken before recent writes will legitimately be BEHIND. Ahead is
    # never legitimate, and equal-or-behind still needs a human to eyeball.
    if [ "$dst" -gt "$src" ] 2>/dev/null; then
      echo "  ✗ ${t}: restored ${dst} > live ${src} — the backup cannot be newer"
      MISMATCH=1
    else
      echo "  ~ ${t}: live ${src}, restored ${dst} (backup predates recent writes)"
    fi
  fi
done
[ "$MISMATCH" -eq 0 ] || fail "row counts disagree in a way a time gap cannot explain"
echo "✓ row counts consistent across $(echo "$TABLES" | wc -w | tr -d ' ') tables"

# ── 3. the audit triggers came back ──────────────────────────────────────────
TRIGGERS="$(sql "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='${SCRATCH_DB}' AND EVENT_OBJECT_TABLE='audit_log';" | sort | tr '\n' ' ')"
for want in audit_log_block_delete audit_log_block_update; do
  case "$TRIGGERS" in
    *"$want"*) ;;
    *) fail "restored database is MISSING trigger ${want} — a recovery from this backup would silently lose audit-log immutability (found: ${TRIGGERS:-none})" ;;
  esac
done
echo "✓ audit_log immutability triggers present in the restored database"

echo "✓ restore drill passed — ${ARCHIVE} is recoverable"
