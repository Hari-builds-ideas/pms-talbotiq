#!/usr/bin/env bash
#
# gcs_backup_setup.sh — one-time setup of the backup bucket (C5).
#
#   GCS_BUCKET=gs://axiom-backups GCP_PROJECT=my-project ./scripts/gcs_backup_setup.sh
#
# Idempotent: safe to re-run. It creates the bucket if missing, then applies the
# two settings that decide whether the backups are actually worth having.
#
# WHY VERSIONING. Retention alone is not protection. The failure that destroys a
# backup set is rarely "the disk died" — it is a bad script, a wrong path, or
# ransomware overwriting or deleting objects. Versioning keeps the previous
# generation of an overwritten or deleted object, so a destructive mistake is
# recoverable rather than final.
#
# WHY UNIFORM ACCESS + NO PUBLIC ACCESS. This bucket holds every performance
# review, every piece of 360 feedback and every employee record in the product.
# A publicly readable backup bucket is the single worst outcome available here,
# and it is two clicks away by default.
set -euo pipefail

GCS_BUCKET="${GCS_BUCKET:?set GCS_BUCKET, e.g. gs://axiom-backups}"
GCP_PROJECT="${GCP_PROJECT:-}"
GCS_LOCATION="${GCS_LOCATION:-asia-south1}"   # keep it near the VM (FACTS: asia-south1-a)
# How long a daily backup is kept. 35 days covers a monthly reporting cycle plus
# slack for someone noticing a problem late.
RETAIN_DAYS="${RETAIN_DAYS:-35}"
# Non-current (superseded/deleted) versions are kept shorter — they exist to undo
# an accident, which is noticed in days, not weeks.
RETAIN_NONCURRENT_DAYS="${RETAIN_NONCURRENT_DAYS:-14}"

command -v gsutil >/dev/null 2>&1 || {
  echo "gsutil is not installed. Install the Google Cloud SDK first." >&2; exit 1; }

echo "▶ bucket: ${GCS_BUCKET}"
if gsutil ls -b "$GCS_BUCKET" >/dev/null 2>&1; then
  echo "  already exists"
else
  ARGS=(mb -b on -l "$GCS_LOCATION")
  [ -n "$GCP_PROJECT" ] && ARGS=(-u "$GCP_PROJECT" "${ARGS[@]}")
  gsutil "${ARGS[@]}" "$GCS_BUCKET"
  echo "  created in ${GCS_LOCATION} with uniform bucket-level access"
fi

echo "▶ blocking all public access"
gsutil pap set enforced "$GCS_BUCKET"

echo "▶ enabling object versioning"
gsutil versioning set on "$GCS_BUCKET"

echo "▶ applying the lifecycle policy"
LIFECYCLE="$(mktemp)"
trap 'rm -f "$LIFECYCLE"' EXIT
cat > "$LIFECYCLE" <<JSON
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": ${RETAIN_DAYS}, "isLive": true}
    },
    {
      "action": {"type": "Delete"},
      "condition": {"daysSinceNoncurrentTime": ${RETAIN_NONCURRENT_DAYS}}
    },
    {
      "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
      "condition": {"age": 7, "isLive": true}
    }
  ]
}
JSON
gsutil lifecycle set "$LIFECYCLE" "$GCS_BUCKET"

echo
echo "✓ ${GCS_BUCKET} ready:"
echo "    public access  : blocked (enforced)"
echo "    versioning     : on"
echo "    live objects   : NEARLINE after 7d, deleted after ${RETAIN_DAYS}d"
echo "    old versions   : deleted ${RETAIN_NONCURRENT_DAYS}d after being superseded"
echo
echo "Next: give the VM's service account object write access to this bucket, e.g."
echo "  gsutil iam ch serviceAccount:<SA_EMAIL>:roles/storage.objectAdmin ${GCS_BUCKET}"
echo "Then verify a real round trip:"
echo "  GCS_BUCKET=${GCS_BUCKET} ./scripts/backup_db.sh"
echo "  GCS_BUCKET=${GCS_BUCKET} ./scripts/restore_drill.sh --from-bucket"
