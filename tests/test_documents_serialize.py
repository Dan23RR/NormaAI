"""Tests for src/document_check/serialize.py: a check to JSON and back.

Offline: the official texts come from tests/documents_support.FakeSource.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.document_check import serialize
from src.document_check.check import Change, Finding, Status, build_lock, check_text, recheck
from src.document_check.extract import Act, Provision, Reference
from src.document_check.official import Version
from src.document_check.report import render_html
from tests.documents_support import (
    AI_ACT,
    ART13,
    ART13_AMENDED,
    ART50,
    CLEAN_DOCUMENT,
    DOCUMENT,
    GDPR,
    NEW_ART4,
    OLD_ART4,
    FakeSource,
    article,
)

NOW = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)
LATER = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)

FINDING_KEYS = {
    "id",
    "group",
    "status",
    "line",
    "raw",
    "context",
    "act",
    "provision",
    "version",
    "url",
    "messages",
    "quotes",
    "official_quote",
    "differences",
    "before",
    "after_text",
}


@pytest.fixture
def checked():
    source = FakeSource()
    check = check_text(DOCUMENT, source, document="informativa.docx", today="2026-11-03")
    lock = build_lock(check)
    return check, lock, source


def _by_raw(findings, part):
    found = [f for f in findings if part in f["raw"]]
    assert len(found) == 1, [f["raw"] for f in findings]
    return found[0]


# ─── Findings ────────────────────────────────────────────────────────


class TestFindings:
    def test_every_finding_has_the_fields_of_the_contract(self, checked):
        check, lock, _ = checked
        findings = serialize.findings_to_json(check, lock)
        assert [f["id"] for f in findings] == ["f1", "f2", "f3", "f4", "f5", "f6"]
        for finding in findings:
            assert set(finding) >= FINDING_KEYS
            assert finding["group"] in ("correggere", "controllare", "a_posto", "non_coperto")
            assert set(finding["status"]) == {"code", "label"}
            assert set(finding["act"]) == {"source", "id", "name", "label"}
            assert set(finding["provision"]) >= {"key", "label"}
            assert isinstance(finding["messages"], list) and finding["messages"]
            assert isinstance(finding["quotes"], list)
            assert isinstance(finding["differences"], list)
        json.dumps(findings)  # plain JSON, nothing else

    def test_an_outdated_quote_keeps_the_provision_then_and_now(self, checked):
        check, lock, _ = checked
        outdated = _by_raw(serialize.findings_to_json(check, lock), "art. 4 dell'AI Act")
        assert outdated["group"] == "correggere"
        assert outdated["status"] == {"code": "superata", "label": "Citazione superata"}
        assert outdated["line"] == 2
        assert outdated["act"] == {
            "source": "eurlex",
            "id": AI_ACT,
            "name": "AI Act",
            "label": "AI Act",
        }
        assert outdated["provision"] == {"key": "art:4", "label": "art. 4", "paragraphs": []}
        assert outdated["version"] == {
            "id": "02024R1689-20260727",
            "as_of": "2026-07-27",
            "label": "testo consolidato al 27/07/2026",
        }
        assert outdated["url"].endswith("uri=CELEX:02024R1689-20260727")
        assert outdated["before"] == {
            "version_label": "testo consolidato al 12/07/2024",
            "version_id": "02024R1689-20240712",
            "as_of": "2024-07-12",
            "text": OLD_ART4,
        }
        assert outdated["after_text"] == NEW_ART4
        assert outdated["dependency"] == {"source": "eurlex", "act": AI_ACT, "key": "art:4"}

    def test_an_altered_quote_shows_the_words_that_differ(self, checked):
        check, lock, _ = checked
        altered = _by_raw(serialize.findings_to_json(check, lock), "par. 5")
        assert altered["status"]["code"] == "alterata"
        assert altered["differences"] == [{"quoted": "3", "official": "4"}]
        assert "paragrafi da 1 a 4" in altered["official_quote"]
        assert "paragrafi da 1 a 3" in altered["altered_quote"]
        assert altered["quotes"] == [altered["altered_quote"]]
        assert altered["provision"] == {
            "key": "art:50",
            "label": "art. 50, par. 5",
            "paragraphs": ["5"],
        }
        assert altered["before"] is None and altered["after_text"] is None

    def test_a_verified_quote(self, checked):
        check, lock, _ = checked
        verified = _by_raw(serialize.findings_to_json(check, lock), "art. 13 del GDPR")
        assert verified["group"] == "a_posto"
        assert verified["status"] == {"code": "verificata", "label": "Citazione verificata"}
        assert verified["official_quote"].endswith("le seguenti informazioni")
        assert verified["differences"] == []
        assert verified["dependency"] == {"source": "eurlex", "act": GDPR, "key": "art:13"}

    def test_italian_law_and_a_reference_without_an_act(self, checked):
        check, lock, _ = checked
        findings = serialize.findings_to_json(check, lock)
        italian = _by_raw(findings, "d.lgs. 196/2003")
        assert italian["group"] == "non_coperto"
        assert italian["act"]["source"] == "normattiva"
        assert italian["version"] is None
        assert italian["dependency"] is None
        assert "normattiva.it" in italian["url"]
        orphan = _by_raw(findings, "art. 22")
        assert orphan["status"]["code"] == "atto_mancante"
        assert orphan["act"] == {
            "source": None,
            "id": None,
            "name": "Atto non indicato",
            "label": "Atto non indicato",
        }
        assert orphan["provision"] == {"key": None, "label": "art. 22", "paragraphs": []}
        assert orphan["version"] is None and orphan["url"] is None

    def test_only_160_characters_of_the_document_are_kept(self, checked):
        secret = "Il compenso pattuito con il cliente Bianchi è di 12.000 euro."
        filler = " ".join(["Premessa generale senza riferimenti di legge."] * 6)
        text = (
            f"{secret}\n"
            f"{filler} {secret} {filler} Si applica l'art. 13 del GDPR. {filler} {secret}\n"
        )
        check = check_text(text, FakeSource(), document="nota.txt", today="2026-11-03")
        findings = serialize.findings_to_json(check, build_lock(check))
        assert len(findings) == 1
        context = findings[0]["context"]
        assert len(context) <= serialize.CONTEXT_LIMIT
        assert "art. 13 del GDPR" in context
        assert context.startswith("... ") and context.endswith(" ...")
        stored = json.dumps(findings, ensure_ascii=False)
        assert "Bianchi" not in stored and "12.000" not in stored

    def test_status_is_the_worst_group_present(self, checked):
        check, lock, _ = checked
        status, counts = serialize.summarize(serialize.findings_to_json(check, lock))
        assert status == "correggere"
        assert counts == {"correggere": 3, "controllare": 1, "a_posto": 1, "non_coperto": 1}

        def of(*groups):
            return serialize.summarize([{"group": g} for g in groups])[0]

        assert of("a_posto", "controllare") == "controllare"
        assert of("a_posto", "non_coperto") == "a_posto"
        assert of("non_coperto") == "non_coperto"
        assert of() == "a_posto"
        assert serialize.summarize([])[1] == {
            "correggere": 0,
            "controllare": 0,
            "a_posto": 0,
            "non_coperto": 0,
        }


class TestClipContext:
    def test_short_context_is_left_alone(self):
        assert serialize.clip_context("Si veda l'art. 22.", "art. 22") == "Si veda l'art. 22."

    def test_long_context_is_cut_around_the_reference(self):
        words = "parola " * 60
        context = f"{words}secondo l'art. 13 del GDPR il titolare informa {words}"
        clipped = serialize.clip_context(context, "art. 13 del GDPR")
        assert len(clipped) <= 160
        assert "art. 13 del GDPR" in clipped
        assert clipped.startswith("... parola") and clipped.endswith("parola ...")
        assert "…" not in clipped

    def test_the_marks_of_extract_become_three_dots(self):
        clipped = serialize.clip_context("… testo prima dell'art. 5 e dopo …", "art. 5")
        assert clipped == "... testo prima dell'art. 5 e dopo ..."

    def test_whitespace_in_the_reference_does_not_matter(self):
        context = ("x " * 100) + "art.  13\tdel GDPR" + (" y" * 100)
        clipped = serialize.clip_context(context, "art. 13 del GDPR")
        assert "art. 13 del GDPR" in clipped and len(clipped) <= 160

    def test_a_reference_longer_than_the_limit(self):
        raw = "art. " + "1, " * 80 + "2"
        clipped = serialize.clip_context(f"prima {raw} dopo", raw)
        assert len(clipped) <= 160


# ─── Dependencies and the lock ───────────────────────────────────────


class TestDependencies:
    def test_one_dependency_per_provision_found_in_force(self, checked):
        _, lock, _ = checked
        dependencies = serialize.dependencies_to_json(lock)
        assert [(d["act"], d["key"]) for d in dependencies] == [
            (AI_ACT, "art:4"),
            (AI_ACT, "art:50"),
            (GDPR, "art:13"),
        ]
        gdpr = dependencies[2]
        assert gdpr["source"] == "eurlex"
        assert gdpr["name"] == "GDPR" and gdpr["article"] == "Art. 13"
        assert gdpr["version"] == "02016R0679-20160504" and gdpr["as_of"] == "2016-05-04"
        assert gdpr["fingerprint"].startswith("sha256:") and gdpr["text"] == ART13
        assert gdpr["cited_as"] == ["art. 13 del GDPR"]
        assert gdpr["state"] == "current" and gdpr["changed_at"] is None

    def test_public_form_has_no_official_text(self, checked):
        _, lock, _ = checked
        public = serialize.dependency_public(serialize.dependencies_to_json(lock)[0])
        assert set(public) >= {
            "source",
            "act",
            "name",
            "article",
            "key",
            "version",
            "as_of",
            "fingerprint",
            "state",
            "changed_at",
        }
        assert "text" not in public and "change" not in public
        assert public["state"] == "current" and public["changed_at"] is None

    def test_lock_round_trip(self, checked):
        _, lock, source = checked
        dependencies = serialize.dependencies_to_json(lock)
        rebuilt = serialize.lock_from_json(
            dependencies,
            document="informativa.docx",
            checked_on="2026-11-03",
            document_date=None,
            lang="IT",
        )
        # A lock without "fonte" means EUR-Lex: the rebuilt one says it.
        expected = {**lock, "dipendenze": [{"fonte": "eurlex", **e} for e in lock["dipendenze"]]}
        assert rebuilt["dipendenze"] == [
            {key: entry[key] for key in rebuilt["dipendenze"][0]}
            for entry in expected["dipendenze"]
        ]
        assert {k: v for k, v in rebuilt.items() if k != "dipendenze"} == {
            k: v for k, v in lock.items() if k != "dipendenze"
        }
        assert [c.code for c in recheck(rebuilt, source)] == [c.code for c in recheck(lock, source)]

    def test_lock_for_the_surveillance_carries_nothing_of_the_document(self, checked):
        _, lock, source = checked
        bare = serialize.lock_from_json(
            serialize.dependencies_to_json(lock), document="informativa.docx", with_document=False
        )
        assert bare["documento"] == ""
        assert all(entry["riferimenti"] == [] for entry in bare["dipendenze"])
        assert [c.code for c in recheck(bare, source)] == ["invariato"] * 3

    def test_an_italian_act_identified_by_its_urn_is_linked_by_name(self):
        # After the Normattiva source the lock names an Italian act by its URN.
        act = Act("IT:dlgs:2003:196", "D.Lgs. 196/2003 (Codice privacy)")
        provision = Provision("art:13")
        reference = Reference(0, 0, [provision], act=act, raw="art. 13 del d.lgs. 196/2003", line=1)
        text = "Art. 13\nTesto di prova dell'articolo."
        finding = Finding(
            reference,
            provision,
            act,
            Status("valido", "Riferimento valido", "a_posto"),
            ["Art. 13 esiste."],
            version=Version("urn:nir:stato:decreto.legislativo:2003-06-30;196", "2026-01-01"),
            article=article("Art. 13", text),
        )
        urn = "urn:nir:stato:decreto.legislativo:2003-06-30;196"
        lock = {
            "lingua": "IT",
            "dipendenze": [
                {
                    "fonte": "normattiva",
                    "atto": urn,
                    "nome": finding.act_name,
                    "versione": urn,
                    "consolidato_al": "2026-01-01",
                    "articolo": "Art. 13",
                    "chiave": "art:13",
                    "lingua": "IT",
                    "impronta": "sha256:abc",
                    "testo": text,
                    "riferimenti": [reference.raw],
                }
            ],
        }
        check = check_text("", FakeSource(), document="x")
        check.findings = [finding]
        stored = serialize.findings_to_json(check, lock)[0]
        assert stored["dependency"] == {"source": "normattiva", "act": urn, "key": "art:13"}
        assert stored["act"]["source"] == "normattiva"
        assert serialize.dependencies_to_json(lock)[0]["source"] == "normattiva"


# ─── What a re-check means ───────────────────────────────────────────


def _change(code, after=None, version=None, message="msg"):
    return Change({}, code, message, version, "before", after)


class TestNextState:
    def _dependency(self, **over):
        return {"state": "current", "changed_at": None, "change": None, "lang": "IT", **over}

    def test_unchanged(self):
        update = serialize.next_state(self._dependency(), _change("invariato"), NOW)
        assert (update.state, update.changed_at, update.change) == ("current", None, None)
        assert update.verified and not update.is_new

    def test_a_change_is_new_once(self):
        version = Version("02016R0679-20270101", "2027-01-01")
        change = _change("cambiato", "nuovo testo", version, "Art. 13 è cambiato.")
        first = serialize.next_state(self._dependency(), change, NOW)
        assert first.state == "changed" and first.is_new and first.verified
        assert first.changed_at == NOW
        assert first.change["version"] == "02016R0679-20270101"
        assert first.change["as_of"] == "2027-01-01"
        assert first.change["label"] == "testo consolidato al 01/01/2027"
        assert first.change["text"] == "nuovo testo"
        assert first.change["message"] == "Art. 13 è cambiato."
        assert first.change["url"].endswith("uri=CELEX:02016R0679-20270101")

        seen = self._dependency(state=first.state, changed_at=first.changed_at, change=first.change)
        again = serialize.next_state(seen, change, LATER)
        assert again.state == "changed" and not again.is_new
        assert again.changed_at == NOW  # the day it was first seen

    def test_a_later_wording_is_a_new_change(self):
        first = serialize.next_state(self._dependency(), _change("cambiato", "testo B"), NOW)
        seen = self._dependency(state="changed", changed_at=NOW, change=first.change)
        newer_version_same_words = serialize.next_state(
            seen,
            _change("cambiato", "testo B", Version("02016R0679-20280101", "2028-01-01")),
            LATER,
        )
        assert not newer_version_same_words.is_new
        assert newer_version_same_words.change["version"] == "02016R0679-20280101"
        other_words = serialize.next_state(seen, _change("cambiato", "testo C"), LATER)
        assert other_words.is_new and other_words.changed_at == LATER

    def test_removed(self):
        update = serialize.next_state(self._dependency(), _change("soppresso"), NOW)
        assert update.state == "removed" and update.is_new and update.change["text"] is None
        seen = self._dependency(state="removed", changed_at=NOW, change=update.change)
        assert not serialize.next_state(seen, _change("soppresso"), LATER).is_new

    def test_unreachable_text_never_hides_a_change(self):
        fresh = serialize.next_state(self._dependency(), _change("non_disponibile"), NOW)
        assert fresh.state == "unavailable" and not fresh.verified and not fresh.is_new
        assert fresh.change == {"message": "msg"}
        change = {"digest": "abc", "text": "nuovo"}
        seen = self._dependency(state="changed", changed_at=NOW, change=change)
        kept = serialize.next_state(seen, _change("non_disponibile"), LATER)
        assert (kept.state, kept.changed_at, kept.change) == ("changed", NOW, change)
        assert not kept.verified and not kept.is_new

    def test_back_to_the_text_of_the_check(self):
        seen = self._dependency(state="changed", changed_at=NOW, change={"digest": "abc"})
        update = serialize.next_state(seen, _change("invariato"), LATER)
        assert (update.state, update.changed_at, update.change) == ("current", None, None)


class TestEffectiveFindings:
    def _stored(self, document=CLEAN_DOCUMENT):
        source = FakeSource()
        check = check_text(document, source, document="nota.txt", today="2026-11-03")
        lock = build_lock(check)
        return (
            serialize.findings_to_json(check, lock),
            serialize.dependencies_to_json(lock),
            source,
        )

    def _recheck(self, dependencies, source, now=NOW):
        lock = serialize.lock_from_json(dependencies)
        for dependency, change in zip(dependencies, recheck(lock, source), strict=True):
            update = serialize.next_state(dependency, change, now)
            dependency.update(
                state=update.state, changed_at=update.changed_at, change=update.change
            )

    def test_nothing_changed_nothing_shown(self):
        findings, dependencies, _ = self._stored()
        assert serialize.effective_findings(findings, dependencies) == findings

    def test_a_changed_provision_moves_its_findings_to_correggere(self):
        findings, dependencies, source = self._stored()
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        self._recheck(dependencies, source)
        effective = serialize.effective_findings(findings, dependencies)
        changed = _by_raw(effective, "art. 13 del GDPR")
        assert changed["group"] == "correggere"
        assert changed["status"] == {"code": "cambiato", "label": "Cambiato dopo il controllo"}
        assert changed["before"] == {
            "version_label": "testo consolidato al 04/05/2016",
            "version_id": "02016R0679-20160504",
            "as_of": "2016-05-04",
            "text": ART13,
        }
        assert changed["after_text"] == ART13_AMENDED
        assert changed["version"] == {
            "id": "02016R0679-20270101",
            "as_of": "2027-01-01",
            "label": "testo consolidato al 01/01/2027",
        }
        assert changed["url"].endswith("uri=CELEX:02016R0679-20270101")
        assert changed["messages"][-1] == "Art. 13 è cambiato nel testo consolidato al 01/01/2027."
        untouched = _by_raw(effective, "art. 50, par. 1")
        assert untouched == _by_raw(findings, "art. 50, par. 1")
        # The stored findings are not modified.
        assert _by_raw(findings, "art. 13 del GDPR")["group"] == "a_posto"
        assert serialize.summarize(effective)[0] == "correggere"

    def test_a_removed_provision(self):
        findings, dependencies, source = self._stored()
        source.publish(GDPR, "2027-01-01", [article("Art. 12", "Articolo 12\nAltro.")])
        self._recheck(dependencies, source)
        removed = _by_raw(serialize.effective_findings(findings, dependencies), "art. 13 del GDPR")
        assert removed["status"] == {
            "code": "inesistente",
            "label": "Non esiste più nel testo vigente",
        }
        assert removed["group"] == "correggere"
        assert removed["before"]["text"] == ART13 and removed["after_text"] is None

    def test_a_finding_already_to_correct_keeps_its_own_outcome(self):
        findings, dependencies, source = self._stored(DOCUMENT)
        source.publish(
            AI_ACT,
            "2027-01-01",
            [article("Art. 4", NEW_ART4 + "\n3. Nuovo paragrafo."), article("Art. 50", ART50)],
        )
        self._recheck(dependencies, source)
        outdated = _by_raw(serialize.effective_findings(findings, dependencies), "art. 4 dell'AI")
        assert outdated["status"]["code"] == "superata"
        assert outdated["before"]["text"] == OLD_ART4 and outdated["after_text"] == NEW_ART4
        assert outdated["messages"][-1] == "Art. 4 è cambiato nel testo consolidato al 01/01/2027."

    def test_an_unreachable_text_changes_no_finding(self):
        findings, dependencies, source = self._stored()
        source.unreachable = {GDPR}
        self._recheck(dependencies, source)
        assert [d["state"] for d in dependencies] == ["unavailable", "current"]
        assert serialize.effective_findings(findings, dependencies) == findings


# ─── The report from stored findings ─────────────────────────────────


class TestReportFromStoredFindings:
    def test_same_report_as_the_one_of_the_check(self):
        # Every line of this document fits in the stored context.
        check = check_text(CLEAN_DOCUMENT, FakeSource(), document="nota.txt", today="2026-11-03")
        findings = serialize.findings_to_json(check, build_lock(check))
        rebuilt = serialize.check_from_json(
            findings, document="nota.txt", checked_on="2026-11-03", document_date=None, lang="IT"
        )
        assert render_html(rebuilt) == render_html(check)

    def test_every_outcome_is_rendered(self, checked):
        check, lock, _ = checked
        findings = serialize.findings_to_json(check, lock)
        rebuilt = serialize.check_from_json(
            findings,
            document="informativa.docx",
            checked_on="2026-11-03",
            document_date="2026-03-01",
            lang="IT",
        )
        html = render_html(rebuilt)
        direct = render_html(check)
        for fragment in (
            "Citazione superata",
            "Citazione diversa dal testo ufficiale",
            "Differenze tra la citazione nel documento e il testo ufficiale",
            "Differenze tra il testo consolidato al 12/07/2024 e il testo consolidato al 27/07/2026",
            "Atto non indicato, art. 22",
            "AI Act, art. 50, par. 9",
            "Testo vigente su EUR-Lex",
            "D.Lgs. 196/2003 (Codice privacy), art. 13",
            "normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003;196",
            "Data del documento: 01/03/2026",
        ):
            assert fragment in html, fragment
            if "Data del documento" not in fragment:
                assert fragment in direct, fragment
        assert [f.status.group for f in rebuilt.findings] == [
            f.status.group for f in check.findings
        ]
        assert [f.url for f in rebuilt.findings] == [f.url for f in check.findings]

    def test_labels_are_the_stored_ones(self):
        stored = {
            "id": "f1",
            "group": "a_posto",
            "status": {"code": "valido", "label": "Riferimento valido"},
            "line": 3,
            "raw": "art. 13, comma 1, del Codice privacy",
            "context": "Vale l'art. 13, comma 1, del Codice privacy.",
            "act": {
                "source": "normattiva",
                "id": "urn:nir:stato:decreto.legislativo:2003-06-30;196",
                "name": "Codice privacy",
                "label": "D.Lgs. 196/2003 (Codice privacy)",
            },
            "provision": {"key": "art:13", "label": "art. 13, comma 1", "paragraphs": ["1"]},
            "version": {"id": "v1", "as_of": "2026-01-01", "label": "testo vigente al 01/01/2026"},
            "url": "https://www.normattiva.it/esempio",
            "messages": ["Art. 13, comma 1 esiste."],
            "quotes": [],
            "official_quote": None,
            "differences": [],
            "before": None,
            "after_text": None,
        }
        finding = serialize.check_from_json(
            [stored], document="x", checked_on="2026-11-03", document_date=None, lang="IT"
        ).findings[0]
        assert finding.provision.label == "art. 13, comma 1"
        assert finding.version.label == "testo vigente al 01/01/2026"
        assert finding.act_name == "Codice privacy"
        assert finding.url == "https://www.normattiva.it/esempio"
        assert finding.act is not None and not finding.act.eu


def test_iso_z():
    assert serialize.iso_z(None) is None
    assert serialize.iso_z(datetime(2026, 11, 11, 16, 20, tzinfo=UTC)) == "2026-11-11T16:20:00Z"
    # SQLite gives back datetimes without a zone: they are UTC.
    assert serialize.iso_z(datetime(2026, 11, 11, 16, 20, 5, 999)) == "2026-11-11T16:20:05Z"
