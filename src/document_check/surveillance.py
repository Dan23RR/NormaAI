"""Scheduled surveillance of the watched documents.

``python -m src.pipeline --action recheck-documents`` (a weekly cron job on the
server, not the in-process scheduler) calls ``run``:

1. For every organisation, in a session opened for that organisation, it lists
   the provisions of the watched checks. The tenant tables are under row-level
   security: a session without an organisation sees none of them, which is why
   the job goes organisation by organisation exactly as a request would
   (``db_manager.session(org_id=...)``).
2. It asks the official texts once for each distinct provision, for all the
   organisations together. What is asked is an act, an article and the wording
   it had: nothing of any document.
3. For every organisation again, in one transaction each: the new state of
   every provision, ``needs_review`` on the checks whose provisions changed,
   and the one alert of each such document (``service.apply_recheck``, the same
   code the API re-check uses).
4. For every organisation that has checks to review nobody was emailed about:
   one digest email to each user who has not turned it off, then the checks
   are marked as announced.

Running it twice in a row writes no second alert and sends no second email: a
change is new only the first time its wording is seen (``serialize.next_state``)
and a check is announced once per change (``review_notified_at``). An email
that could not be sent is tried again at the next run.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from src.config import get_settings
from src.db.models import DocumentCheck as CheckRow
from src.db.models import DocumentDependency as DependencyRow
from src.db.models import Organization, User
from src.document_check import service

if TYPE_CHECKING:
    import uuid

    from src.document_check.check import Change
    from src.document_check.official import TextSource
    from src.document_check.service import ProvisionKey

logger = structlog.get_logger()

# Documents listed in one email; the rest is a count.
DIGEST_MAX_DOCUMENTS = 20
# The page of the app that shows a check.
CHECK_PATH = "/app/controlla"


@dataclass
class SurveillanceReport:
    """What a run did, for the job's log."""

    organisations: int = 0
    checks: int = 0
    provisions: int = 0  # distinct provisions asked of the official texts
    unanswered: int = 0  # of those, the ones that could not be read
    checks_changed: int = 0  # checks with a change seen for the first time
    alerts: int = 0
    emails_sent: int = 0
    emails_failed: int = 0
    emails_skipped: str | None = None  # why no email was attempted, if so
    failed_organisations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def failed(self, org_id: Any) -> None:
        if str(org_id) not in self.failed_organisations:
            self.failed_organisations.append(str(org_id))


# A session for an organisation (or for none): ``db_manager.session``.
SessionFactory = Any
# ``src.email_client.send_document_digest_email``.
DigestSender = Any


def check_url(check_id: Any) -> str:
    return f"{get_settings().normaai_public_url.rstrip('/')}{CHECK_PATH}/{check_id}"


async def _organisations(sessions: SessionFactory) -> list[uuid.UUID]:
    async with sessions() as session:
        result = await session.execute(select(Organization.id).order_by(Organization.created_at))
        return list(result.scalars().all())


async def _watched(
    session: Any, org_id: uuid.UUID
) -> tuple[list[CheckRow], dict[Any, list[DependencyRow]]]:
    result = await session.execute(
        select(CheckRow)
        .where(CheckRow.org_id == org_id, CheckRow.watch.is_(True))
        .order_by(CheckRow.checked_at)
    )
    checks = list(result.scalars().all())
    by_check: dict[Any, list[DependencyRow]] = {}
    for dependency in await service.load_dependencies(session, org_id, [c.id for c in checks]):
        by_check.setdefault(dependency.check_id, []).append(dependency)
    return checks, by_check


def _question(dependency: dict[str, Any]) -> dict[str, Any]:
    """A dependency without what comes from the document that cites it."""
    return {name: value for name, value in dependency.items() if name != "cited_as"}


async def _collect(
    sessions: SessionFactory, org_ids: list[uuid.UUID], report: SurveillanceReport
) -> dict[ProvisionKey, dict[str, Any]]:
    distinct: dict[ProvisionKey, dict[str, Any]] = {}
    for org_id in org_ids:
        async with sessions(org_id=str(org_id)) as session:
            checks, by_check = await _watched(session, org_id)
            report.checks += len(checks)
            for dependencies in by_check.values():
                for row in dependencies:
                    stored = service.dependency_json(row)
                    distinct.setdefault(service.provision_key(stored), _question(stored))
    return distinct


async def _apply(
    sessions: SessionFactory,
    org_id: uuid.UUID,
    answers: dict[ProvisionKey, Change],
    now: datetime,
    report: SurveillanceReport,
) -> None:
    async with sessions(org_id=str(org_id)) as session:
        checks, by_check = await _watched(session, org_id)
        for check in checks:
            dependencies = by_check.get(check.id, [])
            if not dependencies:
                continue
            changes = [
                answers.get(service.provision_key(service.dependency_json(dependency)))
                for dependency in dependencies
            ]
            fresh = await service.apply_recheck(session, check, dependencies, changes, now)
            if fresh:
                report.checks_changed += 1
                report.alerts += 1
        await session.commit()


async def _recipients(session: Any, org_id: uuid.UUID) -> list[User]:
    conditions = [
        User.org_id == org_id,
        User.is_active.is_(True),
        User.notify_document_changes.is_(True),
    ]
    if get_settings().require_email_verification:
        # The email names the organisation's documents: only to confirmed addresses.
        conditions.append(User.email_verified.is_(True))
    result = await session.execute(select(User).where(*conditions).order_by(User.created_at))
    return list(result.scalars().all())


async def _announce(
    sessions: SessionFactory,
    org_id: uuid.UUID,
    send: DigestSender,
    now: datetime,
    report: SurveillanceReport,
) -> None:
    """One digest email per user for the checks to review not announced yet."""
    async with sessions(org_id=str(org_id)) as session:
        result = await session.execute(
            select(CheckRow)
            .where(
                CheckRow.org_id == org_id,
                CheckRow.needs_review.is_(True),
                CheckRow.review_notified_at.is_(None),
            )
            .order_by(CheckRow.checked_at)
        )
        pending = list(result.scalars().all())
        if not pending:
            return
        by_check: dict[Any, list[DependencyRow]] = {}
        for row in await service.load_dependencies(session, org_id, [c.id for c in pending]):
            by_check.setdefault(row.check_id, []).append(row)
        documents = [
            {
                "filename": check.filename,
                "url": check_url(check.id),
                "provisions": service.changed_provisions(by_check.get(check.id, [])),
            }
            for check in pending
        ]
        recipients = await _recipients(session, org_id)
        sent = 0
        for user in recipients:
            link = service.unsubscribe_url(user.id)
            if link is None:
                continue
            ok, error = await asyncio.to_thread(
                send,
                to_email=user.email,
                recipient_name=user.name,
                documents=documents[:DIGEST_MAX_DOCUMENTS],
                total=len(documents),
                app_url=f"{get_settings().normaai_public_url.rstrip('/')}{CHECK_PATH}",
                unsubscribe_url=link,
            )
            if ok:
                sent += 1
            else:
                report.emails_failed += 1
                logger.warning("document_digest_not_sent", org_id=str(org_id), reason=error)
        report.emails_sent += sent
        if sent or not recipients:
            # Announced (or nobody wants the email). Left pending when every
            # send failed, so the next run tries again.
            for check in pending:
                check.review_notified_at = now
            await session.commit()


def _why_no_email() -> str | None:
    from src.email_client import email_configured

    if not email_configured():
        return "RESEND_API_KEY is not set"
    if not get_settings().api_base_url:
        return "API_PUBLIC_URL (or API_DOMAIN) is not set: no unsubscribe link can be built"
    return None


async def run(
    sessions: SessionFactory,
    source: TextSource,
    *,
    send_email: DigestSender | None = None,
    now: datetime | None = None,
) -> SurveillanceReport:
    """Re-check the watched documents of every organisation; alerts and digest emails.

    ``sessions`` is ``db_manager.session``; ``source`` the official texts
    (``sources.default_source()``); ``send_email`` defaults to the Resend client.
    """
    now = now or datetime.now(UTC)
    report = SurveillanceReport()
    org_ids = await _organisations(sessions)
    report.organisations = len(org_ids)

    distinct = await _collect(sessions, org_ids, report)
    report.provisions = len(distinct)
    answers: dict[ProvisionKey, Change] = {}
    if distinct:
        answers = await asyncio.to_thread(
            service.recheck_provisions, list(distinct.values()), source
        )
    report.unanswered = sum(
        1 for key in distinct if key not in answers or answers[key].code == "non_disponibile"
    )

    for org_id in org_ids:
        try:
            await _apply(sessions, org_id, answers, now, report)
        except Exception as e:  # noqa: BLE001 - one organisation must not stop the others
            report.failed(org_id)
            logger.error(
                "document_surveillance_failed", org_id=str(org_id), error_type=type(e).__name__
            )

    report.emails_skipped = _why_no_email() if send_email is None else None
    if report.emails_skipped is None:
        if send_email is None:
            from src.email_client import send_document_digest_email

            send_email = send_document_digest_email
        for org_id in org_ids:
            try:
                await _announce(sessions, org_id, send_email, now, report)
            except Exception as e:  # noqa: BLE001
                report.failed(org_id)
                logger.error(
                    "document_digest_failed", org_id=str(org_id), error_type=type(e).__name__
                )
    else:
        logger.warning("document_digest_skipped", reason=report.emails_skipped)

    logger.info("document_surveillance_done", **report.as_dict())
    return report
