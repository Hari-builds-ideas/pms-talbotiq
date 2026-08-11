# Backups and restore

Two scripts. Both read credentials from the environment and work on a bare host with
nothing installed but Docker (they fall back to running the MySQL client inside the
compose `mysql` service).

- `scripts/backup_db.sh` — one consistent, compressed, **verified** dump.
- `scripts/restore_db.sh` — restore, defaulting to a **drill** that cannot touch live data.

Both were run for real against this database before being written up; the numbers below
are from that run.

---

## Taking a backup

```bash
./scripts/backup_db.sh                                   # -> ./backups/pms-<UTC stamp>.sql.gz
BACKUP_DIR=/mnt/backups ./scripts/backup_db.sh
S3_BUCKET=s3://acme-pms-backups ./scripts/backup_db.sh   # also copies offsite
```

Scheduled, which is the only way it actually happens:

```cron
0 2 * * *  cd /srv/pms && S3_BUCKET=s3://acme-pms-backups ./scripts/backup_db.sh >> /var/log/pms-backup.log 2>&1
```

**Why the flags are what they are** — these are the details that decide whether the file
is restorable:

| Flag | Why |
|---|---|
| `--single-transaction` | Consistent snapshot **without locking the app out**. Safe because every table is InnoDB; on MyISAM it would silently produce a torn dump. |
| `--routines --triggers --events` | Omit them and you restore a database that is subtly not the one you had. |
| `--set-gtid-purged=OFF` | Keeps the dump replayable into a fresh server with its own GTID history — the usual restore target. |
| *no* `--databases` | The dump carries no `CREATE DATABASE`/`USE`, so it can be replayed into a **differently named** database. That is what makes the drill below possible. |
| `MYSQL_PWD` (exported, forwarded by name) | Keeps the password out of the process list, which `ps` shows to every user on the box. |

**Verification is part of the backup.** The script gzip-tests the file and greps for
mysqldump's own `Dump completed` marker, deleting the file and exiting non-zero if
either fails. Without that check a dump truncated by a full disk or a killed connection
is an ordinary-looking file that fails only when you need it.

Real run:

```
▶ dumping pms -> /tmp/pmsbackup/pms-20260811-183509.sql.gz
✓ /tmp/pmsbackup/pms-20260811-183509.sql.gz ( 27M, 78 tables)
⚠ S3_BUCKET unset — this backup lives on the same host as the database.
```

That warning is deliberate. **A backup on the same disk as the database is not a
backup** — it dies with the host, which is the failure you are insuring against.

---

## Restoring — the drill (run this monthly)

By default the restore goes into a scratch database `pms_restore_check` and **cannot
touch live data**:

```bash
DB_USER=root DB_PASSWORD="$DB_ROOT_PASSWORD" ./scripts/restore_db.sh backups/pms-20260811-183509.sql.gz
```

Real run, against the 27M dump above:

```
▶ restoring … -> pms_restore_check
▶ verifying
  tables: 78
  identity_user          80914
  tenant                 6
  goals_goal             81566
  reviews_review         219
  audit_log              15208
✓ restore verified into pms_restore_check
  This was a DRILL — the live database was not touched.
```

It counts rows in five core tables by their **real** `db_table` names (note `tenant` and
`audit_log` do *not* follow the `app_model` convention). A name that does not exist is
reported as `MISSING` and fails the script — an earlier version printed `n/a`, which
reads like a footnote and would have let a missing table pass the drill.

A truncated dump is refused before anything is dropped:

```
✗ /tmp/truncated.sql.gz is truncated (no 'Dump completed' marker) — do not restore it
```

Afterwards: `DROP DATABASE pms_restore_check;`

## Restoring for real

```bash
RESTORE_TARGET=pms DB_USER=root DB_PASSWORD="$DB_ROOT_PASSWORD" \
  ./scripts/restore_db.sh backups/pms-20260811-183509.sql.gz
```

This is deliberately awkward: you must name the live database in `RESTORE_TARGET` **and**
type it at the confirmation prompt. It is the most dangerous command in the repo and it
gets run by a tired human at 3am.

Everything written since the dump was taken is lost. Before running it, take a dump of
the current broken state — a bad database is still evidence, and you only get one chance
to keep it.

---

## What a human still must decide

1. **Where the offsite copy goes.** Set `S3_BUCKET` (or equivalent) — until then every
   backup shares a disk with the thing it is protecting. Enable bucket **versioning** and
   a lifecycle rule, and keep the credentials write-only if you can: ransomware that
   reaches the host should not be able to delete the backups.
2. **RPO/RTO.** Nightly dumps mean up to 24h of loss. If that is too much, enable binlog
   archiving for point-in-time recovery — dumps alone cannot give you that.
3. **Encryption at rest** for the dumps. They contain every employee's performance data;
   treat them exactly like the database.
4. **Put the drill in the calendar.** A restore procedure nobody has run is a hypothesis.
   The drill is safe, takes about a minute, and touches nothing live.
5. **Back up the `caddy_data` volume too** (certificates + ACME account key) — see item 1.
6. **Managed database?** If you move to RDS/Cloud SQL, use its automated backups and PITR
   and keep these scripts for logical exports and migrations. Snapshot backups and logical
   dumps solve different problems; you want both.
