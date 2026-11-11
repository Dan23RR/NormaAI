"""Tests for the scheduled surveillance (src/document_check/surveillance.py).

``python -m src.pipeline --action recheck-documents`` re-checks the provisions
of every watched document, organisation by organisation, writes one alert per
document whose provisions changed and sends each user one digest email.

Offline: the official texts are tests/documents_support.FakeSource, the tables
are the real ones on SQLite (documents_support.Database) and Resend is mocked
at ``resend.Emails.send``, so the email that would leave is the one inspected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src import email_client
from src.config import get_settings
from src.db.models import Alert, DocumentCheck, DocumentDependency
from src.document_check import service, surveillance
from tests.documents_support import (
    AI_ACT,
    ART13_AMENDED,
    ART50,
    CLEAN_DOCUMENT,
    GDPR,
    NEW_ART4,
    Database,
    FakeSource,
    article,
)

CHECKED = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
MONDAY = datetime(2026, 11, 9, 4, 0, tzinfo=UTC)
NEXT_MONDAY = MONDAY + timedelta(days=7)
API = "https://api.example.test"
APP = "https://app.example.test"
ONLY_GDPR = "Si applica l'art. 13 del GDPR.\n"


@pytest.fixture
def db():
    return Database()


@pytest.fixture
def source():
    return FakeSource()


@pytest.fixture(autouse=True)
def _settings():
    settings = get_settings().model_copy(
        update={"api_public_url": API, "normaai_public_url": APP, "api_domain": ""}
    )
    with (
        patch("src.document_check.service.get_settings", return_value=settings),
        patch("src.document_check.surveillance.get_settings", return_value=settings),
    ):
        yield settings


@pytest.fixture
def outbox(monkeypatch):
    """Resend configured, with ``resend.Emails.send`` recording instead of sending."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_REPLY_TO", "info@normaai.org")
    sent: list[dict] = []

    def send(payload):
        sent.append(payload)
        return {"id": f"msg_{len(sent)}"}

    with patch("resend.Emails.send", side_effect=send):
        yield sent


async def _store(db, source, org_id, text=CLEAN_DOCUMENT, **fields):
    outcome = service.check_document(
        source, filename=fields.pop("filename", "nota.txt"), text=text, now=CHECKED
    )
    async with db.session(org_id=str(org_id)) as session:
        row, _ = await service.store_check(
            session,
            outcome,
            org_id=org_id,
            user_id=None,
            client_id=fields.pop("client_id", None),
            watch=fields.pop("watch", True),
        )
        await session.commit()
        return row.id


def _amend_gdpr(source, as_of="2027-01-01", text=ART13_AMENDED):
    source.publish(GDPR, as_of, [article("Art. 13", text)])


def _check(db, check_id):
    (row,) = db.rows(DocumentCheck, id=check_id)
    return row


# ─── The change, the alert, the email ────────────────────────────────


async def test_a_changed_provision_marks_the_check_writes_one_alert_and_sends_one_email(
    db, source, outbox
):
    org = db.add_org("Studio Rossi")
    user = db.add_user(org, "anna@example.test", name="Anna")
    check_id = await _store(db, source, org, filename="informativa.docx")
    _amend_gdpr(source)

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.organisations == 1 and report.checks == 1
    assert report.provisions == 2 and report.unanswered == 0
    assert (report.checks_changed, report.alerts) == (1, 1)
    assert (report.emails_sent, report.emails_failed, report.emails_skipped) == (1, 0, None)
    assert report.failed_organisations == []

    row = _check(db, check_id)
    assert row.needs_review is True and row.status == "correggere"
    assert row.counts == {"correggere": 1, "controllare": 0, "a_posto": 1, "non_coperto": 0}
    assert row.rechecked_at is not None and row.review_notified_at is not None
    states = {d.act: (d.state, d.changed_at is not None) for d in db.rows(DocumentDependency)}
    assert states == {GDPR: ("changed", True), AI_ACT: ("current", False)}

    (alert,) = db.rows(Alert)
    assert alert.document_check_id == check_id and alert.client_id is None
    assert alert.title == "Documento da rivedere: informativa.docx"
    assert "GDPR, Art. 13 (testo consolidato al 01/01/2027)" in alert.description
    assert alert.severity == "HIGH" and alert.is_read is False

    (email,) = outbox
    assert email["to"] == ["anna@example.test"]
    assert email["subject"] == "NormaAI: 1 documento da rivedere"
    unsubscribe = email["headers"]["List-Unsubscribe"]
    assert unsubscribe.startswith(f"<{API}/api/v1/documents/unsubscribe?token=")
    assert email["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    link = unsubscribe.strip("<>")
    assert service.read_unsubscribe_token(link.split("token=")[1]) == user
    for body in (email["html"], email["text"]):
        assert "Ciao Anna," in body
        assert "informativa.docx" in body
        assert "GDPR, Art. 13 (testo consolidato al 01/01/2027)" in body
        assert f"{APP}/app/controlla/{check_id}" in body
        assert "token=" in body  # the unsubscribe link is in the message too
    assert link in email["text"]
    assert email["tags"] == [{"name": "campaign", "value": "document_digest"}]


async def test_running_it_twice_tells_nobody_twice(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org)
    _amend_gdpr(source)
    await surveillance.run(db.session, source, now=MONDAY)
    first = _check(db, check_id)
    (alert,) = db.rows(Alert)
    (changed,) = db.rows(DocumentDependency, state="changed")

    report = await surveillance.run(db.session, source, now=NEXT_MONDAY)

    assert (report.checks_changed, report.alerts, report.emails_sent) == (0, 0, 0)
    assert len(outbox) == 1
    assert [a.id for a in db.rows(Alert)] == [alert.id]
    again = _check(db, check_id)
    assert again.needs_review is True
    assert again.review_notified_at == first.review_notified_at
    assert again.rechecked_at != first.rechecked_at
    (still,) = db.rows(DocumentDependency, state="changed")
    assert still.changed_at == changed.changed_at


async def test_a_later_wording_is_announced_again_on_the_same_alert(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)
    await surveillance.run(db.session, source, now=MONDAY)
    (alert,) = db.rows(Alert)
    with db.sync_session() as session:
        session.get(Alert, alert.id).is_read = True
        session.commit()

    _amend_gdpr(source, "2027-06-01", ART13_AMENDED + " E altro ancora.")
    report = await surveillance.run(db.session, source, now=NEXT_MONDAY)

    assert (report.checks_changed, report.emails_sent) == (1, 1)
    assert len(outbox) == 2
    (same,) = db.rows(Alert)
    assert same.id == alert.id and same.is_read is False
    assert "testo consolidato al 01/06/2027" in same.description
    assert _check(db, check_id).needs_review is True


async def test_nothing_changed(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org)

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert (report.checks, report.provisions, report.checks_changed) == (1, 2, 0)
    assert outbox == [] and db.rows(Alert) == []
    row = _check(db, check_id)
    assert row.needs_review is False and row.status == "a_posto"
    assert row.rechecked_at is not None and row.review_notified_at is None
    assert {d.state for d in db.rows(DocumentDependency)} == {"current"}
    assert all(d.checked_at is not None for d in db.rows(DocumentDependency))


async def test_an_empty_database(db, source, outbox):
    report = await surveillance.run(db.session, source, now=MONDAY)
    assert report.as_dict() == {
        "organisations": 0,
        "checks": 0,
        "provisions": 0,
        "unanswered": 0,
        "checks_changed": 0,
        "alerts": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "emails_skipped": None,
        "failed_organisations": [],
    }
    assert source.asked_versions == []


# ─── Organisations ───────────────────────────────────────────────────


async def test_each_distinct_provision_is_read_once_for_all_organisations(db, source, outbox):
    alfa, beta = db.add_org("Alfa"), db.add_org("Beta")
    db.add_user(alfa, "anna@alfa.test", name="Anna")
    db.add_user(beta, "bruno@beta.test", name="Bruno")
    of_alfa = [
        await _store(db, source, alfa, ONLY_GDPR, filename="alfa-1.txt"),
        await _store(db, source, alfa, ONLY_GDPR, filename="alfa-2.txt"),
    ]
    of_beta = await _store(db, source, beta, ONLY_GDPR, filename="beta-1.txt")
    _amend_gdpr(source)
    source.asked_versions.clear()
    source.asked_articles.clear()

    report = await surveillance.run(db.session, source, now=MONDAY)

    # Three documents, two organisations, one provision: asked once.
    assert report.provisions == 1 and report.checks == 3
    assert source.asked_versions == [GDPR]
    assert source.asked_articles == ["02016R0679-20270101"]
    assert (report.checks_changed, report.alerts, report.emails_sent) == (3, 3, 2)

    assert {a.document_check_id for a in db.rows(Alert)} == {*of_alfa, of_beta}
    by_recipient = {email["to"][0]: email for email in outbox}
    assert set(by_recipient) == {"anna@alfa.test", "bruno@beta.test"}
    alfa_mail, beta_mail = by_recipient["anna@alfa.test"], by_recipient["bruno@beta.test"]
    assert alfa_mail["subject"] == "NormaAI: 2 documenti da rivedere"
    assert beta_mail["subject"] == "NormaAI: 1 documento da rivedere"
    # Nobody reads the name of another organisation's document.
    assert "alfa-1.txt" in alfa_mail["html"] and "alfa-2.txt" in alfa_mail["html"]
    assert "beta-1.txt" not in alfa_mail["html"] + alfa_mail["text"]
    assert "alfa-" not in beta_mail["html"] + beta_mail["text"]
    assert f"/app/controlla/{of_beta}" in beta_mail["text"]


async def test_it_works_organisation_by_organisation(db, source, outbox):
    alfa, beta = db.add_org("Alfa"), db.add_org("Beta")
    await _store(db, source, alfa)
    await _store(db, source, beta)
    db.session_orgs.clear()

    await surveillance.run(db.session, source, now=MONDAY)

    # First the list of organisations, on a session of no tenant; every other
    # session is opened for one organisation, as a request's would be.
    assert db.session_orgs[0] is None
    assert db.session_orgs.count(None) == 1
    assert set(db.session_orgs[1:]) == {str(alfa), str(beta)}


async def test_a_failure_in_one_organisation_does_not_stop_the_others(db, source, outbox):
    alfa, beta = db.add_org("Alfa"), db.add_org("Beta")
    db.add_user(beta, "bruno@beta.test")
    broken = await _store(db, source, alfa, ONLY_GDPR)
    fine = await _store(db, source, beta, ONLY_GDPR)
    _amend_gdpr(source)
    real = service.apply_recheck

    async def apply(session, row, *args, **kwargs):
        if row.id == broken:
            raise RuntimeError("boom")
        return await real(session, row, *args, **kwargs)

    with patch.object(service, "apply_recheck", side_effect=apply):
        report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.failed_organisations == [str(alfa)]
    assert _check(db, broken).needs_review is False
    assert _check(db, fine).needs_review is True
    assert [email["to"] for email in outbox] == [["bruno@beta.test"]]


# ─── Which documents ─────────────────────────────────────────────────


async def test_only_watched_documents_are_rechecked(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    watched = await _store(db, source, org, ONLY_GDPR, filename="seguito.txt")
    unwatched = await _store(db, source, org, ONLY_GDPR, filename="non-seguito.txt", watch=False)
    _amend_gdpr(source)

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.checks == 1
    assert _check(db, watched).needs_review is True
    row = _check(db, unwatched)
    assert row.needs_review is False and row.rechecked_at is None
    (email,) = outbox
    assert "non-seguito.txt" not in email["text"]


async def test_a_change_found_from_the_api_is_in_the_next_digest(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org, ONLY_GDPR, watch=False, filename="a-mano.txt")
    _amend_gdpr(source)
    # What POST /checks/{id}/recheck does.
    async with db.session(org_id=str(org)) as session:
        row, dependencies = await service.load_check(session, org, check_id)
        stored = [service.dependency_json(d) for d in dependencies]
        answers = service.recheck_provisions(stored, source)
        await service.apply_recheck(
            session, row, dependencies, [answers.get(service.provision_key(d)) for d in stored]
        )
        await session.commit()
    assert len(db.rows(Alert)) == 1 and outbox == []

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert (report.checks, report.alerts, report.emails_sent) == (0, 0, 1)
    assert "a-mano.txt" in outbox[0]["text"]
    assert len(db.rows(Alert)) == 1
    assert (await surveillance.run(db.session, source, now=NEXT_MONDAY)).emails_sent == 0


async def test_unreachable_texts_raise_no_alarm_and_are_asked_again(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org)
    source.unreachable = {GDPR}

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.unanswered == 1 and report.checks_changed == 0
    assert outbox == [] and db.rows(Alert) == []
    states = {d.act: d.state for d in db.rows(DocumentDependency)}
    assert states == {GDPR: "unavailable", AI_ACT: "current"}
    assert _check(db, check_id).needs_review is False

    source.unreachable = set()
    _amend_gdpr(source)
    report = await surveillance.run(db.session, source, now=NEXT_MONDAY)
    assert report.checks_changed == 1 and len(outbox) == 1


async def test_a_change_already_found_is_kept_when_the_text_is_unreachable(db, source, outbox):
    org = db.add_org()
    check_id = await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)
    await surveillance.run(db.session, source, now=MONDAY)
    source.unreachable = {GDPR}

    report = await surveillance.run(db.session, source, now=NEXT_MONDAY)

    assert report.checks_changed == 0
    (dependency,) = db.rows(DocumentDependency)
    assert dependency.state == "changed"
    assert _check(db, check_id).needs_review is True
    assert len(db.rows(Alert)) == 1


async def test_the_alert_of_a_clients_document(db, source, outbox):
    org = db.add_org()
    acme = db.add_client(org, "Acme Srl")
    check_id = await _store(db, source, org, ONLY_GDPR, client_id=acme)
    _amend_gdpr(source)
    await surveillance.run(db.session, source, now=MONDAY)
    (alert,) = db.rows(Alert)
    assert alert.client_id == acme and alert.document_check_id == check_id
    assert alert.framework == "GDPR"


async def test_two_provisions_of_one_document_one_alert(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    await _store(db, source, org)
    _amend_gdpr(source)
    source.publish(
        AI_ACT,
        "2027-02-01",
        [article("Art. 4", NEW_ART4), article("Art. 50", ART50 + "\n8. Nuovo paragrafo.")],
    )

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert (report.checks_changed, report.alerts, report.emails_sent) == (1, 1, 1)
    (alert,) = db.rows(Alert)
    assert alert.description.startswith(
        "Dopo il controllo sono cambiate 2 disposizioni citate nel documento: "
    )
    assert "GDPR, Art. 13" in alert.description and "AI Act, Art. 50" in alert.description
    assert "AI Act, Art. 50 (testo consolidato al 01/02/2027)" in outbox[0]["text"]


# ─── Who gets the email ──────────────────────────────────────────────


async def test_one_email_per_user_who_has_not_turned_it_off(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test", name="Anna")
    db.add_user(org, "bruno@example.test", name="Bruno", role="viewer")
    db.add_user(org, "carla@example.test", notify=False)
    db.add_user(org, "dario@example.test", active=False)
    await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.emails_sent == 2
    assert sorted(email["to"][0] for email in outbox) == ["anna@example.test", "bruno@example.test"]
    # Each link turns the email off for its own reader.
    tokens = {email["to"][0]: email["headers"]["List-Unsubscribe"] for email in outbox}
    assert tokens["anna@example.test"] != tokens["bruno@example.test"]
    assert len(db.rows(Alert)) == 1


async def test_only_confirmed_addresses_when_the_deployment_asks_for_confirmation(
    db, source, outbox, _settings
):
    org = db.add_org()
    db.add_user(org, "anna@example.test", verified=True)
    db.add_user(org, "bruno@example.test", verified=False)
    await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)
    strict = _settings.model_copy(update={"require_email_verification": True})
    with patch("src.document_check.surveillance.get_settings", return_value=strict):
        await surveillance.run(db.session, source, now=MONDAY)
    assert [email["to"] for email in outbox] == [["anna@example.test"]]


async def test_nobody_to_tell(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "carla@example.test", notify=False)
    check_id = await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.emails_sent == 0 and outbox == []
    assert len(db.rows(Alert)) == 1  # the alert is there for whoever opens the app
    assert _check(db, check_id).review_notified_at is not None


async def test_an_email_that_fails_is_tried_again_and_the_alert_stays_one(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)

    with patch("resend.Emails.send", side_effect=RuntimeError("resend is down")):
        report = await surveillance.run(db.session, source, now=MONDAY)
    assert (report.emails_sent, report.emails_failed, report.alerts) == (0, 1, 1)
    assert _check(db, check_id).review_notified_at is None

    report = await surveillance.run(db.session, source, now=NEXT_MONDAY)
    assert (report.emails_sent, report.emails_failed, report.alerts) == (1, 0, 0)
    assert len(outbox) == 1 and len(db.rows(Alert)) == 1
    assert (await surveillance.run(db.session, source, now=NEXT_MONDAY)).emails_sent == 0


async def test_without_resend_the_alerts_are_written_and_the_emails_wait(
    db, source, monkeypatch, _settings
):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    check_id = await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)

    report = await surveillance.run(db.session, source, now=MONDAY)

    assert report.emails_skipped == "RESEND_API_KEY is not set"
    assert report.alerts == 1 and report.emails_sent == 0
    assert _check(db, check_id).review_notified_at is None

    # The key arrives: the change found a week ago is announced, once.
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    sent = []
    with patch("resend.Emails.send", side_effect=lambda p: sent.append(p) or {"id": "m"}):
        report = await surveillance.run(db.session, source, now=NEXT_MONDAY)
    assert report.emails_skipped is None and report.emails_sent == 1 and len(sent) == 1


async def test_without_the_public_address_of_the_api_no_email_leaves(db, source, outbox, _settings):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    await _store(db, source, org, ONLY_GDPR)
    _amend_gdpr(source)
    blind = _settings.model_copy(update={"api_public_url": "", "api_domain": ""})
    with (
        patch("src.document_check.service.get_settings", return_value=blind),
        patch("src.document_check.surveillance.get_settings", return_value=blind),
    ):
        report = await surveillance.run(db.session, source, now=MONDAY)
    assert "no unsubscribe link" in report.emails_skipped
    assert outbox == [] and report.alerts == 1


async def test_many_documents_are_listed_up_to_a_limit(db, source, outbox):
    org = db.add_org()
    db.add_user(org, "anna@example.test")
    for number in range(surveillance.DIGEST_MAX_DOCUMENTS + 2):
        await _store(db, source, org, ONLY_GDPR, filename=f"documento-{number:02d}.txt")
    _amend_gdpr(source)
    await surveillance.run(db.session, source, now=MONDAY)
    (email,) = outbox
    assert email["subject"] == "NormaAI: 22 documenti da rivedere"
    assert email["text"].count("- documento-") == surveillance.DIGEST_MAX_DOCUMENTS
    assert "E altri 2 documenti." in email["text"]
    assert "E altri 2 documenti." in email["html"]


# ─── The email itself ────────────────────────────────────────────────


class TestDigestEmail:
    def _send(self, **over):
        sent = []
        fields = {
            "to_email": "anna@example.test",
            "recipient_name": "Anna",
            "documents": [
                {
                    "filename": "nota <b>cliente</b> & co.docx",
                    "url": f"{APP}/app/controlla/123",
                    "provisions": ["GDPR, Art. 13 (testo consolidato al 01/01/2027)"],
                }
            ],
            "app_url": f"{APP}/app/controlla",
            "unsubscribe_url": f"{API}/api/v1/documents/unsubscribe?token=abc.1.def",
            **over,
        }
        with (
            patch.dict("os.environ", {"RESEND_API_KEY": "re_test_key"}),
            patch("resend.Emails.send", side_effect=lambda p: sent.append(p) or {"id": "m"}),
        ):
            result = email_client.send_document_digest_email(**fields)
        return result, sent

    def test_what_leaves(self):
        (ok, error), (email,) = self._send()
        assert ok is True and error is None
        assert email["subject"] == "NormaAI: 1 documento da rivedere"
        assert email["headers"] == {
            "List-Unsubscribe": f"<{API}/api/v1/documents/unsubscribe?token=abc.1.def>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        assert "in questo documento" in email["text"]
        assert "Apri i controlli" in email["html"]
        assert "Non ricevere più questa email" in email["html"]
        assert "Per non riceverla più: " in email["text"]
        assert "Non è un parere legale." in email["text"]

    def test_the_file_name_cannot_inject_markup(self):
        _, (email,) = self._send()
        assert "<b>cliente</b>" not in email["html"]
        assert "nota &lt;b&gt;cliente&lt;/b&gt; &amp; co.docx" in email["html"]
        assert "nota <b>cliente</b> & co.docx" in email["text"]

    def test_typography_of_the_house(self):
        _, (email,) = self._send(recipient_name="")
        for body in (email["html"], email["text"], email["subject"]):
            for forbidden in "—–…“”‘’":
                assert forbidden not in body
        assert email["text"].startswith("Ciao, dopo il controllo")
        # The palette of frontend/DESIGN.md: ink and union blue, no dark theme.
        assert "#0C1B33" in email["html"] and "#0A3A9C" in email["html"]

    def test_plural(self):
        documents = [
            {"filename": f"doc{i}.txt", "url": f"{APP}/app/controlla/{i}", "provisions": []}
            for i in range(3)
        ]
        _, (email,) = self._send(documents=documents[:2], total=3)
        assert email["subject"] == "NormaAI: 3 documenti da rivedere"
        assert "in questi documenti" in email["text"]
        assert "E un altro documento." in email["text"]

    def test_without_a_key_nothing_is_sent(self):
        with patch.dict("os.environ", {"RESEND_API_KEY": ""}), patch("resend.Emails.send") as send:
            result = email_client.send_document_digest_email(
                to_email="anna@example.test",
                recipient_name="Anna",
                documents=[],
                app_url=APP,
                unsubscribe_url=API,
            )
        assert result == (False, "resend_not_configured")
        send.assert_not_called()


def test_check_url_points_to_the_app():
    check_id = uuid.uuid4()
    assert surveillance.check_url(check_id) == f"{APP}/app/controlla/{check_id}"
