# Backup and restore

Everything on this page is runnable. It was written against the actual scripts,
and the restore drill in it has been executed against a real 27 MB / 78-table
dump of this database.

**The state before this work:** `scripts/backup_db.sh` existed and worked, and
nothing ever called it. There was no schedule, no offsite copy, and no evidence
that any dump had ever been restored. That is the shape of a backup story that
fails on the day it matters, so the three gaps are closed here: a schedule, an
offsite target, and a drill that proves the offsite copy restores.

---

## The pieces

| File | What it does |
| --- | --- |
| `scripts/backup_db.sh` | Takes one consistent dump, verifies it, uploads it to GCS, prunes old local copies. |
| `scripts/restore_drill.sh` | Restores a backup into a scratch database and checks three things. Never touches the live database. |
| `scripts/backup_alert.py` | Reports a failure to stderr and to Sentry. Always exits 0 so it can never mask the real error. |
| `scripts/gcs_backup_setup.sh` | One-time bucket setup: versioning, public-access block, lifecycle retention. |
| `deploy/systemd/pms-backup.{service,timer}` | The nightly schedule. |
| `deploy/systemd/pms-restore-drill.service` | The weekly drill, run against the **offsite** copy. |

---

## One-time setup on the VM

FACTS for this deployment: GCP VM `pms-prod` in `asia-south1-a`, Docker Compose,
GCS bucket `gs://axiom-backups`.

### 1. Prepare the bucket

From anywhere with `gcloud` authenticated:

```bash
GCS_BUCKET=gs://axiom-backups GCP_PROJECT=<your-project> \
  ./scripts/gcs_backup_setup.sh
```

This is idempotent. It sets:

- **public access blocked** (`pap set enforced`) — this bucket holds every
  performance review and every piece of 360 feedback in the product;
- **object versioning on** — so a bad script, a wrong path, or ransomware
  overwriting objects is recoverable rather than final;
- **lifecycle**: live objects move to NEARLINE after 7 days and are deleted after
  35; superseded versions are deleted 14 days after they were replaced.

Change the windows with `RETAIN_DAYS` / `RETAIN_NONCURRENT_DAYS` if the business
needs a different retention period.

### 2. Grant the VM write access

The VM's service account needs to write objects and nothing more:

```bash
gsutil iam ch serviceAccount:<VM_SA_EMAIL>:roles/storage.objectAdmin gs://axiom-backups
```

`objectAdmin` rather than `admin`: the job must create objects, not reconfigure
the bucket or turn versioning back off.

Confirm the VM can actually reach the bucket before trusting the schedule:

```bash
gcloud compute ssh pms-prod --zone asia-south1-a
gsutil ls gs://axiom-backups
```

### 3. Credentials file

The units read `/srv/pms/.env.backup`. It holds the database password, so it is
root-owned and unreadable by anyone else:

```bash
sudo install -m 0600 /dev/null /srv/pms/.env.backup
sudo tee /srv/pms/.env.backup >/dev/null <<'EOF'
DB_NAME=pms
DB_USER=pms
DB_PASSWORD=<the application database password>
DB_HOST=127.0.0.1
DB_PORT=3306
# optional — lets a failed backup page you instead of scrolling past in a log
SENTRY_DSN=
EOF
```

`SENTRY_DSN` is worth setting. Without it a failure is a line in
`journalctl` that nobody reads, and the first symptom is a missing backup during
an incident.

### 4. Install the schedule

```bash
sudo cp deploy/systemd/pms-backup.service      /etc/systemd/system/
sudo cp deploy/systemd/pms-backup.timer        /etc/systemd/system/
sudo cp deploy/systemd/pms-restore-drill.service /etc/systemd/system/
sudo mkdir -p /var/backups/pms
sudo systemctl daemon-reload
sudo systemctl enable --now pms-backup.timer
```

Weekly drill — a timer for it, created inline since it is three lines:

```bash
sudo tee /etc/systemd/system/pms-restore-drill.timer >/dev/null <<'EOF'
[Unit]
Description=Axiom PMS — weekly restore drill

[Timer]
OnCalendar=Sun *-*-* 04:30:00
RandomizedDelaySec=900
Persistent=true
Unit=pms-restore-drill.service

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now pms-restore-drill.timer
```

04:30 Sunday: after the nightly backup has finished and uploaded, on the quietest
day.

### 5. Prove it works now, not at 02:15

```bash
sudo systemctl start pms-backup.service
journalctl -u pms-backup.service -n 40 --no-pager
gsutil ls -l gs://axiom-backups | tail -5

sudo systemctl start pms-restore-drill.service
journalctl -u pms-restore-drill.service -n 40 --no-pager
```

Then check the schedule is really armed:

```bash
systemctl list-timers 'pms-*'
```

---

## Taking a backup by hand

```bash
cd /srv/pms
set -a; . ./.env.backup; set +a
GCS_BUCKET=gs://axiom-backups ./scripts/backup_db.sh
```

Expected output:

```
▶ dumping pms -> ./backups/pms-20260816-221213.sql.gz
✓ ./backups/pms-20260816-221213.sql.gz (27M, 78 tables)
▶ uploading to gs://axiom-backups
✓ offsite copy stored in gs://axiom-backups
✓ backup complete
```

The script refuses to call a file a backup until it has gzip-tested it and found
mysqldump's own `Dump completed` marker. A dump truncated by a full disk or a
killed connection is otherwise a perfectly plausible-looking file.

If `GCS_BUCKET` is set but `gsutil` is missing the script **fails** rather than
quietly keeping a local-only copy. A backup on the same disk as the database
dies with the host.

---

## The restore drill

```bash
cd /srv/pms
set -a; . ./.env.backup; set +a

./scripts/restore_drill.sh                                    # newest local file
./scripts/restore_drill.sh ./backups/pms-20260816-221213.sql.gz
GCS_BUCKET=gs://axiom-backups ./scripts/restore_drill.sh --from-bucket   # the real test
```

Real output from this repository:

```
▶ drilling ./backups/pms-20260816-221213.sql.gz into test_restore_drill
✓ restored
✓ row counts consistent across 78 tables
✓ audit_log immutability triggers present in the restored database
✓ restore drill passed — ./backups/pms-20260816-221213.sql.gz is recoverable
```

It checks three things, and each is there because it has a distinct failure mode:

1. **It loads at all.** Catches a truncated or half-uploaded dump that still
   passes `gzip -t`.
2. **Row counts match the live database, table by table**, using real
   `COUNT(*)` — `information_schema.TABLE_ROWS` is an InnoDB estimate and is
   useless here. Restored *behind* live is normal (the backup predates recent
   writes) and is reported, not failed. Restored *ahead* of live is impossible
   and fails the drill.
3. **The `audit_log` triggers came back.** This is the one most likely to be
   silently wrong. The triggers only survive because the dump is taken with
   `--triggers`, and a restore into a server that will not let a non-SUPER user
   create them **succeeds with the triggers simply missing**. You would recover
   all your data and quietly lose audit-log immutability — a compliance
   invariant of this product — without a single error message.

Scheduled runs use `--from-bucket` deliberately. Restoring the local copy proves
the local copy is good and tells you nothing about the offsite one, which is the
copy you will actually reach for.

**The scratch database is named `test_restore_drill`, not `pms_restore_drill`.**
The application's MySQL user is scoped to its own database plus `test\_%`
(`db/init.sql`), so `pms_restore_drill` is outside the grant and the drill dies
with "Access denied" — the grant doing its job. Borrowing the `test_` prefix lets
the drill run as the ordinary app user with no extra privilege. A drill that
needs elevated rights is one nobody schedules.

---

## Restoring for real

### Into a scratch copy first (do this unless the database is gone)

Most "we need the backup" moments are a bad migration or a wrong bulk update, not
a dead host. Restore beside production and look before you overwrite anything:

```bash
cd /srv/pms
set -a; . ./.env.backup; set +a

gsutil ls gs://axiom-backups | tail -10                 # pick the archive
gsutil cp gs://axiom-backups/pms-20260816-221213.sql.gz ./backups/

docker compose exec -T mysql mysql -upms -p"$DB_PASSWORD" \
  -e "CREATE DATABASE test_recovery CHARACTER SET utf8mb4;"
gunzip -c ./backups/pms-20260816-221213.sql.gz \
  | docker compose exec -T -e MYSQL_PWD="$DB_PASSWORD" mysql \
      mysql -upms test_recovery
```

Then query `test_recovery` to confirm it holds what you expect, and copy back
only the rows you need.

### Full replacement (the host is gone, or the data is unrecoverable)

```bash
cd /srv/pms
docker compose stop web worker beat     # stop writers; leave mysql running
```

Take a dump of the current broken state first. It costs two minutes and it is the
only way back if the backup turns out to be the wrong one:

```bash
./scripts/backup_db.sh                  # names itself with a fresh timestamp
```

Then replace:

```bash
docker compose exec -T mysql mysql -upms -p"$DB_PASSWORD" \
  -e "DROP DATABASE pms; CREATE DATABASE pms CHARACTER SET utf8mb4;"
gunzip -c ./backups/pms-20260816-221213.sql.gz \
  | docker compose exec -T -e MYSQL_PWD="$DB_PASSWORD" mysql mysql -upms pms
```

Verify before letting traffic back in:

```bash
# the audit triggers must exist, or immutability is gone
docker compose exec -T mysql mysql -upms -p"$DB_PASSWORD" -N -B -e \
  "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS
    WHERE TRIGGER_SCHEMA='pms' AND EVENT_OBJECT_TABLE='audit_log';"
# expect: audit_log_block_delete, audit_log_block_update

docker compose run --rm web python manage.py migrate --check
docker compose run --rm web python manage.py check --deploy
```

If `migrate --check` reports unapplied migrations, the backup predates the
deployed code. Run `python manage.py migrate` — the schema moves forward to match
the running image.

Then:

```bash
docker compose start web worker beat
```

### After any restore

- **Sessions survive**, because JWTs are signed, not stored. Anyone whose token
  was issued after the backup was taken keeps working; nothing needs clearing.
- **Redis is not restored and does not need to be** — it holds cache and the
  Celery queue, both rebuildable. Celery tasks that were queued between the
  backup and the incident are lost. If any of them mattered, they need
  re-triggering by hand.
- **Tell people what window was lost.** A nightly backup means up to 24 hours of
  reviews, goals and feedback can be gone. Users who wrote something in that
  window need to know it is not there rather than discovering it later.

---

## What this does and does not protect against

| Scenario | Covered | How |
| --- | --- | --- |
| VM lost / disk failure | Yes | Offsite copy in GCS, restored per the steps above. |
| Bad migration or bad bulk update | Yes | Restore into `test_recovery` and copy rows back. |
| Object deleted or overwritten in the bucket | Yes | Object versioning keeps the previous generation. |
| Bucket-level compromise | Partly | Public access is blocked and the VM has object-level rights only. A stolen project-owner credential can still destroy the bucket. |
| Data loss inside the last 24 hours | **No** | Backups are nightly. See below. |
| Uploaded files / media | **No** | Only MySQL is dumped. See below. |

### Known gaps, stated plainly

- **RPO is 24 hours.** Nightly dumps, no binlog shipping. Worst case, a day of
  performance data is gone. Closing this means enabling binary logs and shipping
  them, or moving to Cloud SQL with point-in-time recovery. That is a real
  decision about cost, not an oversight — it is recorded here so the choice is
  visible rather than assumed.
- **RTO is roughly 30–60 minutes** on a surviving host: download, drop, load a
  27 MB dump, verify. If the VM itself must be rebuilt, add the rebuild time.
- **Media is not backed up.** The dump covers MySQL only. Any user-uploaded file
  stored on the VM's filesystem is not in it. Once media moves to GCS it inherits
  that bucket's own durability; until then it is unprotected.
- **The drill compares row counts, not content.** It proves the dump is
  structurally complete and the triggers came back. It does not prove every field
  is byte-identical.

---

## When the nightly backup fails

`backup_alert.py` reports to stderr and to Sentry (when `SENTRY_DSN` is set) and
always exits 0, so it can never hide the original failure.

```bash
systemctl status pms-backup.service
journalctl -u pms-backup.service --since '2 days ago' --no-pager
```

The three failures that actually happen:

| Message | Cause | Fix |
| --- | --- | --- |
| `Access denied ... (using password: NO)` | `MYSQL_PWD` did not reach the container. | Confirm `/srv/pms/.env.backup` is readable by root and `DB_PASSWORD` is set in it. |
| `GCS_BUCKET is set but gsutil is not installed` | Cloud SDK missing on the VM. | Install it. Until then the backup is local-only, which is not a backup. |
| `has no 'Dump completed' marker` | Disk filled, or the connection was killed mid-dump. | `df -h`, clear space, re-run. The partial file is already deleted. |

A run that produced no offsite object is a failed run even when it printed a
local path. Check the bucket, not the log line:

```bash
gsutil ls -l gs://axiom-backups | tail -5
```
