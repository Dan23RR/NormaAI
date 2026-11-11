"""scripts/verify_site_sources.py: the offline parts.

No network: the texts are small fixtures shaped like what Normattiva, CELLAR
and a PDF give. The checks that matter are the refusals: a changed number, the
right words in the wrong article or paragraph, words that are only in an
editorial note, an article in force from another date.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_site_sources.py"
REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "lib"
    / "verification"
    / "sources.json"
)


@pytest.fixture(scope="module")
def vss():
    spec = importlib.util.spec_from_file_location("verify_site_sources", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the annotations of a module through sys.modules.
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ARTICLE_HTML = """
<div class="bodyTesto">
  <h2 class="article-num-akn" id="art_25">Art. 25</h2>
  <div class="article-heading-akn">Obblighi in materia di notifica di incidente</div>
  <div class="art-commi-div-akn">
    <div class="art-comma-div-akn">
      <span class="comma-num-akn">1. </span><span class="art_text_in_comma">I soggetti notificano
      al CSIRT Italia ogni incidente, ai sensi dell'<a href="http://example.invalid/x">articolo 30</a>.
      <br></span>
    </div>
    <div class="art-comma-div-akn">
      <span class="comma-num-akn">2. </span><span class="art_text_in_comma">I soggetti trasmettono,
      comunque entro 24 ore da quando sono venuti a conoscenza dell'incidente, una pre-notifica.<br></span>
    </div>
    <div class="art-comma-div-akn">
      <span class="comma-num-akn">2-bis. </span><span class="art_text_in_comma">
        <div class="ins-akn" eId="ins_1">((La relazione finale e' trasmessa entro un mese.))</div>
      </span>
    </div>
  </div>
  <div class="note-akn">Note all'art. 25: <br> - Si riporta il testo: «entro 72 ore dalla
    conoscenza dell'incidente il soggetto invia una notifica completa».</div>
  <div class="art_aggiornamento-akn"><div class="art_aggiornamento_title-akn">AGGIORNAMENTO (1)</div>
    Il D.L. ha disposto che il termine e' di novanta giorni.</div>
</div>
"""

ANNEX_LINES = [
    "ALLEGATO II",
    "Altri settori critici",
    "=====================================================================",
    "|    Settore     |   Sottosettore    |  Tipologia di soggetto  |",
    "+================+===================+=========================+",
    "|1. Servizi      |                   |Fornitori di servizi     |",
    "|postali e di    |                   |postali                  |",
    "|corriere        |                   |                         |",
    "+----------------+-------------------+-------------------------+",
    "|5. Fabbricazione|a) Fabbricazione di|Soggetti che fabbricano  |",
    "|                |dispositivi medici |dispositivi medici       |",
    "|                +-------------------+-------------------------+",
    "|                |b) Fabbricazione di|Imprese della divisione  |",
    "|                |computer           |26                       |",
    "+----------------+-------------------+-------------------------+",
]


def test_normattiva_text_keeps_the_provision_and_drops_notes(vss):
    text = vss.normattiva_text(ARTICLE_HTML)
    lines = text.split("\n")
    assert "Art. 25" in lines
    # Inline links leave no stray space before the punctuation.
    assert "ai sensi dell'articolo 30." in text
    # Each paragraph starts its own line with its number, so its number can be read back.
    assert any(line.startswith("1. I soggetti notificano") for line in lines)
    assert any(line.startswith("2. I soggetti trasmettono") for line in lines)
    # Marks of amended wording are removed, the wording stays.
    assert "((" not in text and "))" not in text
    assert "La relazione finale e' trasmessa entro un mese." in text
    # Editorial notes and amendment notes are not the provision.
    assert "72 ore" not in text
    assert "novanta giorni" not in text


def test_html_lines_closes_a_skipped_element_at_its_own_end_tag(vss):
    lines = vss.html_lines(
        '<div><div class="note-akn"><p>nota <span>interna</div><p>dopo la nota</p></div>',
        ("note-akn",),
    )
    assert lines == ["dopo la nota"]


def test_table_columns_reads_each_column_top_to_bottom(vss):
    plain, columns = vss.table_columns(ANNEX_LINES)
    assert plain == ["ALLEGATO II", "Altri settori critici"]
    assert columns[0] == "Settore 1. Servizi postali e di corriere 5. Fabbricazione"
    assert columns[1] == (
        "Sottosettore a) Fabbricazione di dispositivi medici b) Fabbricazione di computer"
    )


def test_split_articles_cuts_at_article_headings(vss):
    text = "Determinazione\nIL DIRETTORE\nArticolo 1\n(Termini)\n1. Primo.\nArticolo 2\n1. Secondo."
    assert vss.split_articles(text) == [
        ("", "Determinazione\nIL DIRETTORE"),
        ("Art. 1", "Articolo 1\n(Termini)\n1. Primo."),
        ("Art. 2", "Articolo 2\n1. Secondo."),
    ]


def _entry(vss, **fields):
    base = {
        "id": "x-1",
        "kind": "normattiva",
        "act": "urn:nir:stato:decreto.legislativo:2024-09-04;138",
        "article": "Art. 25",
        "paragraph": "2",
        "lang": "IT",
        "excerpt": "comunque entro 24 ore da quando sono venuti a conoscenza dell'incidente, una pre-notifica",
    }
    return vss.Entry(**{**base, **fields})


def test_normattiva_urn_asks_for_the_text_in_force_on_a_date(vss):
    on = "2026-11-11"
    assert vss.normattiva_urn(_entry(vss), on) == (
        "urn:nir:stato:decreto.legislativo:2024-09-04;138~art25!vig=2026-11-11"
    )
    bis = _entry(vss, act="urn:nir:stato:decreto.legislativo:1997-05-26;152", article="Art. 1-bis")
    assert vss.normattiva_urn(bis, on).endswith(";152~art1bis!vig=2026-11-11")
    annex = _entry(vss, article="Allegato II", annex=2, paragraph="")
    assert vss.normattiva_urn(annex, on).endswith(";138:2~art1!vig=2026-11-11")


def _reading(vss, **fields):
    base = {
        "version": "vigente al 2026-11-11",
        "version_label": "testo vigente al 2026-11-11 (Normattiva)",
        "articles": [("Art. 25", vss.normattiva_text(ARTICLE_HTML))],
        "in_force_from": "2024-10-16",
    }
    return vss.Reading(**{**base, **fields})


def test_check_reading_verifies_a_literal_excerpt_in_its_paragraph(vss):
    outcome = vss.check_reading(_entry(vss), _reading(vss))
    assert outcome["status"] == "verified"
    assert outcome["official_quote"].startswith("comunque entro 24 ore")
    assert outcome["in_force_from"] == "2024-10-16"


def test_check_reading_refuses_a_changed_number(vss):
    entry = _entry(vss, excerpt=_entry(vss).excerpt.replace("24 ore", "48 ore"))
    outcome = vss.check_reading(entry, _reading(vss))
    assert outcome["status"] == "failed"
    assert outcome["official_quote"] is None


def test_check_reading_refuses_the_wrong_paragraph_and_the_wrong_article(vss):
    wrong_paragraph = vss.check_reading(_entry(vss, paragraph="1"), _reading(vss))
    assert wrong_paragraph["status"] == "failed"
    assert "paragrafo 2" in wrong_paragraph["detail"]

    two_articles = _reading(
        vss,
        articles=[
            ("Art. 24", "Art. 24\n1. I soggetti adottano misure adeguate e proporzionate."),
            ("Art. 25", vss.normattiva_text(ARTICLE_HTML)),
        ],
    )
    wrong_article = vss.check_reading(_entry(vss, article="Art. 24"), two_articles)
    assert wrong_article["status"] == "failed"
    assert "Art. 25" in wrong_article["detail"]


def test_check_reading_does_not_find_words_that_are_only_in_a_note(vss):
    entry = _entry(
        vss,
        paragraph="",
        excerpt="entro 72 ore dalla conoscenza dell'incidente il soggetto invia una notifica completa",
    )
    assert vss.check_reading(entry, _reading(vss))["status"] == "failed"


def test_check_reading_checks_the_date_the_article_is_in_force_from(vss):
    entry = _entry(vss, in_force_from="2026-10-23")
    assert vss.check_reading(entry, _reading(vss))["status"] == "failed"
    assert vss.check_reading(entry, _reading(vss, in_force_from="2026-10-23"))["status"] == (
        "verified"
    )
    ended = _reading(vss, in_force_from="2026-10-23", in_force_to="2027-01-01")
    assert vss.check_reading(entry, ended)["status"] == "failed"


def test_build_record_keeps_an_earlier_verification_through_an_outage(vss):
    entry = _entry(vss)
    verified = vss.build_record(
        entry, vss.check_reading(entry, _reading(vss)), "2026-11-11", previous=None
    )
    assert verified["status"] == "verified" and verified["verified_on"] == "2026-11-11"

    outage = {"status": "unreachable", "detail": "fonte non raggiungibile: timeout"}
    kept = vss.build_record(entry, outage, "2026-11-18", previous=verified)
    assert kept["status"] == "verified"
    assert kept["verified_on"] == "2026-11-11"
    assert kept["checked_on"] == "2026-11-18"
    assert kept["official_quote"] == verified["official_quote"]

    # A changed entry is a new claim: the old verification does not cover it.
    changed = _entry(vss, excerpt="comunque entro 24 ore da quando sono venuti a conoscenza")
    dropped = vss.build_record(changed, outage, "2026-11-18", previous=verified)
    assert dropped["status"] == "unreachable" and dropped["verified_on"] is None

    # A failure is never papered over by an old success.
    failed = vss.build_record(
        entry, {"status": "failed", "detail": "x"}, "2026-11-18", previous=verified
    )
    assert failed["status"] == "failed" and failed["verified_on"] is None


def test_load_registry_refuses_malformed_entries(vss, tmp_path):
    def registry(**fields):
        path = tmp_path / "sources.json"
        entry = {
            "id": "ok-1",
            "kind": "eurlex",
            "act": "32024R1689",
            "article": "Art. 50",
            "paragraph": "1",
            "lang": "IT",
            "excerpt": "siano informate del fatto di stare interagendo con un sistema di IA",
        }
        path.write_text(json.dumps({"sources": [{**entry, **fields}]}), encoding="utf-8")
        return path

    assert [e.id for e in vss.load_registry(registry())] == ["ok-1"]
    for bad in (
        {"id": "Not Valid"},
        {"kind": "blog"},
        {"act": "AI Act"},
        {"article": "da qualche parte"},
        {"excerpt": ""},
        {"in_force_from": "2026-10-23"},  # only for texts read on Normattiva
        {"kind": "document", "url": "https://example.com/determina.pdf"},
        {"kind": "document", "url": "http://www.acn.gov.it/determina.pdf"},
    ):
        with pytest.raises(ValueError):
            vss.load_registry(registry(**bad))


def test_the_committed_registry_is_well_formed(vss):
    entries = vss.load_registry(REGISTRY)
    assert len(entries) > 50
    assert len({e.id for e in entries}) == len(entries)
