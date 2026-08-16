#!/usr/bin/env python3
"""
Report a backup failure (C5).

Kept as its own file rather than a heredoc inside backup_db.sh: quoting a Python
block inside a shell function is exactly the kind of thing that works until
someone edits it, and a broken alerter is worse than none — it fails silently at
the moment it is needed.

Always writes to stderr. Additionally sends to Sentry when SENTRY_DSN is set, so
a failed backup lands where the rest of the operational noise already goes rather
than in a log nobody reads.

Exits 0 even when it cannot report. Its caller has already failed; making the
failure path itself fail would only lose the original message.
"""
import os
import sys


def main() -> int:
    message = " ".join(sys.argv[1:]) or "unknown failure"
    print(f"BACKUP FAILED: {message}", file=sys.stderr)

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return 0
    try:
        import sentry_sdk
    except ImportError:
        print(
            "SENTRY_DSN is set but sentry_sdk is not installed here; "
            "the failure was logged only.",
            file=sys.stderr,
        )
        return 0
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )
        sentry_sdk.capture_message(
            f"Database backup failed: {message}", level="error"
        )
        sentry_sdk.flush(timeout=5)
    except Exception as exc:  # noqa: BLE001 — never mask the original failure
        print(f"could not report to Sentry: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
