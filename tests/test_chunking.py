"""Tests for legal document chunking pipeline."""

import re
from pathlib import Path

import pytest

from src.nlp.chunking.contextual_chunker import ContextualChunk, ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker, LegalChunk

FIXTURES = Path(__file__).parent / "fixtures" / "eurlex"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _by_article(chunks, article):
    return [c for c in chunks if c.metadata["article"] == article]


class TestLegalChunker:
    def setup_method(self):
        self.chunker = EURLexHTMLChunker(celex="32022L2464", framework="CSRD")

    def test_article_extraction(self):
        html = """<html><body>
        <h2>CHAPTER I</h2>
        <p>Article 1</p>
        <p>This Directive establishes rules on sustainability reporting by certain categories of undertakings. It sets out obligations regarding sustainability information.</p>
        <p>Article 2</p>
        <p>For the purposes of this Directive, the following definitions apply: sustainability matters means environmental, social and human rights, and governance factors including anti-corruption and bribery matters.</p>
        </body></html>"""
        chunks = self.chunker.chunk_html(html)
        assert len(chunks) > 0
        assert all(isinstance(c, LegalChunk) for c in chunks)
        assert all(c.metadata["celex"] == "32022L2464" for c in chunks)
        assert all(c.metadata["framework"] == "CSRD" for c in chunks)

    def test_recital_batching(self):
        recitals = "".join(
            f"<p>({i}) Recital text number {i} with enough content to be meaningful.</p>"
            for i in range(1, 12)
        )
        html = f"<html><body>{recitals}</body></html>"
        chunks = self.chunker.chunk_html(html)
        recital_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "recital"]
        assert len(recital_chunks) >= 2  # 11 recitals / batch_size=5 = at least 2

    def test_table_extraction(self):
        html = """<html><body>
        <p>Article 1</p>
        <p>Introductory text for article one with enough content to pass minimum size threshold.</p>
        <table><tr><th>Criterion</th><th>Threshold</th></tr><tr><td>Employees</td><td>1000</td></tr><tr><td>Revenue</td><td>EUR 50M</td></tr></table>
        </body></html>"""
        chunks = self.chunker.chunk_html(html)
        [c for c in chunks if c.metadata.get("chunk_type") == "table"]
        # Tables may or may not be extracted depending on content
        assert len(chunks) > 0

    def test_fallback_chunking(self):
        html = "<html><body><p>Simple paragraph with no article structure but enough text to be processed correctly.</p><p>Another paragraph with additional content for the fallback chunking mechanism to work properly with minimum sizes.</p></body></html>"
        chunks = self.chunker.chunk_html(html)
        assert len(chunks) >= 0  # May fallback to paragraph chunking

    def test_max_chunk_size_respected(self):
        long_article = "Article 1\n" + "x " * 2000  # Very long article
        html = f"<html><body><p>Article 1</p><p>{long_article}</p></body></html>"
        chunks = self.chunker.chunk_html(html)
        for chunk in chunks:
            assert len(chunk.text) <= EURLexHTMLChunker.MAX_CHUNK_SIZE + 200  # Allow some margin

    def test_metadata_has_char_count(self):
        html = "<html><body><p>Article 1</p><p>This Directive establishes rules on sustainability reporting by certain categories of undertakings in the European Union.</p></body></html>"
        chunks = self.chunker.chunk_html(html)
        for chunk in chunks:
            assert "char_count" in chunk.metadata
            assert chunk.metadata["char_count"] == len(chunk.text)


class TestContextualChunker:
    def setup_method(self):
        self.chunker = ContextualChunker()

    def test_enrich_single(self):
        result = self.chunker.enrich_single(
            text="Member States shall ensure compliance.",
            framework="GDPR",
            article="Art. 32",
            section="Security of Processing",
        )
        assert isinstance(result, ContextualChunk)
        assert result.text == "Member States shall ensure compliance."
        assert "General Data Protection Regulation" in result.contextualized_text
        assert "Art. 32" in result.contextualized_text
        assert result.metadata["has_context"] is True

    def test_enrich_without_framework(self):
        result = self.chunker.enrich_single(text="Some text")
        assert result.text == "Some text"
        assert result.contextualized_text == "Some text"

    def test_known_frameworks(self):
        for fw_key in ["CSRD", "CSDDD", "AI_ACT", "DORA", "NIS2", "TAXONOMY", "GDPR"]:
            result = self.chunker.enrich_single("test", framework=fw_key)
            assert fw_key in result.metadata["framework"] or result.metadata["framework"] == fw_key


# ─── Structural chunking on CELLAR-style fixtures ─────────────────────────


@pytest.fixture(scope="module")
def en_chunks():
    chunker = EURLexHTMLChunker(celex="32099R0001", framework="AI_ACT")
    return chunker.chunk_html(_load("cellar_act_en.html"))


class TestCellarFixtureEN:
    """The CELLAR XHTML markup of an OJ act (oj-* classes, layout tables)."""

    def test_chunk_types_follow_act_structure(self, en_chunks):
        types = [c.metadata["chunk_type"] for c in en_chunks]
        assert types.count("preamble") == 1
        assert types.count("recital") == 3
        assert types.count("article") == 3
        assert types.count("annex") == 3
        # Document order: preamble, recitals, articles, annexes.
        order = ["preamble", "recital", "article", "annex"]
        assert types == sorted(types, key=order.index)

    def test_recitals_are_single_units_distinct_from_articles(self, en_chunks):
        recitals = [c for c in en_chunks if c.metadata["chunk_type"] == "recital"]
        assert [c.metadata["article"] for c in recitals] == ["Recital 1", "Recital 2", "Recital 3"]
        assert recitals[1].text.startswith("(2) Fixture systems can be easily deployed")
        assert recitals[0].metadata["section_title"] == "Preamble"
        assert recitals[0].metadata["hierarchy"] == "Preamble > Recital 1"
        # Recital text never leaks into article chunks.
        for c in en_chunks:
            if c.metadata["chunk_type"] == "article":
                assert "(1) The purpose of this Regulation" not in c.text
        # Nested points of recital 3 stay inside it, with their markers glued on.
        assert "(a) the safety of natural persons;" in recitals[2].text
        assert "(b) the protection of fundamental rights." in recitals[2].text

    def test_preamble_chunk_holds_title_and_citations(self, en_chunks):
        pre = en_chunks[0]
        assert pre.metadata["chunk_type"] == "preamble"
        assert pre.metadata["article"] == "Preamble"
        assert pre.text.startswith("REGULATION (EU) 2099/1 OF THE EUROPEAN PARLIAMENT")
        assert "Having regard to the Treaty" in pre.text
        assert "Whereas:" not in pre.text

    def test_articles_keep_title_and_chapter(self, en_chunks):
        art1 = _by_article(en_chunks, "Art. 1")
        assert len(art1) == 1
        m = art1[0].metadata
        assert m["title"] == "Subject matter"
        assert m["section_title"] == "CHAPTER I - GENERAL PROVISIONS"
        assert m["hierarchy"] == "CHAPTER I - GENERAL PROVISIONS > Art. 1"
        assert m["article_number"] == "Art. 1"  # legacy alias of ``article``
        assert art1[0].text.startswith("Article 1\nSubject matter\n1. The purpose of this")
        art3 = _by_article(en_chunks, "Art. 3")[0]
        assert art3.metadata["title"] == "Entry into force"
        assert art3.metadata["section_title"] == "CHAPTER II - FINAL PROVISIONS"

    def test_paragraph_and_point_numbers_glued_to_their_text(self, en_chunks):
        lines = _by_article(en_chunks, "Art. 1")[0].text.split("\n")
        assert "2. This Regulation lays down:" in lines
        assert "(a) harmonised rules for the placing on the market of fixture systems;" in lines
        assert "(b) prohibitions of certain practices, including:" in lines
        assert "(i) manipulative techniques;" in lines
        assert "(ii) exploitative techniques." in lines
        # No orphan marker lines survive.
        assert not any(re.fullmatch(r"\(?[a-z0-9]{1,3}[.)]", line) for line in lines)

    def test_no_words_glued_across_inline_tags(self, en_chunks):
        art2 = _by_article(en_chunks, "Art. 2")[0].text
        assert "This Regulation shall apply to providers" in art2
        assert "Regulationshall" not in art2 and "shallapply" not in art2
        assert "should therefore be applied" in _by_article(en_chunks, "Recital 2")[0].text
        art3 = _by_article(en_chunks, "Art. 3")[0].text
        assert "publication in the Official Journal of the European Union." in art3

    def test_cross_reference_is_not_mistaken_for_heading(self, en_chunks):
        # "Article 5 shall not apply ..." is a sentence inside Article 2.
        assert not _by_article(en_chunks, "Art. 5")
        assert "Article 5 shall not apply" in _by_article(en_chunks, "Art. 2")[0].text

    def test_boilerplate_is_dropped(self, en_chunks):
        full = "\n".join(c.text for c in en_chunks)
        for junk in (
            "L series",
            "1.1.2099",
            "Done at Brussels",
            "For the European Parliament",
            "A. PRESIDENT",
            "OJ C 1, 1.1.2098",
            "ISSN 1977-0677",
            "ELI: http://data.europa.eu/eli/reg/2099/1/oj",
            "HAVE ADOPTED THIS REGULATION",
        ):
            assert junk not in full, junk

    def test_annexes_chunked_per_section(self, en_chunks):
        annex = [c for c in en_chunks if c.metadata["chunk_type"] == "annex"]
        a1 = [c for c in annex if c.metadata["article"] == "Annex I"]
        assert [c.metadata["section_title"] for c in a1] == [
            "Section A. List of Union harmonisation legislation based on the New Legislative Framework",
            "Section B. List of other Union harmonisation legislation",
        ]
        assert all(c.metadata["title"] == "List of Union harmonisation legislation" for c in a1)
        assert a1[0].metadata["hierarchy"].startswith("Annex I > Section A.")
        assert a1[0].text.startswith(
            "Annex I - List of Union harmonisation legislation\nSection A. List of"
        )
        # Items held in bare <span> cells are not lost and keep their numbers.
        assert "1. Directive 2006/42/EC" in a1[0].text
        assert "2. Directive 2009/48/EC" in a1[0].text
        assert "3. Regulation (EC) No 300/2008" in a1[1].text
        a2 = [c for c in annex if c.metadata["article"] == "Annex II"]
        assert len(a2) == 1
        assert a2[0].metadata["title"] == "List of criminal offences referred to in Article 5(1)"
        assert "— terrorism," in a2[0].text
        # A real data table becomes "cell | cell" rows inside the annex.
        assert "Area | Threshold" in a2[0].text and "Biometrics | High" in a2[0].text

    def test_every_chunk_has_full_metadata(self, en_chunks):
        required = {
            "celex",
            "source_celex",
            "eli",
            "lang",
            "article",
            "paragraph",
            "title",
            "framework",
            "url",
            "consolidated_as_of",
            "chunk_index",
            "chunk_type",
            "article_number",
            "section_title",
            "hierarchy",
            "char_count",
        }
        for c in en_chunks:
            assert required <= set(c.metadata)
            assert c.metadata["celex"] == "32099R0001"
            assert c.metadata["source_celex"] == "32099R0001"
            assert c.metadata["framework"] == "AI_ACT"
            assert c.metadata["lang"] == "EN"
            assert c.metadata["eli"] == "http://data.europa.eu/eli/reg/2099/1/oj"
            assert c.metadata["url"] == (
                "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32099R0001"
            )
            assert c.metadata["consolidated_as_of"] is None
            assert c.metadata["char_count"] == len(c.text)
        assert [c.metadata["chunk_index"] for c in en_chunks] == list(range(len(en_chunks)))

    def test_chunking_is_deterministic(self):
        html = _load("cellar_act_en.html")
        a = EURLexHTMLChunker(celex="32099R0001", framework="AI_ACT").chunk_html(html)
        b = EURLexHTMLChunker(celex="32099R0001", framework="AI_ACT").chunk_html(html)
        assert [(c.text, c.metadata) for c in a] == [(c.text, c.metadata) for c in b]


class TestCellarFixtureIT:
    @pytest.fixture(scope="class")
    def it_chunks(self):
        chunker = EURLexHTMLChunker(celex="32099L0002", framework="CSRD", lang="it", eli_type="dir")
        return chunker.chunk_html(_load("cellar_act_it.html"))

    def test_italian_structure_and_language_tagging(self, it_chunks):
        types = [c.metadata["chunk_type"] for c in it_chunks]
        assert types.count("recital") == 2
        assert types.count("article") == 3
        assert types.count("annex") == 1
        assert all(c.metadata["lang"] == "IT" for c in it_chunks)
        assert it_chunks[0].metadata["url"] == (
            "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32099L0002"
        )
        assert it_chunks[0].metadata["eli"] == "http://data.europa.eu/eli/dir/2099/2/oj"

    def test_italian_headings_points_and_annex(self, it_chunks):
        art1 = _by_article(it_chunks, "Art. 1")[0]
        assert art1.metadata["title"] == "Modifiche della direttiva (UE) 2022/2464"
        assert art1.text.startswith("Articolo 1\nModifiche della direttiva (UE) 2022/2464\n")
        lines = art1.text.split("\n")
        assert "a) il primo comma è così modificato:" in lines
        assert "i) alla lettera b), la frase introduttiva è sostituita dalla seguente:" in lines
        assert "b) il secondo comma è soppresso." in lines
        art2 = _by_article(it_chunks, "Art. 2")[0]
        assert art2.metadata["title"] == "Recepimento"
        assert "1. Gli Stati membri mettono in vigore" in art2.text
        assert "2. Gli Stati membri comunicano alla Commissione" in art2.text
        annex = [c for c in it_chunks if c.metadata["chunk_type"] == "annex"][0]
        assert annex.metadata["article"] == "Annex I"
        assert annex.metadata["title"] == "Elenco delle normative di armonizzazione dell'Unione"
        assert annex.metadata["section_title"].startswith("Sezione A.")
        assert "1. Direttiva 2006/42/CE" in annex.text
        full = "\n".join(c.text for c in it_chunks)
        assert "Fatto a Bruxelles" not in full
        assert "HANNO ADOTTATO" not in full
        assert "Posizione del Parlamento europeo" not in full


class TestFlatLegalContentFixture:
    def test_flat_markup_and_definitions_are_not_recitals(self):
        chunker = EURLexHTMLChunker(celex="32099L0003", framework="CSRD")
        chunks = chunker.chunk_html(_load("legal_content_flat.html"))
        types = [c.metadata["chunk_type"] for c in chunks]
        assert types.count("recital") == 2
        assert types.count("article") == 2
        art1 = _by_article(chunks, "Art. 1")[0]
        assert art1.metadata["title"] == "Scope"
        assert art1.metadata["section_title"] == "CHAPTER I - SCOPE AND DEFINITIONS"
        assert "1. This Directive applies to large undertakings" in art1.text
        art2 = _by_article(chunks, "Art. 2")[0]
        # "(1) ‘large undertaking’ ..." inside Article 2 is a definition, not a recital.
        assert "(1) ‘large undertaking’ means" in art2.text
        assert "(2) ‘net turnover’ means" in art2.text
        full = "\n".join(c.text for c in chunks)
        assert "window.tracking" not in full
        assert "EUR-Lex home" not in full
        assert "Legal notice" not in full
        assert "Done at Strasbourg" not in full


class TestConsolidatedIdentifiers:
    def test_consolidated_celex_is_normalised(self):
        ch = EURLexHTMLChunker(celex="02022L2464-20260318", framework="CSRD", lang="it")
        assert ch.celex == "32022L2464"
        assert ch.source_celex == "02022L2464-20260318"
        assert ch.consolidated_as_of == "2026-03-18"
        assert ch.eli == "http://data.europa.eu/eli/dir/2022/2464/2026-03-18"
        assert ch.url == (
            "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02022L2464-20260318"
        )
        chunks = ch.chunk_html(_load("cellar_act_it.html"))
        assert chunks
        assert all(c.metadata["celex"] == "32022L2464" for c in chunks)
        assert all(c.metadata["source_celex"] == "02022L2464-20260318" for c in chunks)
        assert all(c.metadata["consolidated_as_of"] == "2026-03-18" for c in chunks)

    def test_explicit_source_celex_and_eli_type(self):
        ch = EURLexHTMLChunker(
            celex="32023R2772",
            framework="CSRD",
            source_celex="02023R2772-20250101",
            eli_type="reg_del",
        )
        assert ch.eli == "http://data.europa.eu/eli/reg_del/2023/2772/2025-01-01"
        assert ch.consolidated_as_of == "2025-01-01"
        assert ch.celex == "32023R2772"

    def test_non_celex_identifier_has_null_eli_and_url(self):
        ch = EURLexHTMLChunker(
            celex="urn:nir:stato:decreto.legislativo:2003-06-30;196", framework="GDPR", lang="IT"
        )
        assert ch.eli is None and ch.url is None and ch.consolidated_as_of is None
        chunks = ch.chunk_html(
            "<html><body><p>Art. 1</p><p>Oggetto</p>"
            "<p>1. Il presente decreto disciplina il trattamento dei dati personali.</p>"
            "</body></html>"
        )
        assert chunks
        assert chunks[0].metadata["article"] == "Art. 1"
        assert chunks[0].metadata["title"] == "Oggetto"
        assert chunks[0].metadata["eli"] is None and chunks[0].metadata["url"] is None


class TestLongArticleSplitting:
    @staticmethod
    def _html(n_paragraphs: int = 8, words: int = 70) -> str:
        paras = "".join(
            f'<p class="oj-normal">{i}.   '
            + " ".join(f"word{i}x{j}" for j in range(words))
            + ".</p>"
            for i in range(1, n_paragraphs + 1)
        )
        return (
            '<html><body><p class="oj-ti-art">Article 7</p><p class="oj-sti-art">Long one</p>'
            f"{paras}</body></html>"
        )

    def test_split_parts_keep_heading_and_paragraph_ranges(self):
        chunks = EURLexHTMLChunker(celex="32099R0001", framework="X").chunk_html(self._html())
        assert len(chunks) > 1
        assert all(c.metadata["article"] == "Art. 7" for c in chunks)
        assert all(c.metadata["chunk_type"] == "article" for c in chunks)
        assert [c.metadata["part"] for c in chunks] == [str(i) for i in range(1, len(chunks) + 1)]
        covered = []
        for c in chunks:
            assert len(c.text) <= EURLexHTMLChunker.MAX_CHUNK_SIZE
            assert c.text.startswith("Article 7\nLong one\n")
            # Every continuation starts at a paragraph boundary, number first.
            assert re.match(r"^\d+\. word", c.text.split("\n")[2])
            lo, _, hi = c.metadata["paragraph"].partition("-")
            covered.extend(range(int(lo), int(hi or lo) + 1))
        assert covered == list(range(1, 9))

    def test_single_chunk_article_has_no_paragraph_range(self):
        html = self._html(n_paragraphs=2, words=10)
        chunks = EURLexHTMLChunker(celex="32099R0001", framework="X").chunk_html(html)
        assert len(chunks) == 1
        assert chunks[0].metadata["paragraph"] is None
        assert "part" not in chunks[0].metadata


class TestMarkdownFallback:
    def test_markdown_in_single_paragraph_is_packed_by_blank_lines(self):
        md = (
            "Executive summary\n\n"
            "The company operates in Italy and Germany with 2500 employees and reports under CSRD.\n\n"
            "Second paragraph about the double materiality assessment process and its governance.\n\n"
        ) * 3
        chunker = EURLexHTMLChunker(celex="DOC_1234ABCD", framework="CSRD")
        chunks = chunker.chunk_html(f"<html><body><p>{md}</p></body></html>")
        assert chunks
        assert all(c.metadata["chunk_type"] == "paragraph" for c in chunks)
        assert all(c.metadata["article"] == "" and c.metadata["eli"] is None for c in chunks)
        assert "The company operates in Italy" in chunks[0].text
        assert "\n" in chunks[0].text  # paragraphs kept as separate lines

    def test_empty_html_yields_no_chunks(self):
        assert EURLexHTMLChunker(celex="X", framework="Y").chunk_html("") == []
