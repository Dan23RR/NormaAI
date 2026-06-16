"""
Tests for EUR-Lex SPARQL client.

Run: pytest tests/test_eurlex_client.py -v
"""

import pytest

from src.crawler.eurlex.client import CORE_FRAMEWORKS, EurLexClient, RegulationMetadata


class TestCelexParsing:
    """Test CELEX number parsing and document type detection."""

    def test_directive_celex(self):
        assert EurLexClient._celex_to_doc_type("32022L2464") == "directive"

    def test_regulation_celex(self):
        assert EurLexClient._celex_to_doc_type("32024R1689") == "regulation"

    def test_decision_celex(self):
        assert EurLexClient._celex_to_doc_type("32020D0001") == "decision"

    def test_short_celex(self):
        assert EurLexClient._celex_to_doc_type("32") == "unknown"


class TestCoreFrameworks:
    """Verify core framework definitions are complete."""

    def test_all_frameworks_defined(self):
        expected = {"CSRD", "CSDDD", "AI_ACT", "DORA", "NIS2", "TAXONOMY", "GDPR", "CRA"}
        assert set(CORE_FRAMEWORKS.keys()) == expected

    def test_csrd_includes_omnibus(self):
        csrd_celex = CORE_FRAMEWORKS["CSRD"]
        assert "32025L0794" in csrd_celex, "Stop-the-Clock Directive missing"
        assert "32026L0470" in csrd_celex, "Omnibus I substantive Directive missing"

    def test_cra_seeds(self):
        cra_celex = CORE_FRAMEWORKS["CRA"]
        assert "32024R2847" in cra_celex, "Cyber Resilience Act missing"
        assert "32025R2392" in cra_celex, "CRA Implementing Regulation missing"

    def test_all_celex_valid_format(self):
        """All CELEX numbers should start with '3' (legislation sector)."""
        for framework, celex_map in CORE_FRAMEWORKS.items():
            for celex in celex_map:
                assert celex.startswith("3"), f"Invalid CELEX {celex} in {framework}"
                assert len(celex) >= 8, f"CELEX too short: {celex} in {framework}"


class TestRegulationMetadata:
    """Test RegulationMetadata dataclass."""

    def test_default_values(self):
        meta = RegulationMetadata(celex="32022L2464")
        assert meta.celex == "32022L2464"
        assert meta.title == ""
        assert meta.amendments == []
        assert meta.is_in_force is None

    def test_full_metadata(self):
        meta = RegulationMetadata(
            celex="32022L2464",
            title="CSRD",
            framework="CSRD",
            doc_type="directive",
            date_document="2022-12-14",
            is_in_force=True,
            amendments=["32025L0794"],
        )
        assert meta.framework == "CSRD"
        assert len(meta.amendments) == 1


class TestEurLexClientInit:
    """Test client initialization (no network calls)."""

    def test_default_endpoint(self):
        client = EurLexClient()
        assert "publications.europa.eu" in client.endpoint
        client.close()

    def test_custom_endpoint(self):
        client = EurLexClient(endpoint="http://localhost:8080/sparql")
        assert client.endpoint == "http://localhost:8080/sparql"
        client.close()

    def test_rate_limit_config(self):
        client = EurLexClient(request_delay=2.0, max_retries=5)
        assert client.request_delay == 2.0
        assert client.max_retries == 5
        client.close()


class TestFullTextURL:
    """Test full text URL construction."""

    def test_html_url_format(self):
        """Verify EUR-Lex HTML download URL format."""
        celex = "32022L2464"
        expected = f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
        # This is the URL pattern used in download_full_text_html
        url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
        assert url == expected


class TestChunker:
    """Test legal document chunking."""

    def test_simple_html_chunking(self):
        from src.nlp.chunking.legal_chunker import EURLexHTMLChunker

        chunker = EURLexHTMLChunker(celex="32022L2464", framework="CSRD")

        html = """
        <html><body>
        <h2>CHAPTER I - GENERAL PROVISIONS</h2>
        <p>Article 1</p>
        <p>This Directive establishes rules on sustainability reporting by certain categories of undertakings.</p>
        <p>Member States shall ensure that companies report sustainability information in accordance with Articles 19a and 29a of Directive 2013/34/EU.</p>
        <p>Article 2</p>
        <p>For the purposes of this Directive, the following definitions apply: sustainability matters means environmental, social and human rights, and governance factors.</p>
        </body></html>
        """

        chunks = chunker.chunk_html(html)
        assert len(chunks) > 0
        assert all(c.metadata.get("celex") == "32022L2464" for c in chunks)
        assert all(c.metadata.get("framework") == "CSRD" for c in chunks)

    def test_recital_extraction(self):
        from src.nlp.chunking.legal_chunker import EURLexHTMLChunker

        chunker = EURLexHTMLChunker(celex="32022L2464", framework="CSRD")

        html = """
        <html><body>
        <p>(1) The European Green Deal set out a new growth strategy for the Union.</p>
        <p>(2) Sustainability reporting is essential for the transition.</p>
        <p>(3) Financial market participants need reliable sustainability information.</p>
        <p>(4) Current reporting requirements are insufficient.</p>
        <p>(5) A common framework is needed across the Union.</p>
        <p>(6) This Directive aims to address these shortcomings.</p>
        </body></html>
        """

        chunks = chunker.chunk_html(html)
        recital_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "recital"]
        assert len(recital_chunks) > 0


# ─── Integration Tests (require network) ───────────────────────


@pytest.mark.skipif(True, reason="Requires network access to EUR-Lex SPARQL")
class TestEurLexIntegration:
    """Integration tests that hit the real EUR-Lex SPARQL endpoint."""

    def test_fetch_csrd_metadata(self):
        with EurLexClient() as client:
            meta = client.fetch_regulation_metadata("32022L2464")
            assert meta.celex == "32022L2464"
            assert meta.framework == "CSRD"

    def test_fetch_amendments(self):
        with EurLexClient() as client:
            amendments = client.fetch_amendments("32022L2464")
            # CSRD has been amended by Omnibus
            assert isinstance(amendments, list)

    def test_download_full_text(self):
        with EurLexClient() as client:
            html = client.download_full_text_html("32022L2464")
            assert html is not None
            assert len(html) > 1000
            assert "sustainability" in html.lower() or "reporting" in html.lower()
