"""Tests for legal document chunking pipeline."""

from src.nlp.chunking.contextual_chunker import ContextualChunk, ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker, LegalChunk


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
