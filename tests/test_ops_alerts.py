"""src/ops_alerts.py: a failed cron job, backup or restore test reaches the operator.

Sentry and Resend are replaced by stand-ins: the tests check what is sent,
to whom, and that an alert never raises and never carries more than it should.
"""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src import email_client, ops_alerts

WHEN = datetime(2026, 11, 18, 2, 5, tzinfo=UTC)


def _settings(**values) -> SimpleNamespace:
    base = {"sentry_dsn": None, "ops_alert_email": "", "app_env": "production"}
    base.update(values)
    return SimpleNamespace(**base)


def test_summary_is_the_type_and_the_first_line():
    error = RuntimeError("connection refused\n[SQL: SELECT secret FROM t]")
    assert ops_alerts.failure_summary(error) == "RuntimeError: connection refused"
    assert ops_alerts.failure_summary(ValueError()) == "ValueError"
    assert len(ops_alerts.failure_summary(RuntimeError("x" * 1000))) == 300


def test_email_goes_to_the_operator_with_the_details():
    sent = MagicMock(return_value=(True, None))
    with patch.object(email_client, "send_ops_alert_email", sent):
        delivered = ops_alerts.notify_failure(
            "backup",
            "restic backup failed",
            "[backup] WARNING: one\n[backup] FAIL: two",
            settings=_settings(ops_alert_email="ops@example.org"),
            now=WHEN,
        )
    assert delivered == {"sentry": False, "email": True}
    kwargs = sent.call_args.kwargs
    assert kwargs["to_email"] == "ops@example.org"
    assert kwargs["job"] == "backup"
    assert kwargs["summary"] == "restic backup failed"
    assert kwargs["when"] == "2026-11-18 02:05 UTC"
    assert kwargs["details"].endswith("[backup] FAIL: two")


def test_details_are_cut_to_their_end():
    sent = MagicMock(return_value=(True, None))
    with patch.object(email_client, "send_ops_alert_email", sent):
        ops_alerts.notify_failure(
            "backup",
            "x",
            "a" * 10_000 + "THE END",
            settings=_settings(ops_alert_email="ops@example.org"),
        )
    details = sent.call_args.kwargs["details"]
    assert len(details) == ops_alerts.MAX_DETAIL_CHARS
    assert details.endswith("THE END")


def test_sentry_gets_one_event_grouped_by_job():
    sdk = MagicMock()
    sdk.get_client.return_value.is_active.return_value = True
    with patch.dict(sys.modules, {"sentry_sdk": sdk}):
        delivered = ops_alerts.notify_failure(
            "restore-test",
            "the dump does not load",
            settings=_settings(sentry_dsn="https://k@o1.ingest.sentry.io/1"),
        )
    assert delivered == {"sentry": True, "email": False}
    sdk.capture_message.assert_called_once()
    text = sdk.capture_message.call_args.args[0]
    assert text.startswith("restore-test failed on ")
    assert text.endswith(": the dump does not load")
    kwargs = sdk.capture_message.call_args.kwargs
    assert kwargs["level"] == "error"
    assert kwargs["fingerprint"] == ["ops-alert", "restore-test"]
    sdk.flush.assert_called_once()


def test_sentry_can_be_left_to_the_caller():
    sdk = MagicMock()
    with patch.dict(sys.modules, {"sentry_sdk": sdk}):
        ops_alerts.notify_failure(
            "pipeline check-freshness",
            "boom",
            sentry=False,
            settings=_settings(sentry_dsn="https://k@o1.ingest.sentry.io/1"),
        )
    sdk.capture_message.assert_not_called()


def test_a_broken_channel_never_raises():
    sdk = MagicMock()
    sdk.get_client.side_effect = RuntimeError("sdk broken")
    with (
        patch.dict(sys.modules, {"sentry_sdk": sdk}),
        patch.object(email_client, "send_ops_alert_email", side_effect=OSError("no network")),
    ):
        delivered = ops_alerts.notify_failure(
            "backup",
            "x",
            settings=_settings(
                sentry_dsn="https://k@o1.ingest.sentry.io/1", ops_alert_email="ops@example.org"
            ),
        )
    assert delivered == {"sentry": False, "email": False}


def test_the_email_escapes_what_the_job_printed():
    sent = MagicMock(return_value=(True, None))
    with patch.object(email_client, "_send_via_resend", sent):
        email_client.send_ops_alert_email(
            to_email="ops@example.org",
            job="backup",
            host="normaai",
            when="2026-11-18 02:05 UTC",
            summary="<b>pg_dump</b> failed",
            details="<script>alert(1)</script>",
        )
    kwargs = sent.call_args.kwargs
    assert kwargs["subject"] == "NormaAI: backup non riuscito su normaai"
    assert "<script>" not in kwargs["html"]
    assert "&lt;script&gt;" in kwargs["html"]
    assert "<script>alert(1)</script>" in kwargs["text"]


class TestCommandLine:
    def _main(self, argv, stdin="", delivered=None):
        notify = MagicMock(return_value=delivered or {"sentry": False, "email": True})
        with (
            patch.object(ops_alerts, "notify_failure", notify),
            patch.object(sys, "stdin", io.StringIO(stdin)),
        ):
            code = ops_alerts.main(argv)
        return code, notify

    def test_reads_the_details_from_standard_input(self):
        code, notify = self._main(["backup", "restic failed"], stdin="line 1\nline 2\n")
        assert code == 0
        notify.assert_called_once_with("backup", "restic failed", "line 1\nline 2\n")

    def test_says_when_nobody_was_told(self, capsys):
        code, _ = self._main(["backup", "x"], delivered={"sentry": False, "email": False})
        assert code == 2
        assert "nobody was told" in capsys.readouterr().err

    def test_needs_a_job_and_a_summary(self):
        with pytest.raises(SystemExit):
            ops_alerts.main(["backup"])
