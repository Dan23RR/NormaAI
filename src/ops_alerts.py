"""Tell the operator that a scheduled job failed: a Sentry event and an email.

Who calls it:

- ``python -m src.pipeline --action check-freshness | recheck-documents``, the
  cron jobs that run inside the app container, when they raise;
- ``scripts/backup.sh`` and ``scripts/restore_test.sh``, which run on the host,
  through the app container (it holds the Resend key and the Sentry DSN):

      docker exec -i normaai-app python -m src.ops_alerts <job> "<summary>" < details

What goes out: the job, the host, the time and the one-line summary; the email
also carries the details (the last lines of the script's own messages, which
name steps and files, never a secret value). With SENTRY_DSN set, one Sentry
event at level error, grouped by job. With OPS_ALERT_EMAIL and RESEND_API_KEY
set, one email to OPS_ALERT_EMAIL. With neither, nobody is told: this module
says so on stderr and exits with 2, and the failure stays in the job's log.
"""

from __future__ import annotations

import argparse
import socket
import sys
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()

# Details beyond this are cut: an email is not the log.
MAX_DETAIL_CHARS = 6000
MAX_SUMMARY_CHARS = 300


def failure_summary(error: BaseException) -> str:
    """``Type: first line of the message``, short: the details stay in the log."""
    first = str(error).strip().splitlines()[0] if str(error).strip() else ""
    text = f"{type(error).__name__}: {first}" if first else type(error).__name__
    return text[:MAX_SUMMARY_CHARS]


def _send_to_sentry(settings: Any, job: str, text: str, host: str) -> bool:
    if not str(getattr(settings, "sentry_dsn", None) or "").strip():
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    from src.observability import setup_sentry

    try:
        if not sentry_sdk.get_client().is_active() and not setup_sentry(settings):
            return False
        sentry_sdk.capture_message(
            text,
            level="error",
            tags={"job": job, "host": host},
            fingerprint=["ops-alert", job],
        )
        sentry_sdk.flush(timeout=10)
        return True
    except Exception as e:  # noqa: BLE001 - an alert must never raise
        logger.warning("ops_alert_sentry_failed", job=job, error=type(e).__name__)
        return False


def notify_failure(
    job: str,
    summary: str,
    details: str = "",
    *,
    sentry: bool = True,
    settings: Any = None,
    now: datetime | None = None,
) -> dict[str, bool]:
    """Report a failed job. Returns which channels took it: ``{"sentry", "email"}``.

    ``sentry=False`` when the caller already sent the error to Sentry itself
    (the pipeline logs the traceback at ERROR, which the SDK captures).
    Never raises.
    """
    if settings is None:
        from src.config import get_settings

        settings = get_settings()
    host = socket.gethostname()
    when = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    summary = " ".join(str(summary).split())[:MAX_SUMMARY_CHARS] or "failed"
    details = str(details or "")[-MAX_DETAIL_CHARS:]
    text = f"{job} failed on {host}: {summary}"

    delivered = {"sentry": False, "email": False}
    if sentry:
        delivered["sentry"] = _send_to_sentry(settings, job, text, host)

    address = str(getattr(settings, "ops_alert_email", "") or "").strip()
    if address:
        try:
            from src.email_client import send_ops_alert_email

            ok, _error = send_ops_alert_email(
                to_email=address, job=job, host=host, when=when, summary=summary, details=details
            )
            delivered["email"] = bool(ok)
        except Exception as e:  # noqa: BLE001
            logger.warning("ops_alert_email_failed", job=job, error=type(e).__name__)

    logger.warning("ops_alert", job=job, summary=summary, **delivered)
    return delivered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.ops_alerts",
        description="Tell the operator that a job failed (Sentry and/or email). "
        "Details are read from standard input.",
    )
    parser.add_argument("job", help="the job that failed, e.g. backup")
    parser.add_argument("summary", help="one line: what failed")
    args = parser.parse_args(argv)
    details = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    delivered = notify_failure(args.job, args.summary, details)
    if any(delivered.values()):
        return 0
    print(
        "ops_alerts: nobody was told: set SENTRY_DSN and/or OPS_ALERT_EMAIL with "
        "RESEND_API_KEY in .env (docs/RUNBOOK.md, section 1)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
