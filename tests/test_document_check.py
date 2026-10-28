"""Tests for src/document_check (prototype of "controlla un documento").

Offline: the official texts come from FakeSource, a small stand-in for CELLAR
with the AI Act's art. 4 before and after Regulation (EU) 2026/1744 and the
GDPR's art. 13.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.citation_verifier import parse_article
from src.crawler.eurlex.client import EurLexClient
from src.document_check.check import (
    CHANGED,
    ELSEWHERE,
    MISSING,
    NO_ACT,
    NOT_COVERED,
    NOT_FOUND,
    OUTDATED,
    UNAVAILABLE,
    VALID,
    VERIFIED,
    build_lock,
    check_text,
    fingerprint,
    paragraph_text,
    recheck,
)
from src.document_check.extract import (
    detect_language,
    extract_references,
    load_text,
    mentioned_acts,
)
from src.document_check.official import (
    ArticleText,
    CellarTextSource,
    TextUnavailableError,
    Version,
    assemble_articles,
    find_article,
)
from src.document_check.report import diff_html, render_html, render_recheck_html, summary_lines
from src.nlp.chunking.legal_chunker import LegalChunk

OLD_ART4 = (
    "Articolo 4\nAlfabetizzazione in materia di IA\nI fornitori e i deployer dei sistemi di IA "
    "adottano misure per garantire nella misura del possibile un livello sufficiente di "
    "alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che "
    "si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto."
)
NEW_ART4 = (
    "Articolo 4\nAlfabetizzazione in materia di IA\n1. I fornitori e i deployer di sistemi di IA "
    "adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del "
    "loro personale.\n2. La Commissione e gli Stati membri sostengono e agevolano gli sforzi dei "
    "fornitori e dei deployer di sistemi di IA, in particolare delle PMI."
)
ART50 = (
    "Articolo 50\nObblighi di trasparenza\n1. I fornitori garantiscono che i sistemi di IA "
    "destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in "
    "modo tale che le persone fisiche interessate siano informate del fatto di stare interagendo "
    "con un sistema di IA.\n2. Testo del paragrafo due.\n3. Testo del paragrafo tre.\n"
    "4. Testo del paragrafo quattro.\n5. Le informazioni di cui ai paragrafi da 1 a 4 sono "
    "fornite alle persone fisiche interessate in maniera chiara e distinguibile al più tardi al "
    "momento della prima interazione o esposizione.\n6. Testo del paragrafo sei.\n"
    "7. Testo del paragrafo sette."
)
ART13 = (
    "Articolo 13\nInformazioni da fornire qualora i dati personali siano raccolti presso "
    "l'interessato\n1. In caso di raccolta presso l'interessato di dati che lo riguardano, il "
    "titolare del trattamento fornisce all'interessato, nel momento in cui i dati personali sono "
    "ottenuti, le seguenti informazioni:"
)


def _article(label: str, text: str) -> ArticleText:
    key = parse_article(label)
    assert key is not None
    return ArticleText(key, label, text, tuple(re.findall(r"(?m)^(\d{1,3})\.\s", text)))


AI_OLD = [_article("Art. 4", OLD_ART4), _article("Art. 50", ART50)]
AI_NEW = [_article("Art. 4", NEW_ART4), _article("Art. 50", ART50)]
GDPR = [_article("Art. 13", ART13)]


class FakeSource:
    """CELLAR stand-in: the AI Act as adopted, on 12/07/2024 and on 27/07/2026; the GDPR."""

    def __init__(self, ai_versions: int = 3) -> None:
        ai = [
            Version("32024R1689", None),
            Version("02024R1689-20240712", "2024-07-12"),
            Version("02024R1689-20260727", "2026-07-27"),
        ]
        self._versions = {
            "32024R1689": ai[:ai_versions],
            "32016R0679": [
                Version("32016R0679", None),
                Version("02016R0679-20160504", "2016-05-04"),
            ],
        }
        self._articles = {
            "32024R1689": AI_OLD,
            "02024R1689-20240712": AI_OLD,
            "02024R1689-20260727": AI_NEW,
            "32016R0679": GDPR,
            "02016R0679-20160504": GDPR,
        }
        self.asked: list[str] = []
        self.unreadable: set[str] = set()

    def versions(self, celex: str) -> list[Version]:
        if celex not in self._versions:
            raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")
        return self._versions[celex]

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        self.asked.append(version.celex)
        if version.celex in self.unreadable:
            raise TextUnavailableError(f"CELLAR non ha il testo di {version.celex}")
        return self._articles[version.celex]


def _only(check, raw_part):
    found = [f for f in check.findings if raw_part in f.reference.raw]
    assert len(found) == 1, [f.reference.raw for f in check.findings]
    return found[0]


# ─── Extraction ──────────────────────────────────────────────────────


class TestExtraction:
    def _refs(self, text):
        return [
            ([(p.key, p.paragraphs) for p in r.provisions], r.act.key if r.act else None)
            for r in extract_references(text)
        ]

    def test_act_after_and_before_the_reference(self):
        assert self._refs("Ai sensi dell'art. 13 del GDPR.") == [([("art:13", ())], "32016R0679")]
        assert self._refs("GDPR, art. 13: informazioni.") == [([("art:13", ())], "32016R0679")]
        assert self._refs("L'assistente (AI Act, art. 50) informa.") == [
            ([("art:50", ())], "32024R1689")
        ]

    def test_formal_eu_names_and_old_formats(self):
        acts = mentioned_acts(
            "Regolamento (UE) 2016/679, Regulation (EU) 2024/1689, Direttiva 2013/34/UE, "
            "Regolamento (CE) n. 1907/2006, Directive (EU) 2022/2555"
        )
        assert [a.key for a in acts] == [
            "32016R0679",
            "32024R1689",
            "32013L0034",
            "32006R1907",
            "32022L2555",
        ]
        assert acts[0].label == "Regolamento (UE) 2016/679 (GDPR)"
        assert mentioned_acts("GDPR")[0].label == "GDPR"

    def test_defined_name_points_to_its_act(self):
        text = (
            "Il Regolamento (UE) 2016/679 (di seguito «Regolamento») si applica.\n"
            "Le informazioni dell'art. 13 del Regolamento vanno date subito."
        )
        assert self._refs(text) == [([("art:13", ())], "32016R0679")]

    def test_lists_ranges_paragraphs_and_suffixes(self):
        assert self._refs("Vedi artt. 13 e 14 GDPR.") == [
            ([("art:13", ()), ("art:14", ())], "32016R0679")
        ]
        assert self._refs("Vedi artt. 15-17 del GDPR.") == [
            ([("art:15", ()), ("art:16", ()), ("art:17", ())], "32016R0679")
        ]
        assert self._refs("Under Article 6(1)(f) GDPR.") == [([("art:6", ("1",))], "32016R0679")]
        assert self._refs("Art. 50, par. 5, AI Act.") == [([("art:50", ("5",))], "32024R1689")]
        assert self._refs("Il paragrafo 9 dell'articolo 50 dell'AI Act.") == [
            ([("art:50", ("9",))], "32024R1689")
        ]
        assert self._refs("L'art. 4 bis dell'AI Act.") == [([("art:4bis", ())], "32024R1689")]
        assert self._refs("Codice privacy, art. 2-ter.") == [
            ([("art:2ter", ())], "IT:dlgs:2003:196")
        ]

    def test_recitals_and_annexes(self):
        assert self._refs("Il considerando 47 del GDPR e l'Allegato III dell'AI Act.") == [
            ([("recital:47", ())], "32016R0679"),
            ([("annex:III", ())], "32024R1689"),
        ]

    def test_act_number_is_not_an_article(self):
        assert self._refs("art. 13, Regolamento (UE) 2016/679") == [
            ([("art:13", ())], "32016R0679")
        ]

    def test_italian_acts(self):
        keys = [
            a.key
            for a in mentioned_acts(
                "d.lgs. 196/2003; decreto legislativo 30 giugno 2003, n. 196; legge 23 settembre "
                "2025, n. 132; L. 132/2025; D.Lgs. n. 138/2024"
            )
        ]
        assert keys == ["IT:dlgs:2003:196", "IT:legge:2025:132", "IT:dlgs:2024:138"]

    def test_closer_act_wins(self):
        assert self._refs("La legge 23 settembre 2025, n. 132, art. 13, e la L. 132/2025.") == [
            ([("art:13", ())], "IT:legge:2025:132")
        ]

    def test_act_inferred_from_the_line_or_the_only_act(self):
        refs = extract_references("Il GDPR chiede trasparenza; vedi in particolare l'art. 12.")
        assert refs[0].act is not None and refs[0].act.key == "32016R0679"
        assert refs[0].act_inferred
        only = extract_references("Si applica il GDPR.\nSi veda l'art. 22.")
        assert only[0].act is not None and only[0].act_inferred
        none = extract_references("Si applicano GDPR e AI Act.\nSi veda l'art. 22.")
        assert none[0].act is None

    def test_quote_goes_to_the_nearest_reference(self):
        refs = extract_references(
            "L'art. 13 del GDPR e l'art. 4 dell'AI Act prevedono che i deployer «adottano misure "
            "per garantire un livello sufficiente»."
        )
        assert refs[0].quotes == []
        assert refs[1].quotes == ["adottano misure per garantire un livello sufficiente"]

    def test_lines_and_context(self):
        refs = extract_references("Titolo\n\nSecondo l'art. 13 del GDPR il titolare informa.")
        assert refs[0].line == 3
        assert "art. 13 del GDPR" in refs[0].context

    def test_language(self):
        assert detect_language("Il titolare del trattamento fornisce le informazioni") == "IT"
        assert detect_language("The controller shall provide the data subject with") == "EN"


# ─── Checking ────────────────────────────────────────────────────────

DOCUMENT = (
    "Informativa sull'uso dell'intelligenza artificiale\n"
    "Ai sensi dell'art. 4 dell'AI Act, i deployer «adottano misure per garantire nella misura "
    "del possibile un livello sufficiente di alfabetizzazione in materia di IA del loro "
    "personale».\n"
    "L'assistente del sito rispetta l'art. 50, par. 5, AI Act.\n"
    "Non esiste l'art. 50, par. 9, AI Act.\n"
    "Ai sensi dell'art. 13 del GDPR, il titolare «fornisce all'interessato, nel momento in cui i "
    "dati personali sono ottenuti, le seguenti informazioni».\n"
    "Resta fermo l'art. 13 del d.lgs. 196/2003.\n"
    "Si veda l'art. 22.\n"
)


class TestCheck:
    def test_outdated_quote_shows_then_and_now(self):
        check = check_text(DOCUMENT, FakeSource(), document="doc.txt", today="2026-10-28")
        f = _only(check, "art. 4 dell'AI Act")
        assert f.status is OUTDATED
        assert f.before_version is not None and f.before_version.celex == "02024R1689-20240712"
        assert f.before == OLD_ART4
        assert f.article is not None and f.article.text == NEW_ART4
        assert any("in vigore fino al 26/07/2026" in m for m in f.messages)

    def test_existing_and_missing_paragraphs(self):
        check = check_text(DOCUMENT, FakeSource(), today="2026-10-28")
        assert _only(check, "par. 5").status is VALID
        missing = _only(check, "par. 9")
        assert missing.status is MISSING
        assert any("da 1 a 7" in m for m in missing.messages)

    def test_verified_quote_keeps_the_official_words(self):
        check = check_text(DOCUMENT, FakeSource(), today="2026-10-28")
        f = _only(check, "art. 13 del GDPR")
        assert f.status is VERIFIED
        assert f.official_quote is not None and "le seguenti informazioni" in f.official_quote

    def test_italian_law_and_missing_act(self):
        check = check_text(DOCUMENT, FakeSource(), today="2026-10-28")
        italian = _only(check, "d.lgs. 196/2003")
        assert italian.status is NOT_COVERED
        assert italian.url and "decreto.legislativo:2003;196" in italian.url
        assert _only(check, "art. 22").status is NO_ACT

    def test_quote_in_another_article(self):
        text = (
            "L'art. 4 dell'AI Act dice che «le persone fisiche interessate siano informate del "
            "fatto di stare interagendo con un sistema di IA»."
        )
        f = check_text(text, FakeSource()).findings[0]
        assert f.status is ELSEWHERE
        assert any("Art. 50" in m for m in f.messages)

    def test_quote_not_found_anywhere(self):
        text = "L'art. 4 dell'AI Act dice che «ogni dipendente deve superare un esame annuale»."
        assert check_text(text, FakeSource()).findings[0].status is NOT_FOUND

    def test_short_quote_is_not_judged(self):
        f = check_text("L'art. 4 dell'AI Act parla di «alfabetizzazione in materia»", FakeSource())
        assert f.findings[0].status is VALID
        assert any("troppo breve" in m for m in f.findings[0].messages)

    def test_change_after_the_document_date(self):
        text = "L'art. 4 dell'AI Act chiede misure per il personale."
        before = check_text(text, FakeSource(), document_date="2026-03-01").findings[0]
        assert before.status is CHANGED
        assert before.before == OLD_ART4
        after = check_text(text, FakeSource(), document_date="2026-08-01").findings[0]
        assert after.status is VALID

    def test_unreachable_texts(self):
        f = check_text("L'art. 21 della NIS2 chiede misure.", FakeSource()).findings[0]
        assert f.status is UNAVAILABLE

    def test_unreadable_version_falls_back_to_the_one_before(self):
        source = FakeSource()
        source.unreadable = {"02024R1689-20240712"}
        text = (
            "L'art. 4 dell'AI Act chiede che i deployer «adottano misure per garantire nella "
            "misura del possibile un livello sufficiente di alfabetizzazione»."
        )
        f = check_text(text, source, document_date="2026-03-01").findings[0]
        assert f.status is OUTDATED
        assert f.before_version is not None and f.before_version.celex == "32024R1689"
        assert any("testo originale, in vigore fino al 26/07/2026" in m for m in f.messages)
        assert any("cambiato dopo la data del documento" in m for m in f.messages)

    def test_change_outside_the_cited_paragraph_is_only_noted(self):
        source = FakeSource()
        changed_art50 = ART50.replace("7. Testo del paragrafo sette.", "7. Testo nuovo.")
        source._articles["02024R1689-20260727"] = [
            _article("Art. 4", NEW_ART4),
            _article("Art. 50", changed_art50),
        ]
        text = "L'assistente rispetta l'art. 50, par. 5, AI Act."
        f = check_text(text, source, document_date="2026-03-01").findings[0]
        assert f.status is VALID
        assert any("ma non nella parte citata" in m for m in f.messages)
        whole = check_text("Vedi l'art. 50 dell'AI Act.", source, document_date="2026-03-01")
        assert whole.findings[0].status is CHANGED

    def test_paragraph_text(self):
        assert paragraph_text(
            ART50,
            "5",
        ).startswith("5. Le informazioni")
        assert paragraph_text(ART50, "9") is None


# ─── Lock file and re-check ──────────────────────────────────────────


class TestLockAndRecheck:
    def test_lock_records_the_provisions_in_force(self):
        check = check_text(DOCUMENT, FakeSource(), document="doc.txt", today="2026-10-28")
        lock = build_lock(check)
        keys = {(d["atto"], d["articolo"]) for d in lock["dipendenze"]}
        assert keys == {
            ("32024R1689", "Art. 4"),
            ("32024R1689", "Art. 50"),
            ("32016R0679", "Art. 13"),
        }
        art4 = next(d for d in lock["dipendenze"] if d["articolo"] == "Art. 4")
        assert art4["versione"] == "02024R1689-20260727"
        assert art4["impronta"] == fingerprint(NEW_ART4)
        json.dumps(lock)  # serialisable as written to disk

    def test_recheck_says_what_changed(self):
        text = "L'art. 4 dell'AI Act e l'art. 50 dell'AI Act."
        lock = build_lock(check_text(text, FakeSource(ai_versions=2)))  # checked before the Omnibus
        changes = {c.entry["articolo"]: c for c in recheck(lock, FakeSource())}
        assert changes["Art. 4"].code == "cambiato"
        assert changes["Art. 4"].before == OLD_ART4 and changes["Art. 4"].after == NEW_ART4
        assert changes["Art. 50"].code == "invariato"

    def test_recheck_without_new_versions_reads_nothing(self):
        source = FakeSource()
        lock = build_lock(check_text("L'art. 50 dell'AI Act.", source))
        fresh = FakeSource()
        assert [c.code for c in recheck(lock, fresh)] == ["invariato"]
        assert fresh.asked == []


# ─── Report ──────────────────────────────────────────────────────────


class TestReport:
    def test_html_report(self):
        check = check_text(
            DOCUMENT + "Nota <script>alert(1)</script> sull'art. 13 del GDPR.\n",
            FakeSource(),
            document="doc.txt",
            today="2026-10-28",
        )
        html = render_html(check, "doc.norma-lock.json")
        assert "Citazione superata" in html and "Da correggere" in html
        assert "<del>" in html and "<ins>" in html
        assert "<script>alert(1)</script>" not in html
        assert "doc.norma-lock.json" in html
        assert "decreto.legislativo:2003;196" in html

    def test_recheck_report(self):
        lock = build_lock(check_text("L'art. 4 dell'AI Act.", FakeSource(ai_versions=2)))
        html = render_recheck_html(lock, recheck(lock, FakeSource()), "2026-10-28")
        assert "Cambiato" in html and "<del>" in html

    def test_summary_and_diff(self):
        check = check_text(DOCUMENT, FakeSource(), document="doc.txt", today="2026-10-28")
        lines = summary_lines(check)
        assert lines[0].startswith("Controllo di doc.txt (28/10/2026)")
        assert any("Citazione superata" in line for line in lines)
        assert diff_html("a b c", "a x c") == "a <del>b</del> <ins>x</ins> c"


# ─── Official texts and documents ────────────────────────────────────


class TestOfficialTexts:
    def test_assemble_drops_repeated_headings(self):
        chunks = [
            LegalChunk("Articolo 50\nObblighi\n1. Primo.\n2. Secondo.", {"article": "Art. 50"}),
            LegalChunk("Articolo 50\nObblighi\n▼M1\n3. Terzo ►M1 nuovo◄.", {"article": "Art. 50"}),
            LegalChunk("Preambolo", {"article": "Preamble"}),
        ]
        [article] = assemble_articles(chunks)
        # Heading repeats and consolidation marks ("▼M1", "►M1 ... ◄") are gone.
        assert article.text == "Articolo 50\nObblighi\n1. Primo.\n2. Secondo.\n3. Terzo nuovo."
        assert article.paragraphs == ("1", "2", "3")
        assert find_article([article], "art:50") is article

    def test_list_consolidated_celex(self):
        client = EurLexClient(request_delay=0)
        rows = {
            "results": {
                "bindings": [
                    {"celex": {"value": v}}
                    for v in ("02024R1689-20260727", "garbage", "02024R1689-20240712")
                ]
            }
        }
        with patch.object(client, "_execute_sparql", return_value=rows) as ex:
            assert client.list_consolidated_celex("32024R1689") == [
                "02024R1689-20240712",
                "02024R1689-20260727",
            ]
        assert '"02024R1689-"' in ex.call_args[0][0]
        with (
            patch.object(client, "_execute_sparql", side_effect=RuntimeError("offline")),
            pytest.raises(RuntimeError),
        ):
            client.list_consolidated_celex("32024R1689")


class TestLoadText:
    def test_docx(self, tmp_path):
        docx = pytest.importorskip("docx")
        document = docx.Document()
        document.add_paragraph("Ai sensi dell'art. 13 del GDPR.")
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Base"
        table.rows[0].cells[1].text = "art. 6 GDPR"
        path = tmp_path / "informativa.docx"
        document.save(str(path))
        text = load_text(path)
        assert "art. 13 del GDPR" in text and "art. 6 GDPR" in text

    def test_html(self, tmp_path):
        path = tmp_path / "pagina.html"
        path.write_text(
            "<html><script>x()</script><body><p>Vedi l'art. 50 dell'AI Act.</p></body></html>",
            encoding="utf-8",
        )
        text = load_text(path)
        assert "art. 50 dell'AI Act" in text and "x()" not in text

    def test_pdf(self, tmp_path):
        fpdf = pytest.importorskip("fpdf")
        pytest.importorskip("pypdf")
        pdf = fpdf.FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, "Ai sensi dell'art. 13 del GDPR il titolare informa.")
        path = tmp_path / "policy.pdf"
        pdf.output(str(path))
        assert "art. 13 del GDPR" in load_text(path)

    def test_unsupported(self, tmp_path):
        with pytest.raises(ValueError):
            load_text(tmp_path / "foglio.xlsx")


def test_command_line(tmp_path, capsys):
    script = Path(__file__).resolve().parent.parent / "scripts" / "check_document.py"
    spec = importlib.util.spec_from_file_location("check_document", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = tmp_path / "informativa.txt"
    document.write_text(DOCUMENT, encoding="utf-8")
    with patch.object(module, "CellarTextSource", return_value=FakeSource()):
        assert module.main([str(document), "--cache", str(tmp_path / "cache")]) == 0
        report = tmp_path / "informativa.controllo.html"
        lock = tmp_path / "informativa.norma-lock.json"
        assert report.exists() and lock.exists()
        assert module.main(["--ricontrolla", str(lock), "--cache", str(tmp_path / "cache")]) == 0
    assert (tmp_path / "informativa.ricontrollo.html").exists()
    out = capsys.readouterr().out
    assert "Citazione superata" in out


# ─── CELLAR source with a fake client ────────────────────────────────

_MINIMAL_ACT = (
    "<html><body><p>HANNO ADOTTATO IL PRESENTE REGOLAMENTO:</p>"
    "<p>Articolo 4</p><p>Alfabetizzazione in materia di IA</p>"
    "<p>1. I fornitori e i deployer di sistemi di IA adottano misure volte a sostenere lo "
    "sviluppo dell'alfabetizzazione in materia di IA del loro personale.</p>"
    "<p>2. La Commissione e gli Stati membri sostengono gli sforzi dei fornitori.</p>"
    "</body></html>"
)


class FakeClient:
    """EurLexClient stand-in: one consolidated AI Act with its text; no text for older ids."""

    def __init__(self) -> None:
        self.listed = 0
        self.downloaded: list[str] = []

    def list_consolidated_celex(self, celex: str) -> list[str]:
        self.listed += 1
        return ["02024R1689-20260727"]

    def download_full_text_html(self, celex: str, lang: str = "EN") -> str | None:
        self.downloaded.append(celex)
        return _MINIMAL_ACT if celex == "02024R1689-20260727" else None


class TestCellarTextSource:
    def test_versions_are_cached_for_a_day(self, tmp_path):
        client = FakeClient()
        assert CellarTextSource(tmp_path, client).versions("32024R1689") == [
            Version("32024R1689", None),
            Version("02024R1689-20260727", "2026-07-27"),
        ]
        CellarTextSource(tmp_path, client).versions("32024R1689")
        assert client.listed == 1
        cache = tmp_path / "32024R1689.versions.json"
        stale = json.loads(cache.read_text(encoding="utf-8"))
        stale["asked_at"] = "2020-01-01T00:00:00+00:00"
        cache.write_text(json.dumps(stale), encoding="utf-8")
        CellarTextSource(tmp_path, client).versions("32024R1689")
        assert client.listed == 2

    def test_unreachable_version_list(self, tmp_path):
        client = FakeClient()
        with (
            patch.object(client, "list_consolidated_celex", side_effect=RuntimeError("offline")),
            pytest.raises(TextUnavailableError),
        ):
            CellarTextSource(tmp_path, client).versions("32024R1689")

    def test_articles_are_parsed_and_cached_on_disk(self, tmp_path):
        client = FakeClient()
        version = Version("02024R1689-20260727", "2026-07-27")
        [art4] = CellarTextSource(tmp_path, client).articles(version, "it")
        assert art4.label == "Art. 4" and art4.paragraphs == ("1", "2")
        CellarTextSource(tmp_path, client).articles(version, "IT")
        assert client.downloaded == ["02024R1689-20260727"]

    def test_missing_text_is_remembered(self, tmp_path):
        client = FakeClient()
        old = Version("02024R1689-20240712", "2024-07-12")
        source = CellarTextSource(tmp_path, client)
        for _ in range(2):
            with pytest.raises(TextUnavailableError):
                source.articles(old, "IT")
        with pytest.raises(TextUnavailableError):
            CellarTextSource(tmp_path, client).articles(old, "IT")
        assert client.downloaded == ["02024R1689-20240712"]
        assert (tmp_path / "02024R1689-20240712.IT.missing").exists()
