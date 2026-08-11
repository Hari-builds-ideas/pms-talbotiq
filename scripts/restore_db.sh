#!/usr/bin/env bash
#
# restore_db.sh — restore a dump from backup_db.sh, with a safety net.
#
#   ./scripts/restore_db.sh backups/pms-20260812-020000.sql.gz            # DRILL (default)
#   RESTORE_TARGET=pms ./scripts/restore_db.sh backups/pms-....sql.gz     # the real thing
#
# By DEFAULT this restores into a scratch database (`<name>_restore_check`), never
# over your live data, and prints the row counts it found. That is the drill you
# should be running monthly: it exercises the whole path and proves the dump is
# replayable, without a maintenance window and without the chance of destroying the
# database you were trying to protect.
#
# Restoring OVER the live database is deliberately awkward: you must name it in
# RESTORE_TARGET and type the confirmation. A restore is the most dangerous command
# in this repo — it is run by a stressed human, usually at night.
set -euo pipefail

cd "$(dirname "$0")/.."

DUMP="${1:?usage: restore_db.sh <dump.sql.gz>}"
[ -f "$DUMP" ] || { echo "✗ no such file: $DUMP"; exit 1; }

DB_NAME="${DB_NAME:-pms}"
DB_USER="${DB_USER:-root}"          # creating a database needs a privileged user
DB_PASSWORD="${DB_PASSWORD:?set DB_PASSWORD (or DB_ROOT_PASSWORD) for the restore user}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
RESTORE_TARGET="${RESTORE_TARGET:-${DB_NAME}_restore_check}"

MYSQL_DOCKER_SERVICE="${MYSQL_DOCKER_SERVICE:-mysql}"
# Exported, and forwarded by NAME into the container — a variable set on the host
# shell is invisible to `docker compose exec`, which reads as "Access denied …
# (using password: NO)". Passing it by name also keeps it out of the command line.
export MYSQL_PWD="$DB_PASSWORD"
if command -v mysql >/dev/null 2>&1; then
  RUNNER=(mysql)
else
  RUNNER=(docker compose exec -T -e MYSQL_PWD "$MYSQL_DOCKER_SERVICE" mysql)
  DB_HOST_EFFECTIVE=127.0.0.1
fi
DB_HOST_EFFECTIVE="${DB_HOST_EFFECTIVE:-$DB_HOST}"

run_sql() {
  "${RUNNER[@]}" \
    --host="$DB_HOST_EFFECTIVE" --port="$DB_PORT" --user="$DB_USER" \
    --default-character-set=utf8mb4 "$@"
}

# ── refuse to clobber production by accident ─────────────────────────────────
if [ "$RESTORE_TARGET" = "$DB_NAME" ]; then
  echo "⚠  This will OVERWRITE the live database '${DB_NAME}' on ${DB_HOST_EFFECTIVE}."
  echo "   Everything written since the dump was taken will be gone."
  printf "   Type the database name to confirm: "
  read -r confirm
  [ "$confirm" = "$DB_NAME" ] || { echo "✗ aborted"; exit 1; }
fi

gzip -t "$DUMP" || { echo "✗ ${DUMP} is not a valid gzip stream"; exit 1; }
gunzip -c "$DUMP" | tail -5 | grep -q "Dump completed" \
  || { echo "✗ ${DUMP} is truncated (no 'Dump completed' marker) — do not restore it"; exit 1; }

echo "▶ restoring ${DUMP} -> ${RESTORE_TARGET}"
run_sql -e "DROP DATABASE IF EXISTS \`${RESTORE_TARGET}\`;
            CREATE DATABASE \`${RESTORE_TARGET}\`
              CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# The dump carries no CREATE DATABASE/USE (see backup_db.sh), which is what lets it
# be replayed into a differently named database like this one.
gunzip -c "$DUMP" | "${RUNNER[@]}" \
  --host="$DB_HOST_EFFECTIVE" --port="$DB_PORT" --user="$DB_USER" \
  --default-character-set=utf8mb4 "$RESTORE_TARGET"

# ── prove it landed ──────────────────────────────────────────────────────────
echo "▶ verifying"
run_sql -N -B -e "
  SELECT CONCAT('  tables: ', COUNT(*)) FROM information_schema.tables
   WHERE table_schema='${RESTORE_TARGET}';"

# Real db_table names (NOT the app_model convention — `tenant` and `audit_log` differ).
# A wrong name here counts as "n/a", which looks like a note and reads like a pass, so
# a missing table would slip through the drill unnoticed. MISSING is a hard failure.
MISSING=0
for t in identity_user tenant goals_goal reviews_review audit_log; do
  if n=$(run_sql -N -B -e "SELECT COUNT(*) FROM \`${RESTORE_TARGET}\`.\`${t}\`;" 2>/dev/null); then
    printf "  %-22s %s\n" "$t" "$n"
  else
    printf "  %-22s MISSING\n" "$t"
    MISSING=1
  fi
done
if [ "$MISSING" -ne 0 ]; then
  echo "✗ core tables are missing from the restore — this dump is NOT usable"
  exit 1
fi

echo "✓ restore verified into ${RESTORE_TARGET}"
if [ "$RESTORE_TARGET" != "$DB_NAME" ]; then
  echo
  echo "  This was a DRILL — the live database was not touched."
  echo "  Inspect it, then drop it:"
  echo "    DROP DATABASE \`${RESTORE_TARGET}\`;"
  echo "  To restore for real: RESTORE_TARGET=${DB_NAME} $0 ${DUMP}"
fi
