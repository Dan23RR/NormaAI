"""Tests for src/document_check/service.py: the parts the router tests do not reach.

Reading a file from memory, the job runner (threads, time limit, one
organisation at a time), the shared text source and the re-check of distinct
provisions. Offline.
"""

from __future__ import annotations

import asyncio
import io
import threading
import time
import zipfile
from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from src.config import get_settings
from src.document_check import service
from src.document_check.service import DocumentCheckError
from tests.documents_support import CLEAN_DOCUMENT, GDPR, FakeSource


def _settings(**overrides):
    return get_settings().model_copy(update=overrides)


@pytest.fixture(autouse=True)
def _clean_state():
    service._RUNNING.clear()
    service._SOURCE = None
    yield
    deadline = time.time() + 5
    while service._RUNNING and time.time() < deadline:
        time.sleep(0.01)
    service._RUNNING.clear()
    service._SOURCE = None


# ─── The request ─────────────────────────────────────────────────────


class TestRequestFields:
    def test_clean_filename(self):
        assert service.clean_filename("nota.docx") == "nota.docx"
        assert service.clean_filename("C:\\Utenti\\Anna\\nota.docx") == "nota.docx"
        assert service.clean_filename("../../etc/passwd") == "passwd"
        assert service.clean_filename("no\x00ta\n.txt") == "nota.txt"
        assert service.clean_filename("") == "documento.txt"
        assert service.clean_filename(None) == "documento.txt"
        long_name = service.clean_filename("a" * 400 + ".docx")
        assert len(long_name) == 255 and long_name.endswith(".docx")

    def test_extension(self):
        assert service.extension_of("Nota.DOCX") == ".docx"
        assert service.extension_of("archivio.tar.gz") == ".gz"
        assert service.extension_of("senza") == "" and service.extension_of("punto.") == ""

    def test_document_date(self):
        assert service.parse_document_date("2026-03-15") == date(2026, 3, 15)
        assert service.parse_document_date(" 2026-03-15 ") == date(2026, 3, 15)
        assert service.parse_document_date(None) is None
        assert service.parse_document_date("") is None
        assert service.parse_document_date(date(2026, 3, 15)) == date(2026, 3, 15)
        for bad in ("15/03/2026", "2026-02-30", "20260315", "2026-3-15", 20260315):
            with pytest.raises(DocumentCheckError) as error:
                service.parse_document_date(bad)
            assert error.value.status_code == 422 and error.value.code == "invalid_date"

    def test_language(self):
        assert service.parse_language("it") == "IT" and service.parse_language(" EN ") == "EN"
        assert service.parse_language(None) is None and service.parse_language("") is None
        with pytest.raises(DocumentCheckError) as error:
            service.parse_language("de")
        assert error.value.code == "invalid_language"

    def test_every_error_has_a_status_a_code_and_an_italian_sentence(self):
        errors = [
            service.file_too_large(10 * 1024 * 1024),
            service.unsupported_type(".xls"),
            service.text_too_long(400_000),
            service.too_many_references(300),
            service.storage_full(1000),
            service.empty_file(),
            service.missing_document(),
            service.unreadable_file(),
            service.password_protected(),
            service.no_text(),
            service.pdf_not_supported(),
            service.invalid_date(),
            service.invalid_language(),
            service.client_not_found(),
            service.check_not_found(),
            service.busy(),
            service.timed_out(),
            service.source_unavailable(),
        ]
        assert len({e.code for e in errors}) == len(errors)
        for error in errors:
            assert 400 <= error.status_code < 600
            assert error.detail.endswith(".") and str(error) == error.detail
            for forbidden in "\u2014\u2013\u2026\u201c\u201d\u2018\u2019":
                assert forbidden not in error.detail
        assert service.busy().retry_after and service.timed_out().retry_after


# ─── Files, in memory ────────────────────────────────────────────────


class TestTextFromBytes:
    def test_plain_text_encodings(self):
        text = "Così è: l'art. 13 del GDPR.\r\nSeconda riga.\rTerza."
        expected = "Così è: l'art. 13 del GDPR.\nSeconda riga.\nTerza."
        assert service.text_from_bytes("n.txt", text.encode("utf-8")) == expected
        assert service.text_from_bytes("n.md", b"\xef\xbb\xbf" + text.encode("utf-8")) == expected
        assert service.text_from_bytes("n.txt", text.encode("utf-16")) == expected
        assert service.text_from_bytes("n.text", text.encode("cp1252")) == expected

    def test_characters_the_database_cannot_store_are_dropped(self):
        assert service.text_from_bytes("n.txt", b"art. 13\x00 del GDPR") == "art. 13 del GDPR"
        assert service._clean_text("a\ud800b") == "ab"

    def test_html_keeps_the_text_and_drops_scripts(self):
        html = b"<html><head><style>p{}</style></head><body><p>Vale l'art. 13.</p><script>x()</script></body></html>"
        text = service.text_from_bytes("pagina.htm", html)
        assert "Vale l'art. 13." in text and "x()" not in text and "p{}" not in text

    def test_docx_paragraphs_and_tables(self):
        docx = pytest.importorskip("docx")
        document = docx.Document()
        document.add_paragraph("Vale l'art. 13 del GDPR.")
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Norma"
        table.rows[0].cells[1].text = "art. 50 dell'AI Act"
        buffer = io.BytesIO()
        document.save(buffer)
        text = service.text_from_bytes("nota.docx", buffer.getvalue())
        assert text.split("\n") == ["Vale l'art. 13 del GDPR.", "Norma | art. 50 dell'AI Act"]

    def test_a_docx_that_unpacks_to_too_much_is_refused(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b"0" * 300_000)
        with (
            patch.object(service, "_DOCX_MAX_UNPACKED", 100_000),
            pytest.raises(DocumentCheckError) as error,
        ):
            service.text_from_bytes("bomba.docx", buffer.getvalue())
        assert error.value.code == "unreadable_file"

    def test_not_really_a_docx_or_a_pdf(self):
        for name in ("finto.docx", "finto.pdf"):
            with pytest.raises(DocumentCheckError) as error:
                service.text_from_bytes(name, b"testo qualunque")
            assert error.value.code == "unreadable_file"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("qualcosa.txt", "non un documento Word")
        with pytest.raises(DocumentCheckError) as error:
            service.text_from_bytes("zip.docx", archive.getvalue())
        assert error.value.code == "unreadable_file"

    def _pdf(self, lines, password=None):
        canvas_module = pytest.importorskip("reportlab.pdfgen.canvas")
        buffer = io.BytesIO()
        if password:
            from reportlab.lib.pdfencrypt import StandardEncryption

            page = canvas_module.Canvas(buffer, encrypt=StandardEncryption(password))
        else:
            page = canvas_module.Canvas(buffer)
        y = 800
        for line in lines:
            page.drawString(40, y, line)
            y -= 18
        page.save()
        return buffer.getvalue()

    def test_pdf_lines_are_joined_like_the_command_line_does(self):
        pytest.importorskip("pypdf")
        data = self._pdf(["Ai sensi dell'art. 13 del", "GDPR il titolare informa."])
        text = service.text_from_bytes("nota.pdf", data)
        assert "art. 13 del GDPR il titolare informa." in text

    def test_pdf_with_either_library(self):
        data = self._pdf(["Vale l'art. 13 del GDPR."])
        readers = []
        if service._pdf_pages_pypdf(data, 10_000) is not None:
            readers.append(service._pdf_pages_pypdf)
        if service._pdf_pages_pdfium(data, 10_000) is not None:
            readers.append(service._pdf_pages_pdfium)
        assert readers, "no PDF library in this environment"
        for read in readers:
            assert "art. 13 del GDPR" in "\n".join(read(data, 10_000))

    def test_pdf_reading_stops_once_the_text_is_too_long(self):
        pytest.importorskip("pypdf")
        canvas_module = pytest.importorskip("reportlab.pdfgen.canvas")
        buffer = io.BytesIO()
        page = canvas_module.Canvas(buffer)
        for _ in range(5):
            page.drawString(40, 800, "x" * 80)
            page.showPage()
        page.save()
        assert len(service._pdf_pages_pypdf(buffer.getvalue(), 100)) == 2

    def test_password_protected_pdf(self):
        pytest.importorskip("pypdf")
        data = self._pdf(["Vale l'art. 13 del GDPR."], password="segreto")
        with pytest.raises(DocumentCheckError) as error:
            service.text_from_bytes("protetto.pdf", data)
        assert error.value.code == "password_protected"
        assert error.value.detail.startswith("Il PDF è protetto da password")

    def test_a_pdf_without_text(self):
        pytest.importorskip("pypdf")
        with pytest.raises(DocumentCheckError) as error:
            service.check_document(FakeSource(), filename="scansione.pdf", data=self._pdf([]))
        assert error.value.code == "no_text"
        assert "PDF fatto di immagini" in error.value.detail

    def test_unsupported_and_empty(self):
        with pytest.raises(DocumentCheckError) as error:
            service.text_from_bytes("foglio.xlsx", b"x")
        assert error.value.status_code == 415
        with pytest.raises(DocumentCheckError) as error:
            service.text_from_bytes("vuoto.txt", b"")
        assert error.value.code == "empty_file"


class TestCheckDocument:
    def test_outcome(self):
        now = datetime(2026, 11, 3, 23, 30, tzinfo=UTC)
        outcome = service.check_document(
            FakeSource(), filename="nota.txt", text=CLEAN_DOCUMENT, now=now
        )
        assert outcome.status == "a_posto" and outcome.lang == "IT"
        assert outcome.checked_at == now
        assert outcome.counts == {"correggere": 0, "controllare": 0, "a_posto": 2, "non_coperto": 0}
        assert len(outcome.findings) == 2 and len(outcome.dependencies) == 2
        # Neither the document nor what it says ends up in a log through repr().
        assert repr(outcome) == "<check outcome: a_posto, 2 findings>"

    def test_language_given_or_detected(self):
        english = "Under Article 13 GDPR the controller shall provide the information."
        assert service.check_document(FakeSource(), filename="n.txt", text=english).lang == "EN"
        forced = service.check_document(FakeSource(), filename="n.txt", text=english, lang="IT")
        assert forced.lang == "IT"

    def test_neither_file_nor_text(self):
        with pytest.raises(DocumentCheckError) as error:
            service.check_document(FakeSource(), filename="n.txt")
        assert error.value.code == "missing_document"


# ─── Re-checking distinct provisions ─────────────────────────────────


class TestRecheckProvisions:
    def test_the_same_provision_is_asked_once(self):
        source = FakeSource()
        one = service.check_document(source, filename="a.txt", text=CLEAN_DOCUMENT).dependencies
        two = service.check_document(source, filename="b.txt", text=CLEAN_DOCUMENT).dependencies
        source.asked_versions.clear()
        answers = service.recheck_provisions(one + two, source)
        assert sorted(source.asked_versions) == sorted({d["act"] for d in one})
        assert len(answers) == 2
        for dependency in one + two:
            assert answers[service.provision_key(dependency)].code == "invariato"

    def test_nothing_of_the_document_is_in_what_is_asked(self):
        source = FakeSource()
        dependencies = service.check_document(
            source, filename="riservato.txt", text=CLEAN_DOCUMENT
        ).dependencies
        seen = []

        def spy(lock, _source):
            seen.append(lock)
            return []

        with patch.object(service, "recheck", side_effect=spy):
            assert service.recheck_provisions(dependencies, source) == {}
        (lock,) = seen
        assert lock["documento"] == "" and lock["data_documento"] is None
        assert all(entry["riferimenti"] == [] for entry in lock["dipendenze"])
        assert "riservato" not in repr(lock) and "art. 13 del GDPR" not in repr(lock)

    def test_same_article_checked_on_another_version_is_another_question(self):
        source = FakeSource()
        dependency = service.check_document(
            source, filename="a.txt", text="Vale l'art. 13 del GDPR."
        ).dependencies[0]
        older = {**dependency, "version": GDPR, "fingerprint": "sha256:other"}
        assert service.provision_key(dependency) != service.provision_key(older)
        assert len(service.recheck_provisions([dependency, older], source)) == 2


# ─── Threads, time limit, one organisation at a time ─────────────────


class TestRunJob:
    async def test_result_and_release(self):
        assert await service.run_job("org-a", lambda: 6 * 7) == 42
        assert service.running_jobs("org-a") == 0

    async def test_the_job_runs_off_the_event_loop(self):
        loop_thread = threading.get_ident()
        assert await service.run_job("org-a", threading.get_ident) != loop_thread

    async def test_an_exception_comes_back_and_the_place_is_freed(self):
        def job():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await service.run_job("org-a", job)
        assert service.running_jobs("org-a") == 0

    async def test_an_organisation_has_a_limited_number_of_jobs_running(self):
        release = threading.Event()
        limit = _settings(document_check_concurrency_per_org=2)
        with patch("src.document_check.service.get_settings", return_value=limit):
            first = asyncio.ensure_future(service.run_job("org-a", lambda: release.wait(5)))
            second = asyncio.ensure_future(service.run_job("org-a", lambda: release.wait(5)))
            await asyncio.sleep(0.05)
            assert service.running_jobs("org-a") == 2
            with pytest.raises(DocumentCheckError) as error:
                await service.run_job("org-a", lambda: 1)
            assert error.value.status_code == 429 and error.value.retry_after == 15
            # Another organisation is not held back.
            assert await service.run_job("org-b", lambda: "ok") == "ok"
            release.set()
            assert await first is True and await second is True
            assert service.running_jobs("org-a") == 0
            assert await service.run_job("org-a", lambda: "again") == "again"

    async def test_time_limit_and_the_place_kept_until_the_job_ends(self):
        release = threading.Event()
        quick = _settings(document_check_timeout_seconds=0.05)
        with (
            patch("src.document_check.service.get_settings", return_value=quick),
            pytest.raises(DocumentCheckError) as error,
        ):
            await service.run_job("org-a", lambda: release.wait(5))
        assert error.value.status_code == 504 and error.value.code == "timeout"
        assert service.running_jobs("org-a") == 1  # the thread is still working
        release.set()
        for _ in range(100):
            if service.running_jobs("org-a") == 0:
                break
            await asyncio.sleep(0.01)
        assert service.running_jobs("org-a") == 0


# ─── The shared text source ──────────────────────────────────────────


class TestSharedSource:
    def test_one_source_for_a_while_then_a_new_one(self):
        made = []

        def make():
            made.append(FakeSource())
            return made[-1]

        with patch("src.document_check.sources.default_source", side_effect=make):
            first = service.shared_source()
            assert service.shared_source() is first
            assert len(made) == 1
            assert first.versions(GDPR)[0].celex == GDPR  # calls go to the source
            expired = _settings(document_check_source_ttl_seconds=-1)
            with patch("src.document_check.service.get_settings", return_value=expired):
                assert service.shared_source() is not first
            assert len(made) == 2

    def test_a_source_that_cannot_be_built_is_a_503(self):
        with (
            patch(
                "src.document_check.sources.default_source",
                side_effect=OSError("Read-only file system: '/app/.cache'"),
            ),
            pytest.raises(DocumentCheckError) as error,
        ):
            service.shared_source()
        assert error.value.status_code == 503 and error.value.code == "source_unavailable"
        # Not remembered: the next request tries again.
        with patch("src.document_check.sources.default_source", return_value=FakeSource()):
            assert service.shared_source().versions(GDPR)

    def test_what_else_the_engine_reads_from_a_source(self):
        inner = FakeSource()
        inner.stale = {GDPR: "2026-11-10"}
        locked = service._LockedSource(inner)
        assert locked.stale == {GDPR: "2026-11-10"}
        assert getattr(locked, "missing", "default") == "default"
        with pytest.raises(AttributeError):
            locked._private  # noqa: B018

    def test_one_call_at_a_time(self):
        inside = []
        overlaps = []

        class Slow:
            def versions(self, celex):
                inside.append(celex)
                if len(inside) > 1:
                    overlaps.append(list(inside))
                time.sleep(0.02)
                inside.remove(celex)
                return []

            articles = versions

        locked = service._LockedSource(Slow())
        threads = [threading.Thread(target=locked.versions, args=(f"act{i}",)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert overlaps == []
