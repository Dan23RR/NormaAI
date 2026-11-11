"""Tests for Italian law in the document check (src/document_check/normattiva.py).

Offline. The texts are answers of the Normattiva open data API recorded on
11 November 2026 (tests/fixtures/normattiva: each file names the URN asked and
says what was cut): article 2-ter of the Codice privacy in three wordings and
before it existed, its repealed article 13 with the last wording, a repealed
article that Normattiva labels with another Latin form, an article of the
Codice civile, of law 132/2025, of d.lgs. 138/2024, of the TUIR with its repeal
already published, of the Statuto dei lavoratori with two rulings of the
Constitutional Court in the notes, and the four error bodies.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.crawler.normattiva.urn_validator import URNValidator
from src.document_check import check as check_module
from src.document_check.check import (
    ACT_UNCLEAR,
    ALTERED,
    CHANGED,
    MISSING,
    NOT_COVERED,
    NOT_FOUND,
    OUTDATED,
    PARTIAL,
    RULING,
    SCHEDULED,
    UNAVAILABLE,
    VALID,
    VERIFIED,
    build_lock,
    check_text,
    fingerprint,
    recheck,
)
from src.document_check.extract import (
    Provision,
    extract_references,
    latin_ordinal,
    mentioned_acts,
)
from src.document_check.normattiva import (
    API_BASE,
    ARTICLE_ENDPOINT,
    IN_FORCE,
    NOT_IN_FORCE,
    REPEALED,
    ActNotFoundError,
    ArticleNotFoundError,
    ItalianVersion,
    NormattivaClient,
    NormattivaTextSource,
    article_tokens,
    article_url,
    parse_article_html,
    same_article_number,
)
from src.document_check.official import CellarTextSource, TextUnavailableError
from src.document_check.report import render_html, render_recheck_html, summary_lines
from src.document_check.sources import OfficialSources, default_source
from tests.test_document_check import FakeSource

FIXTURES = Path(__file__).parent / "fixtures" / "normattiva"
TODAY = "2026-11-11"
PRIVACY = "urn:nir:stato:decreto.legislativo:2003;196"
AI_LAW = "urn:nir:stato:legge:2025;132"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _html(name: str) -> str:
    return str(_fixture(name)["body"]["data"]["atto"]["articoloHtml"])


def _year_only(urn: str) -> str:
    """ "...:2024-09-04;138" and "...:2024;138" name one act."""
    return re.sub(r":(\d{4})-\d{2}-\d{2};", r":\1;", urn)


class RecordedApi:
    """NormattivaClient stand-in that answers with the recorded fixtures.

    ``article("<act>~art2ter!vig=<day>")`` gives the recorded wording in force
    on that day; an article that was not recorded does not exist, an act that
    was not recorded is not on Normattiva, and ``down`` makes every call fail.
    """

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.down = False
        self.wordings: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for path in sorted(FIXTURES.glob("*.json")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            if fixture["status"] != 200:
                continue
            urn = re.split(r"[!@]", fixture["_source"]["urn"])[0]
            act, _, token = urn.partition("~")
            self.wordings.setdefault((_year_only(act), token), []).append(
                fixture["body"]["data"]["atto"]
            )

    @property
    def acts(self) -> set[str]:
        """The acts recorded, each also without the number of its annex."""
        recorded = {act for act, _ in self.wordings}
        return recorded | {re.sub(r"(;\d+):\d+$", r"\1", act) for act in recorded}

    def article(self, urn: str) -> dict[str, Any]:
        self.asked.append(urn)
        if self.down:
            raise TextUnavailableError(f"Normattiva non ha risposto per {urn}: errore di rete")
        m = re.fullmatch(r"(?P<act>[^~]+)~(?P<token>[a-z0-9]+)(?P<rest>!vig=.*|@originale)", urn)
        assert m, urn
        act = _year_only(m.group("act"))
        if re.sub(r"(;\d+):\d+$", r"\1", act) not in self.acts:
            raise ActNotFoundError(_fixture("error_act-not-found.json")["body"]["message"])
        wordings = self.wordings.get((act, m.group("token")), [])
        if m.group("rest") == "@originale":
            first = min(wordings, key=lambda w: int(w["articoloDataInizioVigenza"]), default=None)
            if first is None or first["articoloDataInizioVigenza"] == "0":
                raise ArticleNotFoundError("Nessun articolo trovato")
            return first
        day = m.group("rest").removeprefix("!vig=").replace("-", "")
        for wording in wordings:
            if wording["articoloDataInizioVigenza"] <= day <= wording["articoloDataFineVigenza"]:
                return wording
        raise ArticleNotFoundError(_fixture("error_article-not-found.json")["body"]["message"])


class NoEuSource:
    """EU side of a source in tests that only read Italian law."""

    def versions(self, celex: str) -> list[Any]:
        raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")

    def articles(self, version: Any, lang: str) -> list[Any]:
        raise TextUnavailableError("nessun testo")


@pytest.fixture
def api() -> RecordedApi:
    return RecordedApi()


@pytest.fixture
def source(tmp_path: Path, api: RecordedApi) -> OfficialSources:
    return OfficialSources(NoEuSource(), NormattivaTextSource(tmp_path, api))  # type: ignore[arg-type]


def _one(text: str, source: OfficialSources, **kwargs: Any):
    check = check_text(text, source, today=TODAY, **kwargs)
    assert len(check.findings) == 1, [f.reference.raw for f in check.findings]
    return check.findings[0]


# ─── Citations and URNs ──────────────────────────────────────────────


class TestItalianCitations:
    @pytest.mark.parametrize(
        ("text", "key", "paragraphs", "urn"),
        [
            (
                "art. 13 della legge 23 settembre 2025, n. 132",
                "art:13",
                (),
                "urn:nir:stato:legge:2025;132",
            ),
            (
                "articolo 24 del d.lgs. 138/2024",
                "art:24",
                (),
                "urn:nir:stato:decreto.legislativo:2024;138",
            ),
            ("art. 2-ter del D.Lgs. n. 196 del 2003", "art:2ter", (), PRIVACY),
            (
                "art. 1 del decreto-legge 21 settembre 2021, n. 127",
                "art:1",
                (),
                "urn:nir:stato:decreto.legge:2021;127",
            ),
            (
                "art. 46 del D.P.R. 445/2000",
                "art:46",
                (),
                "urn:nir:stato:decreto.del.presidente.della.repubblica:2000;445",
            ),
            ("art. 4, comma 1, l. 300/1970", "art:4", ("1",), "urn:nir:stato:legge:1970;300"),
            ("art. 2043 c.c.", "art:2043", (), "urn:nir:stato:regio.decreto:1942-03-16;262:2"),
            (
                "art. 1341, secondo comma, cod. civ.",
                "art:1341",
                ("2",),
                "urn:nir:stato:regio.decreto:1942-03-16;262:2",
            ),
            (
                "art. 640 del Codice penale",
                "art:640",
                (),
                "urn:nir:stato:regio.decreto:1930-10-19;1398:1",
            ),
            ("art. 2-quaterdecies del Codice privacy", "art:2quaterdecies", (), PRIVACY),
            ("art. 18 dello Statuto dei lavoratori", "art:18", (), "urn:nir:stato:legge:1970;300"),
            (
                "art. 33 del Codice del consumo",
                "art:33",
                (),
                "urn:nir:stato:decreto.legislativo:2005;206",
            ),
            (
                "art. 20, comma 1-bis, del CAD",
                "art:20",
                ("1bis",),
                "urn:nir:stato:decreto.legislativo:2005;82",
            ),
            (
                "art. 51 TUIR",
                "art:51",
                (),
                "urn:nir:stato:decreto.del.presidente.della.repubblica:1986;917",
            ),
            ("art. 6 d.lgs. 231/2001", "art:6", (), "urn:nir:stato:decreto.legislativo:2001;231"),
            (
                "art. 18 del d.lgs. 81/2008",
                "art:18",
                (),
                "urn:nir:stato:decreto.legislativo:2008;81",
            ),
            ("art. 2 della l. 241/1990", "art:2", (), "urn:nir:stato:legge:1990;241"),
            ("art. 41 Cost.", "art:41", (), "urn:nir:stato:costituzione:1947-12-27"),
            ("art. 163 c.p.c.", "art:163", (), "urn:nir:stato:regio.decreto:1940-10-28;1443:1"),
            (
                "art. 335 c.p.p.",
                "art:335",
                (),
                "urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447",
            ),
            # Two-digit years, a date in digits, the law everyone calls by another name.
            ("art. 2 l. 241/90", "art:2", (), "urn:nir:stato:legge:1990;241"),
            ("art. 6 D.Lgs. 231/01", "art:6", (), "urn:nir:stato:decreto.legislativo:2001;231"),
            ("legge 20.5.1970, n. 300, art. 7", "art:7", (), "urn:nir:stato:legge:1970;300"),
            ("art. 67 r.d. 267/1942", "art:67", (), "urn:nir:stato:regio.decreto:1942;267:1"),
            (
                "art. 67 della legge fallimentare",
                "art:67",
                (),
                "urn:nir:stato:regio.decreto:1942;267:1",
            ),
            (
                "art. 1 legge costituzionale 3/2001",
                "art:1",
                (),
                "urn:nir:stato:legge.costituzionale:2001;3",
            ),
        ],
    )
    def test_every_form_gives_the_urn_normattiva_answers_to(self, text, key, paragraphs, urn):
        [ref] = extract_references(text)
        assert [(p.key, p.paragraphs) for p in ref.provisions] == [(key, paragraphs)]
        assert ref.act is not None and ref.act.urn == urn
        assert not ref.act.eu and ref.act.source == "normattiva" and ref.act.identifier == urn
        assert ref.act.normattiva_url == "https://www.normattiva.it/uri-res/N2Ls?" + urn

    def test_numbered_state_acts_pass_the_older_urn_validator(self):
        for text in ("d.lgs. 196/2003", "legge 132/2025", "D.L. 127/2021", "r.d. 267/1942"):
            [act] = mentioned_acts(text)
            assert act.urn is not None and URNValidator.validate_format(act.urn)

    def test_the_date_written_in_the_document_is_kept(self):
        [act] = mentioned_acts("legge 23 settembre 2025, n. 132")
        assert act.date == "2025-09-23" and act.key == "IT:legge:2025:132"
        assert mentioned_acts("D.Lgs. 30/6/2003, n. 196")[0].date == "2003-06-30"
        assert mentioned_acts("d.lgs. 196/2003")[0].date is None

    def test_comma_first_and_ordinal_commi(self):
        [ref] = extract_references("il comma 1-bis dell'articolo 2-ter del Codice privacy")
        assert ref.provisions == [Provision("art:2ter", ("1bis",), commi=True)]
        assert ref.provisions[0].label == "art. 2 ter, comma 1-bis"
        [ref] = extract_references("il terzo comma dell'articolo 18 della legge n. 300 del 1970")
        assert ref.provisions == [Provision("art:18", ("3",), commi=True)]
        [ref] = extract_references("art. 2112, commi primo e secondo, c.c.")
        assert ref.provisions[0].paragraphs == ("1", "2")
        assert extract_references("Art. 50, par. 5, AI Act.")[0].provisions[0].label == (
            "art. 50, par. 5"
        )

    def test_latin_suffixes(self):
        assert [latin_ordinal(s) for s in ("bis", "decies", "quaterdecies", "vicies semel")] == [
            2,
            10,
            14,
            21,
        ]
        assert latin_ordinal("quindecies") == latin_ordinal("quinquiesdecies") == 15
        assert latin_ordinal("xyz") is None
        [ref] = extract_references("art. 1, comma 2-vicies semel, d.lgs. 58/1998")
        assert ref.provisions[0].paragraphs == ("2viciessemel",)

    def test_acts_the_check_does_not_read_are_recognised_not_guessed(self):
        for text, kind in (
            ("art. 3 della legge regionale Lombardia 11 marzo 2005, n. 12", "lr"),
            ("art. 4 del D.M. 10 marzo 2014, n. 55", "dm"),
            ("art. 2 del d.P.C.M. 3 dicembre 2013", "dpcm"),
            ("art. 5 del decreto 81/2008", "decreto"),
            ("art. 63 disp. att. c.c.", "dispatt"),
            ("la circolare INPS n. 12 del 2020, par. 3 e art. 5", "circ"),
        ):
            refs = extract_references(text)
            assert refs and refs[-1].act is not None, text
            assert refs[-1].act.key.split(":")[1] == kind, text
            assert refs[-1].act.urn is None and refs[-1].act.not_read, text

    def test_a_bare_decree_is_the_one_the_document_names_in_full(self):
        text = (
            "Il decreto legislativo 4 settembre 2024, n. 138 recepisce la NIS2.\n"
            "Si veda l'art. 24 del decreto 138/2024."
        )
        refs = extract_references(text)
        assert refs[-1].act is not None and refs[-1].act.key == "IT:dlgs:2024:138"

    def test_abbreviations_count_only_next_to_an_article(self):
        assert mentioned_acts("In c.c. all'ufficio del personale, come da CAD 2D allegato.") == []
        assert extract_references("art. 30 c.c.n.l. Metalmeccanici")[0].act is None
        assert extract_references("art. 133 c.p.a.")[0].act is None
        assert extract_references("artt. 1341 e 1342 c.c.")[0].act.key == "IT:cc"
        assert extract_references("c.c., art. 2043")[0].act.key == "IT:cc"
        assert extract_references("art. 5 del codice penale militare di pace")[0].act is None

    def test_an_article_alone_goes_to_the_only_act_named(self):
        only = extract_references("Si applica il d.lgs. 231/2001.\nSi veda l'art. 6.")
        assert only[0].act is not None and only[0].act_inferred
        assert only[0].act.key == "IT:dlgs:2001:231"
        two = extract_references("Si applicano il GDPR e il Codice privacy.\nSi veda l'art. 22.")
        assert two[0].act is None

    def test_what_a_quoted_passage_cites_is_not_a_reference_of_the_document(self):
        text = (
            "L'art. 2-ter del Codice privacy dispone: «La base giuridica prevista dall'articolo "
            "6, paragrafo 3, lettera b), del regolamento (UE) 2016/679 è costituita da una norma "
            "di legge». Resta fermo l'art. 5."
        )
        refs = extract_references(text)
        assert [r.provisions[0].key for r in refs] == ["art:2ter", "art:5"]
        assert len(refs[0].quotes) == 1
        # The regulation is named only inside the quote: it is not the act of "art. 5".
        assert refs[1].act is not None and refs[1].act.key == "IT:dlgs:2003:196"


# ─── The API's HTML ──────────────────────────────────────────────────


class TestParsing:
    def test_numbered_commi_without_editorial_marks(self):
        parsed = parse_article_html(_html("dlgs-196-2003_art2ter_2021-12-08.json"))
        assert parsed.label == "Art. 2-ter" and parsed.state == IN_FORCE and parsed.numbered
        # "1-bis" has no mark of its own in the HTML: it is found after comma 1.
        assert parsed.commi == ("1", "1bis", "2", "3", "4")
        assert parsed.lines[0].startswith("(Base giuridica per il trattamento")
        assert parsed.comma_texts["1"] == (
            "1. La base giuridica prevista dall'articolo 6, paragrafo 3, lettera b), del "
            "regolamento è costituita da una norma di legge o di regolamento o da atti "
            "amministrativi generali."
        )
        text = "\n".join(parsed.lines)
        assert "((" not in text and "))" not in text and "AGGIORNAMENTO" not in text
        # "PERIODO SOPPRESSO DAL D.L. ..." in the middle of comma 2 is Normattiva's, not the law's.
        assert "SOPPRESSO" not in text
        assert parsed.comma_texts["2"].endswith("o se necessaria ai sensi del comma 1-bis.")
        assert parsed.comma_texts["4"].count("\n") == 2  # the two letters of the list
        assert "AGGIORNAMENTO (49)" in parsed.notes

    def test_repealed_and_not_yet_in_force(self):
        repealed = parse_article_html(_html("dlgs-196-2003_art13_repealed.json"))
        assert repealed.state == REPEALED and repealed.commi == ()
        assert repealed.lines == ["ARTICOLO ABROGATO DAL D.LGS. 10 AGOSTO 2018, N. 101"]
        act = parse_article_html(_html("dpr-917-1986_art51_2027-01-01.json"))
        assert act.state == REPEALED and act.lines[0].startswith("PROVVEDIMENTO ABROGATO")
        early = parse_article_html(_html("dlgs-196-2003_art2ter_not-yet.json"))
        assert early.state == NOT_IN_FORCE and early.label == "Art. 2-ter"

    def test_a_label_in_another_latin_form_is_the_same_article(self):
        parsed = parse_article_html(_html("dlgs-196-2003_art2quinquiesdecies_repealed.json"))
        assert parsed.label == "Art. 2-quindecies" and parsed.state == REPEALED
        # The text repeats "Art. 2-quinquiesdecies": it is the label, not a line of law.
        assert parsed.lines[0].startswith("ARTICOLO ABROGATO")
        assert same_article_number("art:2quinquiesdecies", parsed.label)
        assert not same_article_number("art:2quaterdecies", parsed.label)
        assert not same_article_number("art:2", parsed.label)

    def test_a_code_article_has_its_commi_counted(self):
        parsed = parse_article_html(_html("rd-262-1942-2_art1341.json"))
        assert parsed.label == "Art. 1341" and not parsed.numbered
        assert parsed.lines[0] == "(Condizioni generali di contratto)."
        assert parsed.commi == ("1", "2")
        assert parsed.comma_texts["2"].startswith("In ogni caso non hanno effetto")

    def test_notes_are_kept_apart_and_their_pointers_removed(self):
        parsed = parse_article_html(_html("legge-300-1970_art18.json"))
        assert parsed.label == "Art. 18" and not parsed.numbered
        assert parsed.lines[0] == "Tutela del lavoratore in caso di licenziamento illegittimo"
        assert parsed.notes.count("illegittimità costituzionale") >= 2
        assert "AGGIORNAMENTO" not in "\n".join(parsed.lines)

    def test_a_number_inside_a_quoted_amendment_is_not_a_comma(self):
        html = (
            '<div class="bodyTesto"><h2 class="article-num-akn">Art. 44</h2>'
            '<div class="article-heading-akn">Disposizioni finanziarie</div>'
            '<div class="art-commi-div-akn"><div class="art-comma-div-akn">'
            '<span class="comma-num-akn">1. </span><span class="art_text_in_comma">I commi '
            "sono sostituiti dai seguenti:<br>&laquo;512. Le amministrazioni provvedono.<br>"
            "516. Le amministrazioni possono procedere.&raquo;.</span></div>"
            '<div class="art-comma-div-akn"><span class="comma-num-akn">2. </span>'
            '<span class="art_text_in_comma">Resta fermo il comma 1.<br>2.1. Inserito dopo.'
            "</span></div></div></div>"
        )
        parsed = parse_article_html(html)
        assert parsed.commi == ("1", "2", "2.1")
        assert "516. Le amministrazioni" in parsed.comma_texts["1"]

    def test_an_article_given_in_part(self):
        commi = "".join(
            f'<div class="art-comma-div-akn"><span class="comma-num-akn">{n}. </span>'
            f'<span class="art_text_in_comma">Testo del comma {n}.</span></div>'
            for n in range(1, 101)
        )
        html = (
            '<div class="bodyTesto"><h2 class="preamble-title-akn">IL PRESIDENTE</h2>'
            '<p class="formula-introduttiva">Promulga la seguente legge:</p>'
            f'<h2 class="article-num-akn">Art. 1</h2><div class="art-commi-div-akn">{commi}'
            "</div></div>"
        )
        parsed = parse_article_html(html)
        assert parsed.partial and len(parsed.commi) == 100
        # The preamble that comes with article 1 is not part of the article.
        assert parsed.lines[0] == "1. Testo del comma 1."

    def test_a_first_article_given_as_plain_text_after_the_preamble(self):
        html = (
            '<div class="bodyTesto"><h2 class="article-num-akn">Art. 1</h2>'
            '<span class="art-just-text-akn">IL PRESIDENTE DELLA REPUBBLICA<br>Visti gli '
            "articoli 76 e 87 della Costituzione;<br>EMANA il seguente decreto legislativo:<br>"
            "Articolo 1.<br>Principio del risultato.<br>1. Le stazioni appaltanti perseguono il "
            "risultato.<br>2. La concorrenza è funzionale.</span></div>"
        )
        parsed = parse_article_html(html)
        assert parsed.lines[0] == "Principio del risultato." and parsed.commi == ("1", "2")

    def test_an_article_that_replaces_another_keeps_the_line_with_its_number(self):
        html = (
            '<div class="bodyTesto"><h2 class="article-num-akn">Art. 2</h2>'
            '<div class="art-commi-div-akn"><div class="art-comma-div-akn">'
            '<span class="comma-num-akn">1. </span><span class="art_text_in_comma">L\'articolo 2 '
            "della legge è sostituito dal seguente:<br>Art. 2.<br>(Finalità)<br>La legge "
            "promuove la trasparenza.</span></div></div></div>"
        )
        parsed = parse_article_html(html)
        assert parsed.lines[0].startswith("1. L'articolo 2 della legge è sostituito")
        assert parsed.lines[1] == "Art. 2." and parsed.commi == ("1",)

    def test_urn_tokens(self):
        assert article_tokens("art:13") == ["art13"]
        assert article_tokens("art:2ter") == ["art2ter"]
        assert article_tokens("art:2quinquiesdecies") == ["art2quinquiesdecies", "art2quindecies"]
        assert article_tokens("art:19a") == [] and article_tokens("annex:III") == []
        assert article_url(PRIVACY, "art:2ter", "2026-11-11") == (
            f"https://www.normattiva.it/uri-res/N2Ls?{PRIVACY}~art2ter!vig=2026-11-11"
        )
        assert article_url(PRIVACY, "art:13", original=True).endswith("~art13@originale")


# ─── HTTP client ─────────────────────────────────────────────────────


def _client(handler) -> NormattivaClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return NormattivaClient(http=http, delay=0, retries=2)


def _reply(name: str) -> httpx.Response:
    fixture = _fixture(name)
    return httpx.Response(fixture["status"], json=fixture["body"])


class TestClient:
    def test_one_post_per_article_with_the_urn(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _reply("legge-132-2025_art13.json")

        act = _client(handler).article(f"{AI_LAW}~art13!vig=2026-11-11")
        assert act["titolo"] == "LEGGE 23 settembre 2025, n. 132"
        assert act["articoloDataInizioVigenza"] == "20251010"
        [request] = seen
        assert request.method == "POST" and str(request.url) == API_BASE + ARTICLE_ENDPOINT
        assert json.loads(request.content) == {"urn": f"{AI_LAW}~art13!vig=2026-11-11"}

    def test_the_default_client_names_itself_and_has_a_timeout(self):
        client = NormattivaClient()
        try:
            assert client._http.headers["User-Agent"].startswith("NormaAI/")
            assert client._http.timeout.read == 20.0 and client.retries == 2
        finally:
            client.close()

    def test_errors_of_the_api(self):
        with pytest.raises(ArticleNotFoundError):
            _client(lambda r: _reply("error_article-not-found.json")).article("urn~art999")
        with pytest.raises(ArticleNotFoundError):
            _client(lambda r: _reply("error_not-in-the-original.json")).article("urn~art2ter")
        with pytest.raises(ActNotFoundError):
            _client(lambda r: _reply("error_act-not-found.json")).article("urn~art1")
        with pytest.raises(ActNotFoundError):
            _client(lambda r: _reply("error_unknown-act-type.json")).article("urn~art1")
        with pytest.raises(TextUnavailableError):
            _client(lambda r: httpx.Response(200, text="<html>blocked</html>")).article("urn")
        with pytest.raises(TextUnavailableError):
            _client(lambda r: httpx.Response(200, json={"data": {"atto": None}})).article("urn")

    def test_an_error_that_is_not_about_the_law_is_never_read_as_a_missing_article(self):
        # The gateway's own 404 (a path that changed), as the specification shows it.
        gateway = {
            "code": "404",
            "type": "Status report",
            "message": "Runtime Error",
            "description": "No matching resource found for given API Request",
        }
        with pytest.raises(TextUnavailableError, match="HTTP 404"):
            _client(lambda r: httpx.Response(404, json=gateway)).article("urn~art1")
        # The site's protection (HTTP 409), which blocked the older crawler.
        blocked = {"status": "KO", "message": "La pagina richiesta è stata bloccata"}
        with pytest.raises(TextUnavailableError, match="HTTP 409"):
            _client(lambda r: httpx.Response(409, json=blocked)).article("urn~art1")
        with pytest.raises(TextUnavailableError, match="HTTP 400"):
            _client(lambda r: httpx.Response(400, json={"error": "Bad Request"})).article("urn")
        with pytest.raises(TextUnavailableError, match="HTTP 404"):
            _client(lambda r: httpx.Response(404, text="Not Found")).article("urn~art1")

    def test_a_server_error_is_tried_again(self):
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) < 3:
                return httpx.Response(503, text="busy")
            return _reply("legge-132-2025_art13.json")

        assert _client(handler).article("urn")["numeroProvvedimento"] == 132
        assert len(calls) == 3

    def test_an_unreachable_api_gives_up_after_the_retries(self):
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError("offline")

        with pytest.raises(TextUnavailableError, match="errore di rete"):
            _client(handler).article("urn")
        assert len(calls) == 3

    def test_an_act_published_twice_is_one_act_and_two_acts_are_not_chosen_between(self):
        act = _fixture("legge-132-2025_art13.json")["body"]["data"]["atto"]
        later = {**act, "annoGU": 2026, "meseGU": 1, "giornoGU": 30}

        def twice(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"atto": None, "lista": [later, act]}})

        assert _client(twice).article("urn")["annoGU"] == 2025
        other = {**act, "titolo": "LEGGE 1 gennaio 2025, n. 1"}

        def two(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"atto": None, "lista": [act, other]}})

        with pytest.raises(TextUnavailableError, match="più atti"):
            _client(two).article("urn")


# ─── Source and cache ────────────────────────────────────────────────


class TestSource:
    def test_an_article_in_force(self, tmp_path, api):
        article = NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        assert article.label == "Art. 13" and article.state == IN_FORCE
        assert (article.start, article.end, article.asked) == ("2025-10-10", None, TODAY)
        assert article.commi == ("1", "2") and article.numbered and not article.partial
        assert article.act_title == "LEGGE 23 settembre 2025, n. 132"
        assert article.act_date == "2025-09-23"
        assert article.act_subject.startswith("Disposizioni e deleghe al Governo")
        assert article.text.startswith("Art. 13\nDisposizioni in materia di professioni")
        assert api.asked == [f"{AI_LAW}~art13!vig={TODAY}"]
        version = article.version(current=True)
        assert isinstance(version, ItalianVersion) and version.celex == version.as_of == TODAY
        assert version.label == "testo vigente al 11/11/2026"
        assert version.url("IT") == (
            f"https://www.normattiva.it/uri-res/N2Ls?{AI_LAW}~art13!vig={TODAY}"
        )

    def test_a_wording_is_asked_once_for_all_the_days_it_covers(self, tmp_path, api):
        source = NormattivaTextSource(tmp_path, api)
        source.article(AI_LAW, "art:13", TODAY)
        assert source.article(AI_LAW, "art:13", "2026-03-15").asked == "2026-03-15"
        # Another process finds the answer on disk.
        NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        assert len(api.asked) == 1
        assert (tmp_path / "stato_legge_2025_132_art_13.json").exists()

    def test_a_wording_in_force_is_asked_again_after_a_day(self, tmp_path, api):
        NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        path = tmp_path / "stato_legge_2025_132_art_13.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["answers"][0]["fetched_at"] = "2026-11-01T08:00:00+00:00"
        path.write_text(json.dumps(data), encoding="utf-8")
        NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        assert len(api.asked) == 2

    def test_a_wording_that_has_ended_is_kept_for_a_month(self, tmp_path, api):
        NormattivaTextSource(tmp_path, api).article(PRIVACY, "art:2ter", "2020-01-01")
        path = tmp_path / "stato_decreto.legislativo_2003_196_art_2ter.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["answers"][0]["fetched_at"] = "2026-11-01T08:00:00+00:00"
        path.write_text(json.dumps(data), encoding="utf-8")
        again = NormattivaTextSource(tmp_path, api).article(PRIVACY, "art:2ter", "2019-06-30")
        assert (again.start, again.end) == ("2018-09-19", "2021-10-08")
        assert len(api.asked) == 1

    def test_when_the_api_does_not_answer_an_older_answer_is_used_and_said(self, tmp_path, api):
        NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        path = tmp_path / "stato_legge_2025_132_art_13.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["answers"][0]["fetched_at"] = "2026-11-01T08:00:00+00:00"
        path.write_text(json.dumps(data), encoding="utf-8")
        api.down = True
        stale = NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        assert stale.stale and stale.asked == "2026-11-01" and stale.state == IN_FORCE
        with pytest.raises(TextUnavailableError):
            NormattivaTextSource(tmp_path, api).article(PRIVACY, "art:2ter", TODAY)

    def test_missing_articles_and_acts_are_remembered(self, tmp_path, api):
        source = NormattivaTextSource(tmp_path, api)
        with pytest.raises(ArticleNotFoundError):
            source.article(AI_LAW, "art:999", TODAY)
        # The article is looked for in the act and in its first two annexes, once.
        assert api.asked == [
            f"{AI_LAW}~art999!vig={TODAY}",
            f"{AI_LAW}:1~art999!vig={TODAY}",
            f"{AI_LAW}:2~art999!vig={TODAY}",
        ]
        with pytest.raises(ArticleNotFoundError):
            NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:999", TODAY)
        assert len(api.asked) == 3
        with pytest.raises(ActNotFoundError):
            source.article("urn:nir:stato:legge:2024;9999", "art:1", TODAY)
        with pytest.raises(ActNotFoundError):
            source.article("urn:nir:stato:legge:2024;9999", "art:2", TODAY)
        assert len(api.asked) == 4  # the second article of an act that is not there is not asked

    def test_an_article_of_an_annex_is_found_and_keeps_its_urn(self, tmp_path, api):
        decree = "urn:nir:stato:regio.decreto:1942;262"
        article = NormattivaTextSource(tmp_path, api).article(decree, "art:1341", TODAY)
        assert article.urn == f"{decree}:2" and article.label == "Art. 1341"
        assert api.asked == [f"{decree}~art1341!vig={TODAY}", f"{decree}:1~art1341!vig={TODAY}",
                             f"{decree}:2~art1341!vig={TODAY}"]  # fmt: skip

    def test_the_api_drops_a_suffix_it_does_not_know(self, tmp_path):
        class Dropping:
            """The API answers ~art24xyz and ~art24bis with article 24 (seen on 2026-11-11)."""

            def __init__(self) -> None:
                self.asked: list[str] = []

            def article(self, urn: str) -> dict[str, Any]:
                self.asked.append(urn)
                if ":1~" in urn or ":2~" in urn:
                    raise ArticleNotFoundError("")
                return _fixture("dlgs-138-2024_art24.json")["body"]["data"]["atto"]

        api = Dropping()
        source = NormattivaTextSource(tmp_path, api)  # type: ignore[arg-type]
        with pytest.raises(ArticleNotFoundError, match="Art. 24"):
            source.article("urn:nir:stato:decreto.legislativo:2024;138", "art:24bis", TODAY)
        assert source.article("urn:nir:stato:decreto.legislativo:2024;138", "art:24", TODAY)

    def test_an_article_labelled_in_another_latin_form(self, tmp_path, api):
        article = NormattivaTextSource(tmp_path, api).article(
            PRIVACY, "art:2quinquiesdecies", TODAY
        )
        assert article.state == REPEALED and article.label == "Art. 2-quindecies"
        assert article.repeal_note.startswith("ARTICOLO ABROGATO DAL D.L. 8 OTTOBRE 2021, N. 139")

    def test_the_original_text(self, tmp_path, api):
        source = NormattivaTextSource(tmp_path, api)
        original = source.original(AI_LAW, "art:13")
        assert original.original and original.version().label == "testo originale"
        assert original.version().url().endswith("~art13@originale")
        source.original(AI_LAW, "art:13")
        assert api.asked == [f"{AI_LAW}~art13@originale"]
        with pytest.raises(ArticleNotFoundError):  # inserted in 2018: not in the original act
            source.original(PRIVACY, "art:2ter")
        with pytest.raises(ArticleNotFoundError):
            source.original(PRIVACY, "art:2ter")
        assert api.asked.count(f"{PRIVACY}~art2ter@originale") == 1

    def test_default_source_reads_both(self, tmp_path):
        source = default_source(tmp_path)
        assert isinstance(source, OfficialSources)
        assert isinstance(source.eu, CellarTextSource)
        assert isinstance(source.italian, NormattivaTextSource)
        assert source.italian.cache_dir == tmp_path / "normattiva" and source.stale == {}


# ─── Checking ────────────────────────────────────────────────────────


class TestItalianCheck:
    def test_article_and_comma_exist(self, source):
        f = _one("Vale l'art. 13, comma 2, della legge 23 settembre 2025, n. 132.", source)
        assert f.status is VALID and f.act is not None and f.act.key == "IT:legge:2025:132"
        assert f.article is not None and f.article.label == "Art. 13"
        assert isinstance(f.version, ItalianVersion) and f.version.as_of == TODAY
        assert f.url == f"https://www.normattiva.it/uri-res/N2Ls?{AI_LAW}~art13!vig={TODAY}"
        assert f.messages[0] == (
            "Art. 13, comma 2 esiste nel testo vigente al 11/11/2026 su Normattiva."
        )
        assert f.messages[-1] == "Atto letto su Normattiva: LEGGE 23 settembre 2025, n. 132."

    def test_missing_commi_numbered_and_counted(self, source):
        f = _one("Vale l'art. 13, comma 5, della legge 132/2025.", source)
        assert f.status is MISSING
        assert "Il comma 5 non esiste" in f.messages[0] and "da 1 a 2" in f.messages[0]
        ok = _one("Si applica l'art. 1341, secondo comma, c.c.", source)
        assert ok.status is VALID
        f = _one("Si applica l'art. 1341, terzo comma, c.c.", source)
        assert f.status is MISSING and "ha 2 commi, non numerati" in f.messages[0]
        f = _one("Si veda l'art. 2-ter, comma 1-bis, del Codice privacy.", source)
        assert f.status is VALID
        f = _one("Si veda l'art. 2-ter, comma 1-ter, del Codice privacy.", source)
        assert f.status is MISSING and "Il comma 1-ter non esiste" in f.messages[0]

    def test_quote_verified_word_for_word(self, source):
        text = (
            "L'art. 13 della legge 132/2025 dispone che «l'utilizzo di sistemi di intelligenza "
            "artificiale nelle professioni intellettuali è finalizzato al solo esercizio delle "
            "attività strumentali e di supporto all'attività professionale»."
        )
        f = _one(text, source)
        assert f.status is VERIFIED and f.status.group == "a_posto"
        assert f.official_quote is not None and f.official_quote.startswith("L'utilizzo di sistemi")
        assert "La citazione è nel testo vigente, parola per parola." in f.messages

    def test_quote_with_a_changed_number_is_altered(self, source):
        text = (
            "L'art. 24 del d.lgs. 138/2024 chiede misure «adeguate e proporzionate, secondo le "
            "modalità e i termini di cui agli articoli 30, 31 e 33, alla gestione dei rischi»."
        )
        f = _one(text, source)
        assert f.status is ALTERED and f.status.group == "correggere"
        assert f.differences == [{"quoted": "33", "official": "32"}]
        assert f.official_quote is not None and "articoli 30, 31 e 32" in f.official_quote
        assert any("nel documento «33», nel testo ufficiale «32»" in m for m in f.messages)

    OLD_QUOTE = (
        "L'art. 2-ter del Codice privacy prevede che la base giuridica «è costituita "
        "esclusivamente da una norma di legge o, nei casi previsti dalla legge, di regolamento»."
    )

    def test_quote_of_the_wording_at_the_documents_date_is_outdated(self, source):
        f = _one(self.OLD_QUOTE, source, document_date="2020-01-01")
        assert f.status is OUTDATED
        assert f.before is not None and "costituita esclusivamente da una norma" in f.before
        assert f.article is not None and "o da atti amministrativi generali" in f.article.text
        assert f.before_version is not None
        assert f.before_version.label == "testo in vigore dal 19/09/2018 al 08/10/2021"
        assert any("non al testo vigente" in m for m in f.messages)
        assert any("cambiato dopo la data del documento (01/01/2020)" in m for m in f.messages)

    def test_quote_of_an_earlier_wording_is_found_without_a_date(self, source):
        f = _one(self.OLD_QUOTE, source)
        assert f.status is OUTDATED
        # The newest wording that has the quote: the decree-law's, before its conversion.
        assert f.before_version is not None
        assert f.before_version.label == "testo in vigore dal 09/10/2021 al 07/12/2021"

    def test_quote_that_is_in_no_wording(self, source):
        text = (
            "L'art. 13 della legge 132/2025 dice che «ogni professionista deve superare un "
            "esame annuale sull'intelligenza artificiale»."
        )
        f = _one(text, source)
        assert f.status is NOT_FOUND
        assert any("il controllo legge solo gli articoli citati" in m for m in f.messages)

    def test_changed_after_the_documents_date(self, source):
        text = "Il trattamento si fonda sull'art. 2-ter del Codice privacy."
        f = _one(text, source, document_date="2020-01-01")
        assert f.status is CHANGED and f.status.group == "correggere"
        assert f.before is not None and "esclusivamente" in f.before
        assert any("oggi vale il testo in vigore dal 08/12/2021" in m for m in f.messages)
        assert _one(text, source, document_date="2022-01-01").status is VALID
        # Before the article existed.
        early = _one(text, source, document_date="2015-01-01")
        assert early.status is VALID
        assert any("non era in vigore" in m for m in early.messages)

    def test_a_change_outside_the_cited_commi_is_only_noted(self, source):
        text = "Le definizioni sono all'art. 2-ter, comma 4, del Codice privacy."
        f = _one(text, source, document_date="2020-01-01")
        assert f.status is VALID
        assert any("ma non nei commi citati" in m for m in f.messages)
        changed = "Vale l'art. 2-ter, comma 1, del Codice privacy."
        assert _one(changed, source, document_date="2020-01-01").status is CHANGED
        # A comma that did not exist at the document's date: it changed.
        new = "Vale l'art. 2-ter, comma 1-bis, del Codice privacy."
        assert _one(new, source, document_date="2020-01-01").status is CHANGED

    def test_repealed_article_shows_its_last_wording(self, source):
        f = _one("L'informativa è resa ai sensi dell'art. 13 del d.lgs. 196/2003.", source)
        assert f.status is MISSING and f.article is None
        assert f.messages[0] == (
            "Art. 13, D.Lgs. 196/2003 (Codice privacy), risulta abrogato dal 19/09/2018. "
            "Normattiva riporta: «ARTICOLO ABROGATO DAL D.LGS. 10 AGOSTO 2018, N. 101»."
        )
        assert f.before is not None and f.before.startswith("Art. 13\n(Informativa)")
        assert f.before_version is not None
        assert f.before_version.label == "testo in vigore dal 13/07/2011 al 18/09/2018"
        assert build_lock(check_text("art. 13 del d.lgs. 196/2003", source))["dipendenze"] == []

    def test_quote_of_a_repealed_article(self, source):
        text = (
            "Ai sensi dell'art. 13 del Codice privacy «l'interessato o la persona presso la quale "
            "sono raccolti i dati personali sono previamente informati oralmente o per iscritto»."
        )
        f = _one(text, source)
        assert f.status is MISSING
        assert any("l'ultimo prima dell'abrogazione" in m for m in f.messages)

    def test_article_that_does_not_exist(self, source):
        f = _one("Si veda l'art. 99 della legge 132/2025.", source)
        assert f.status is MISSING and f.article is None
        assert f.messages[0].startswith("Art. 99 non esiste: Legge 132/2025 non ha questo articolo")
        f = _one("Si veda l'art. 2-quaterdecies della legge 132/2025.", source)
        assert f.status is MISSING

    def test_act_that_normattiva_does_not_have(self, source):
        f = _one("Si veda l'art. 5 della legge 9999/2024.", source)
        assert f.status is ACT_UNCLEAR and f.status.group == "controllare"
        assert "il numero, l'anno o il tipo dell'atto" in f.messages[0]
        assert f.url == "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2024;9999"

    def test_date_of_the_act_that_differs_from_normattiva(self, source):
        f = _one("Vale l'art. 13 della legge 25 settembre 2025, n. 132.", source)
        assert f.status is ACT_UNCLEAR
        assert any(
            "datato 25/09/2025; su Normattiva è «LEGGE 23 settembre 2025, n. 132»" in m
            for m in f.messages
        )
        assert f.article is not None  # the article is checked all the same

    def test_unreachable_api(self, source, api):
        api.down = True
        f = _one("Vale l'art. 13 della legge 132/2025.", source)
        assert f.status is UNAVAILABLE and f.status.group == "controllare"
        assert f.messages[0].startswith("Normattiva non ha risposto")

    def test_stale_answer_is_declared(self, tmp_path, api):
        NormattivaTextSource(tmp_path, api).article(AI_LAW, "art:13", TODAY)
        path = tmp_path / "stato_legge_2025_132_art_13.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["answers"][0]["fetched_at"] = "2026-11-01T08:00:00+00:00"
        path.write_text(json.dumps(data), encoding="utf-8")
        api.down = True
        source = OfficialSources(NoEuSource(), NormattivaTextSource(tmp_path, api))  # type: ignore[arg-type]
        check = check_text("Vale l'art. 13 della legge 132/2025.", source, today=TODAY)
        [f] = check.findings
        assert f.status is VALID
        assert any("usato il testo letto il 01/11/2026" in m for m in f.messages)
        [entry] = build_lock(check)["dipendenze"]
        assert entry["consolidato_al"] == "2026-11-01"

    def test_repeal_already_published(self, source):
        f = _one("Il reddito di lavoro dipendente è definito dall'art. 51 TUIR.", source)
        assert f.status is SCHEDULED and f.status.group == "controllare"
        assert any(
            m.startswith("Dal 01/01/2027 l'art. 51 risulta abrogato")
            and "PROVVEDIMENTO ABROGATO DAL D.LGS. 19 GIUGNO 2026, N. 117" in m
            for m in f.messages
        )
        assert f.article is not None and f.version is not None

    def test_ruling_of_the_constitutional_court_in_the_notes(self, source):
        f = _one("Si applica l'art. 18 dello Statuto dei lavoratori.", source)
        assert f.status is RULING and f.status.group == "controllare"
        assert any("n. 59/2021, n. 125/2022" in m for m in f.messages)

    def test_article_given_in_part(self, tmp_path):
        commi = "".join(
            f'<div class="art-comma-div-akn"><span class="comma-num-akn">{n}. </span>'
            f'<span class="art_text_in_comma">Testo del comma numero {n} della legge.</span></div>'
            for n in range(1, 101)
        )
        act = {
            **_fixture("legge-132-2025_art13.json")["body"]["data"]["atto"],
            "articoloHtml": '<div class="bodyTesto"><h2 class="article-num-akn">Art. 1</h2>'
            f'<div class="art-commi-div-akn">{commi}</div></div>',
        }

        class Budget:
            def article(self, urn: str) -> dict[str, Any]:
                return act

        source = OfficialSources(NoEuSource(), NormattivaTextSource(tmp_path, Budget()))  # type: ignore[arg-type]
        f = _one("Vale l'art. 1, comma 54, della legge 197/2022.", source)
        assert f.status is VALID
        f = _one("Vale l'art. 1, comma 184, della legge 197/2022.", source)
        assert f.status is PARTIAL and f.status.group == "controllare"
        assert "il comma 184 non è stato letto" in f.messages[0]
        quoted = "L'art. 1 della legge 197/2022 dice «le parole di un comma che non è stato letto»."
        assert _one(quoted, source).status is PARTIAL

    def test_acts_the_check_does_not_read(self, source):
        f = _one("Si veda l'art. 3 della legge regionale Lombardia 11 marzo 2005, n. 12.", source)
        assert f.status is NOT_COVERED and f.status.group == "non_coperto"
        assert f.messages == [
            "Le leggi regionali non sono tra gli atti che il controllo legge su Normattiva: da "
            "controllare a mano."
        ]
        assert f.url is None
        assert _one("Vale l'art. 4 del D.M. 10 marzo 2014, n. 55.", source).status is NOT_COVERED
        annex = _one("Si veda l'Allegato IV del d.lgs. 81/2008.", source)
        assert annex.status is NOT_COVERED and "non gli allegati" in annex.messages[0]

    def test_a_source_without_italian_law_leaves_italian_references_unchecked(self):
        f = _one("Resta fermo l'art. 13 del d.lgs. 196/2003.", FakeSource())  # type: ignore[arg-type]
        assert f.status is NOT_COVERED
        assert f.messages == ["Questa fonte non legge i testi italiani: da controllare a mano."]

    def test_eu_and_italian_references_in_one_document(self, tmp_path, api):
        source = OfficialSources(FakeSource(), NormattivaTextSource(tmp_path, api))
        text = (
            "L'art. 50, par. 5, AI Act si applica all'assistente.\n"
            "Per i professionisti vale l'art. 13 della legge 132/2025.\n"
        )
        check = check_text(text, source, document="nota.txt", today=TODAY)
        assert [f.status for f in check.findings] == [VALID, VALID]
        assert [d["fonte"] for d in build_lock(check)["dipendenze"]] == ["eurlex", "normattiva"]


# ─── Lock file and re-check ──────────────────────────────────────────


class FixedDate(date):
    @classmethod
    def today(cls) -> FixedDate:
        return cls(2026, 11, 11)


class TestItalianLock:
    TEXT = (
        "Vale l'art. 13, comma 1, della legge 132/2025 e, per il lavoro, l'art. 13, comma 2, "
        "della legge 23 settembre 2025, n. 132. Si veda anche l'art. 2-ter del Codice privacy."
    )

    def test_lock_entries_of_italian_provisions(self, source):
        check = check_text(self.TEXT, source, document="nota.txt", today=TODAY)
        lock = build_lock(check)
        assert [(d["atto"], d["articolo"]) for d in lock["dipendenze"]] == [
            (AI_LAW, "Art. 13"),
            (PRIVACY, "Art. 2-ter"),
        ]
        entry = lock["dipendenze"][0]
        assert list(entry) == [
            "fonte",
            "atto",
            "nome",
            "versione",
            "consolidato_al",
            "articolo",
            "chiave",
            "lingua",
            "impronta",
            "testo",
            "riferimenti",
        ]
        assert entry["fonte"] == "normattiva" and entry["nome"] == "Legge 132/2025"
        assert entry["versione"] == entry["consolidato_al"] == TODAY
        assert entry["chiave"] == "art:13" and entry["lingua"] == "IT"
        assert entry["impronta"] == fingerprint(entry["testo"])
        assert entry["testo"].startswith("Art. 13\nDisposizioni in materia di professioni")
        assert len(entry["riferimenti"]) == 2
        json.dumps(lock)

    def test_recheck_unchanged(self, source, monkeypatch):
        monkeypatch.setattr(check_module, "date", FixedDate)
        lock = build_lock(check_text(self.TEXT, source, today=TODAY))
        changes = recheck(lock, source)
        assert [c.code for c in changes] == ["invariato", "invariato"]
        assert changes[0].message == "Art. 13 è uguale nel testo vigente al 11/11/2026."
        assert changes[0].version is not None and "normattiva.it" in changes[0].version.url("IT")

    def test_recheck_changed_removed_and_unreachable(self, source, api, tmp_path, monkeypatch):
        monkeypatch.setattr(check_module, "date", FixedDate)
        lock = build_lock(check_text(self.TEXT, source, today=TODAY))
        # A week later law 132/2025 has a new art. 13 and art. 2-ter is repealed.
        [wording] = api.wordings[(AI_LAW, "art13")]
        wording["articoloDataFineVigenza"] = "20261114"
        api.wordings[(AI_LAW, "art13")].append(
            {
                **wording,
                "articoloHtml": wording["articoloHtml"].replace("al solo esercizio", "anche"),
                "articoloDataInizioVigenza": "20261115",
                "articoloDataFineVigenza": "99999999",
            }
        )
        [in_force] = [
            w
            for w in api.wordings[(PRIVACY, "art2ter")]
            if w["articoloDataFineVigenza"] == "99999999"
        ]
        in_force["articoloDataFineVigenza"] = "20261114"
        api.wordings[(PRIVACY, "art2ter")].append(
            {
                **_fixture("dlgs-196-2003_art13_repealed.json")["body"]["data"]["atto"],
                "articoloHtml": _html("dlgs-196-2003_art13_repealed.json").replace(
                    "Art. 13", "Art. 2-ter"
                ),
                "articoloDataInizioVigenza": "20261115",
            }
        )

        class NextWeek(date):
            @classmethod
            def today(cls) -> NextWeek:
                return cls(2026, 11, 18)

        monkeypatch.setattr(check_module, "date", NextWeek)
        later = OfficialSources(NoEuSource(), NormattivaTextSource(tmp_path / "later", api))  # type: ignore[arg-type]
        changes = {c.entry["articolo"]: c for c in recheck(lock, later)}
        changed = changes["Art. 13"]
        assert changed.code == "cambiato" and "in vigore dal 15/11/2026" in changed.message
        assert changed.before is not None and "al solo esercizio" in changed.before
        assert changed.after is not None and "al solo esercizio" not in changed.after
        removed = changes["Art. 2-ter"]
        assert (
            removed.code == "soppresso" and "non è più in vigore dal 15/11/2026" in removed.message
        )
        assert (
            "ARTICOLO ABROGATO" in removed.message
            and removed.before == lock["dipendenze"][1]["testo"]
        )
        html = render_recheck_html(lock, list(changes.values()), "2026-11-18")
        assert "Testo vigente su Normattiva" in html and "<del>" in html

        api.down = True
        offline = OfficialSources(NoEuSource(), NormattivaTextSource(tmp_path / "off", api))  # type: ignore[arg-type]
        assert [c.code for c in recheck(lock, offline)] == ["non_disponibile", "non_disponibile"]

    def test_recheck_says_when_a_change_is_already_published(self, source, monkeypatch):
        monkeypatch.setattr(check_module, "date", FixedDate)
        lock = build_lock(check_text("Vale l'art. 51 TUIR.", source, today=TODAY))
        [change] = recheck(lock, source)
        assert change.code == "invariato"
        assert "Dal 01/01/2027 è pubblicata una modifica non ancora in vigore." in change.message

    def test_recheck_needs_a_source_that_reads_italian_law(self, source):
        lock = build_lock(check_text(self.TEXT, source, today=TODAY))
        changes = recheck(lock, FakeSource())  # type: ignore[arg-type]
        assert [c.code for c in changes] == ["non_disponibile", "non_disponibile"]

    def test_a_lock_entry_without_fonte_is_an_eu_provision(self, source):
        old = build_lock(check_text("L'art. 50 dell'AI Act.", FakeSource()))  # type: ignore[arg-type]
        assert old["dipendenze"][0]["fonte"] == "eurlex"
        del old["dipendenze"][0]["fonte"]  # as written before Italian law was read
        mixed = OfficialSources(FakeSource(), source.italian)
        assert [c.code for c in recheck(old, mixed)] == ["invariato"]


# ─── Report and command line ─────────────────────────────────────────

NOTE = (
    "Nota al cliente\n"
    "L'art. 13 della legge 132/2025 dispone che «l'utilizzo di sistemi di intelligenza "
    "artificiale nelle professioni intellettuali è finalizzato al solo esercizio delle attività "
    "strumentali e di supporto all'attività professionale».\n"
    "L'informativa è resa ai sensi dell'art. 13 del d.lgs. 196/2003.\n"
    "Per il Comune vale l'art. 3 della legge regionale Lombardia 11 marzo 2005, n. 12.\n"
    "L'art. 24 del d.lgs. 138/2024 rinvia alle modalità «di cui agli articoli 30, 31 e 33, alla "
    "gestione dei rischi posti alla sicurezza».\n"
)


class TestItalianReport:
    def test_html_report(self, source):
        check = check_text(NOTE, source, document="nota.txt", today=TODAY)
        assert [f.status for f in check.findings] == [VERIFIED, MISSING, NOT_COVERED, ALTERED]
        html = render_html(check, "nota.norma-lock.json")
        assert "sui testi vigenti di Normattiva" in html and "EUR-Lex. Data" not in html
        # Cards like the EU ones, with the link to the article on Normattiva.
        assert "Citazione diversa dal testo ufficiale" in html and "<del>33,</del>" in html
        assert (
            f'<a href="https://www.normattiva.it/uri-res/N2Ls?{PRIVACY}~art13!vig={TODAY}">'
            "Testo vigente su Normattiva</a>" in html
        )
        assert "Ultimo testo: testo in vigore dal 13/07/2011 al 18/09/2018" in html
        assert f"{AI_LAW}~art13!vig={TODAY}" in html  # the row of the verified quote links too
        # What is not read is listed with its reason.
        assert "Atti che il controllo non legge" in html
        assert "Le leggi regionali non sono tra gli atti" in html
        # Normattiva's texts are not official, and the licence asks for the credit.
        assert "non hanno carattere di ufficialità" in html
        assert "prevale in caso di discordanza" in html
        assert "https://creativecommons.org/licenses/by/4.0/deed.it" in html
        assert "https://dati.normattiva.it/" in html
        assert "2 disposizioni registrate" in html

    def test_summary(self, source):
        check = check_text(NOTE, source, document="nota.txt", today=TODAY)
        lines = summary_lines(check)
        assert lines[1] == "2 da correggere, 0 da controllare, 1 a posto, 1 non letti."
        assert any("D.Lgs. 196/2003 (Codice privacy), art. 13: Non esiste" in ln for ln in lines)

    def test_a_report_of_eu_law_only_still_names_eur_lex(self):
        check = check_text("Vedi l'art. 50 dell'AI Act.", FakeSource(), today=TODAY)  # type: ignore[arg-type]
        assert "sui testi consolidati di EUR-Lex. Data" in render_html(check)


def test_command_line_with_italian_law(tmp_path, capsys, api):
    script = Path(__file__).resolve().parent.parent / "scripts" / "check_document.py"
    spec = importlib.util.spec_from_file_location("check_document_it", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = tmp_path / "nota.txt"
    document.write_text(NOTE, encoding="utf-8")
    italian = NormattivaTextSource(tmp_path / "cache" / "normattiva", api)
    with (
        patch.object(module, "default_source", return_value=OfficialSources(FakeSource(), italian)),
        patch.object(check_module, "date", FixedDate),
    ):
        assert module.main([str(document), "--data", "2026-03-15"]) == 0
        lock_path = tmp_path / "nota.norma-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        assert [d["fonte"] for d in lock["dipendenze"]] == ["normattiva", "normattiva"]
        assert module.main(["--ricontrolla", str(lock_path)]) == 0
    out = capsys.readouterr().out
    assert "Citazione diversa dal testo ufficiale" in out
    assert "- Legge 132/2025, Art. 13: invariato" in out
    assert (tmp_path / "nota.controllo.html").exists()
    assert (tmp_path / "nota.ricontrollo.html").exists()
    help_text = module.main.__doc__ or module.__doc__ or ""
    assert "Normattiva" in help_text
