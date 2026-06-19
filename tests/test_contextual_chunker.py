"""Tests for the ContextualChunker.

The ContextualChunker enriches chunks with a structured context prefix
(framework | article | section | hierarchy) so that the embedded text carries
its place in the regulatory hierarchy. These tests exercise the pure-logic
paths: single-text enrichment, batch enrichment over LegalChunk objects,
framework-name resolution, metadata preservation and graceful handling of
missing fields. No network / LLM / DB involved.
"""

from dataclasses import dataclass, field

from src.nlp.chunking.contextual_chunker import (
    FRAMEWORK_CONTEXT,
    ContextualChunk,
    ContextualChunker,
)
from src.nlp.chunking.legal_chunker import LegalChunk


@dataclass
class FakeChunk:
    """Minimal stand-in for a LegalChunk: anything with .text and .metadata."""

    text: str
    metadata: dict = field(default_factory=dict)


class TestEnrichSingle:
    def setup_method(self):
        self.chunker = ContextualChunker()

    def test_full_context_builds_prefix_in_order(self):
        result = self.chunker.enrich_single(
            text="Member States shall ensure compliance.",
            framework="GDPR",
            article="Art. 32",
            section="Security of Processing",
        )
        assert isinstance(result, ContextualChunk)
        # Original text preserved verbatim.
        assert result.text == "Member States shall ensure compliance."
        # Framework key resolved to its display name.
        expected_prefix = (
            "[General Data Protection Regulation (EU) 2016/679 | "
            "Art. 32 | Security of Processing]"
        )
        assert result.contextualized_text == (
            f"{expected_prefix}\nMember States shall ensure compliance."
        )

    def test_metadata_stores_raw_framework_key_not_display_name(self):
        result = self.chunker.enrich_single(
            text="x", framework="GDPR", article="Art. 1", section="Sec"
        )
        # metadata keeps the raw key, not the resolved display name.
        assert result.metadata["framework"] == "GDPR"
        assert result.metadata["article_number"] == "Art. 1"
        assert result.metadata["section_title"] == "Sec"
        assert result.metadata["has_context"] is True

    def test_no_context_returns_text_unchanged(self):
        result = self.chunker.enrich_single(text="Some text")
        assert result.text == "Some text"
        # With no framework/article/section, contextualized == original.
        assert result.contextualized_text == "Some text"
        # has_context is still set True even though no prefix was added.
        assert result.metadata["has_context"] is True
        assert result.metadata["framework"] == ""
        assert result.metadata["article_number"] == ""
        assert result.metadata["section_title"] == ""

    def test_unknown_framework_falls_back_to_raw_key(self):
        # An unknown framework key is not in FRAMEWORK_CONTEXT, so .get returns
        # the key itself, which is then used as the display name.
        result = self.chunker.enrich_single(text="body", framework="MIFID2")
        assert result.contextualized_text == "[MIFID2]\nbody"
        assert result.metadata["framework"] == "MIFID2"

    def test_only_article_no_framework(self):
        result = self.chunker.enrich_single(text="body", article="Art. 5")
        # framework="" -> framework_name="" filtered out, only article remains.
        assert result.contextualized_text == "[Art. 5]\nbody"
        assert result.metadata["framework"] == ""
        assert result.metadata["article_number"] == "Art. 5"

    def test_only_section_no_framework_no_article(self):
        result = self.chunker.enrich_single(text="body", section="Chapter IV")
        assert result.contextualized_text == "[Chapter IV]\nbody"

    def test_framework_and_section_skips_empty_article(self):
        result = self.chunker.enrich_single(
            text="body", framework="DORA", section="Operational Resilience"
        )
        # Empty article is filtered; prefix is framework | section.
        assert result.contextualized_text == (
            "[Digital Operational Resilience Act (EU) 2022/2554 | " "Operational Resilience]\nbody"
        )

    def test_known_frameworks_resolve_to_display_names(self):
        for fw_key, display in FRAMEWORK_CONTEXT.items():
            result = self.chunker.enrich_single("test body", framework=fw_key)
            # metadata holds the raw key.
            assert result.metadata["framework"] == fw_key
            # contextualized text uses the human-readable display name.
            assert result.contextualized_text == f"[{display}]\ntest body"

    def test_empty_text_with_framework(self):
        result = self.chunker.enrich_single(text="", framework="GDPR")
        # Empty body still gets a prefix; the body after the newline is empty.
        assert result.text == ""
        assert result.contextualized_text == (
            "[General Data Protection Regulation (EU) 2016/679]\n"
        )


class TestEnrichSingleCustomContext:
    def test_custom_framework_context_overrides_default(self):
        custom = {"FOO": "Foo Framework Long Name"}
        chunker = ContextualChunker(framework_context=custom)
        result = chunker.enrich_single("text", framework="FOO")
        assert result.contextualized_text == "[Foo Framework Long Name]\ntext"

    def test_custom_context_does_not_know_default_keys(self):
        custom = {"FOO": "Foo Framework"}
        chunker = ContextualChunker(framework_context=custom)
        # GDPR is not in the custom map, so it falls back to the raw key.
        result = chunker.enrich_single("text", framework="GDPR")
        assert result.contextualized_text == "[GDPR]\ntext"

    def test_none_framework_context_uses_default(self):
        chunker = ContextualChunker(framework_context=None)
        assert chunker.framework_context is FRAMEWORK_CONTEXT
        result = chunker.enrich_single("text", framework="NIS2")
        assert result.contextualized_text == (
            "[Network and Information Security Directive (EU) 2022/2555]\ntext"
        )


class TestEnrichChunks:
    def setup_method(self):
        self.chunker = ContextualChunker()

    def test_enrich_chunks_builds_full_prefix(self):
        chunk = FakeChunk(
            text="Controllers shall implement measures.",
            metadata={
                "article_number": "Art. 32",
                "section_title": "Security of Processing",
                "hierarchy": "Chapter IV > Section 2 > Art. 32",
                "chunk_type": "article",
                "celex": "32016R0679",
            },
        )
        out = self.chunker.enrich_chunks([chunk], framework="GDPR")
        assert len(out) == 1
        enriched = out[0]
        assert isinstance(enriched, ContextualChunk)
        # Original text preserved.
        assert enriched.text == "Controllers shall implement measures."
        # Prefix order: framework | article | section | hierarchy.
        # chunk_type 'article' is excluded from the prefix.
        assert enriched.contextualized_text == (
            "[General Data Protection Regulation (EU) 2016/679 | "
            "Art. 32 | Security of Processing | "
            "Chapter IV > Section 2 > Art. 32]\n"
            "Controllers shall implement measures."
        )

    def test_enrich_chunks_preserves_original_metadata(self):
        chunk = FakeChunk(
            text="body text here",
            metadata={
                "article_number": "Art. 9",
                "section_title": "Sec",
                "celex": "32022L2464",
                "char_count": 14,
                "page_ref": "p.3",
            },
        )
        out = self.chunker.enrich_chunks([chunk], framework="CSRD")
        meta = out[0].metadata
        # Original keys survive.
        assert meta["celex"] == "32022L2464"
        assert meta["char_count"] == 14
        assert meta["page_ref"] == "p.3"
        assert meta["article_number"] == "Art. 9"
        # Added keys.
        assert meta["framework"] == "CSRD"
        assert meta["has_context"] is True

    def test_enrich_chunks_does_not_mutate_input_metadata(self):
        original_meta = {"article_number": "Art. 1", "section_title": "S"}
        chunk = FakeChunk(text="body", metadata=original_meta)
        self.chunker.enrich_chunks([chunk], framework="CSRD")
        # The source dict must be untouched (enrich uses {**chunk.metadata}).
        assert "framework" not in original_meta
        assert "has_context" not in original_meta

    def test_empty_chunk_list_returns_empty(self):
        out = self.chunker.enrich_chunks([], framework="GDPR")
        assert out == []

    def test_hierarchy_equal_to_section_is_not_duplicated(self):
        chunk = FakeChunk(
            text="some text",
            metadata={
                "article_number": "Art. 5",
                "section_title": "Chapter I",
                "hierarchy": "Chapter I",  # identical to section
            },
        )
        out = self.chunker.enrich_chunks([chunk], framework="CSRD")
        prefix = out[0].contextualized_text.split("]\n")[0]
        # 'Chapter I' should appear exactly once (section), not twice.
        assert prefix.count("Chapter I") == 1

    def test_chunk_type_table_appended_in_parentheses(self):
        chunk = FakeChunk(
            text="row1 | row2",
            metadata={
                "article_number": "Art. 3",
                "chunk_type": "table",
            },
        )
        out = self.chunker.enrich_chunks([chunk], framework="CSRD")
        # Non article/paragraph chunk_type is appended as "(table)".
        assert "(table)" in out[0].contextualized_text

    def test_chunk_type_paragraph_not_appended(self):
        chunk = FakeChunk(
            text="plain body",
            metadata={"article_number": "Art. 3", "chunk_type": "paragraph"},
        )
        out = self.chunker.enrich_chunks([chunk], framework="CSRD")
        assert "(paragraph)" not in out[0].contextualized_text

    def test_chunk_type_recital_is_appended(self):
        chunk = FakeChunk(
            text="recital body",
            metadata={"article_number": "Recitals (1-5)", "chunk_type": "recital"},
        )
        out = self.chunker.enrich_chunks([chunk], framework="CSRD")
        assert "(recital)" in out[0].contextualized_text

    def test_no_framework_no_metadata_returns_raw_text(self):
        # framework="" -> framework_name="" filtered; all metadata empty.
        chunk = FakeChunk(text="raw body", metadata={})
        out = self.chunker.enrich_chunks([chunk], framework="")
        enriched = out[0]
        # No context parts at all -> contextualized equals original.
        assert enriched.contextualized_text == "raw body"
        # framework recorded as empty string, has_context still True.
        assert enriched.metadata["framework"] == ""
        assert enriched.metadata["has_context"] is True

    def test_missing_metadata_fields_handled_gracefully(self):
        # A chunk whose metadata lacks article/section/hierarchy/chunk_type.
        chunk = FakeChunk(text="lonely body", metadata={"celex": "X"})
        out = self.chunker.enrich_chunks([chunk], framework="AI_ACT")
        enriched = out[0]
        # Only the framework name ends up in the prefix.
        assert enriched.contextualized_text == (
            "[EU Artificial Intelligence Act (EU) 2024/1689]\nlonely body"
        )
        assert enriched.metadata["celex"] == "X"

    def test_unknown_framework_used_as_display_name_in_batch(self):
        chunk = FakeChunk(text="body", metadata={"article_number": "Art. 1"})
        out = self.chunker.enrich_chunks([chunk], framework="MYREG")
        # Unknown framework falls back to the raw key as display name.
        assert out[0].contextualized_text == "[MYREG | Art. 1]\nbody"
        assert out[0].metadata["framework"] == "MYREG"

    def test_multiple_chunks_each_enriched(self):
        chunks = [
            FakeChunk(text=f"body {i}", metadata={"article_number": f"Art. {i}"}) for i in range(3)
        ]
        out = self.chunker.enrich_chunks(chunks, framework="DORA")
        assert len(out) == 3
        for i, enriched in enumerate(out):
            assert enriched.text == f"body {i}"
            assert f"Art. {i}" in enriched.contextualized_text
            assert enriched.metadata["framework"] == "DORA"

    def test_works_with_real_legal_chunk(self):
        # Faithful end-to-end: a real LegalChunk feeding enrich_chunks.
        chunk = LegalChunk(
            text="Undertakings shall report sustainability information.",
            metadata={
                "chunk_type": "article",
                "article_number": "Art. 19a",
                "section_title": "Chapter III - Sustainability Reporting",
                "hierarchy": "Title I > Chapter III > Art. 19a",
                "celex": "32022L2464",
            },
        )
        out = self.chunker.enrich_chunks([chunk], framework="CSRD")
        enriched = out[0]
        assert enriched.text == "Undertakings shall report sustainability information."
        assert "Corporate Sustainability Reporting Directive" in enriched.contextualized_text
        assert "Art. 19a" in enriched.contextualized_text
        assert "Chapter III - Sustainability Reporting" in enriched.contextualized_text
        assert enriched.metadata["framework"] == "CSRD"
        assert enriched.metadata["has_context"] is True


class TestContextualChunkDataclass:
    def test_defaults_to_empty_metadata(self):
        c = ContextualChunk(text="a", contextualized_text="[X]\na")
        assert c.metadata == {}

    def test_fields_assignable(self):
        c = ContextualChunk(text="a", contextualized_text="[X]\na", metadata={"k": "v"})
        assert c.text == "a"
        assert c.contextualized_text == "[X]\na"
        assert c.metadata == {"k": "v"}

    def test_distinct_instances_have_independent_metadata(self):
        a = ContextualChunk(text="1", contextualized_text="1")
        b = ContextualChunk(text="2", contextualized_text="2")
        a.metadata["x"] = 1
        # Default factory must not share state across instances.
        assert b.metadata == {}
