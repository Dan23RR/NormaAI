"""
Contextual Chunker - Enriches chunks with document-level context for better retrieval.

Key innovation: Instead of embedding raw article text, prepend a contextual summary
that places the chunk in its regulatory hierarchy. This improves retrieval accuracy
by 10-15% (based on Anthropic's contextual retrieval research).

Example:
    BEFORE: "Member States shall ensure that controllers implement appropriate
             technical and organisational measures..."

    AFTER:  "[GDPR | Article 32 | Security of Processing | Chapter IV - Controller and Processor]
             Member States shall ensure that controllers implement appropriate
             technical and organisational measures..."

This approach preserves the original text while adding retrieval-friendly context.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Framework display names for context prefixes
FRAMEWORK_CONTEXT = {
    "CSRD": "Corporate Sustainability Reporting Directive (EU) 2022/2464",
    "CSDDD": "Corporate Sustainability Due Diligence Directive (EU) 2024/1760",
    "AI_ACT": "EU Artificial Intelligence Act (EU) 2024/1689",
    "DORA": "Digital Operational Resilience Act (EU) 2022/2554",
    "NIS2": "Network and Information Security Directive (EU) 2022/2555",
    "TAXONOMY": "EU Taxonomy Regulation (EU) 2020/852",
    "GDPR": "General Data Protection Regulation (EU) 2016/679",
    "CRA": "Cyber Resilience Act (EU) 2024/2847",
}


@dataclass
class ContextualChunk:
    """A chunk enriched with document-level context."""

    text: str  # Original text
    contextualized_text: str  # Text with context prefix (used for embedding)
    metadata: dict = field(default_factory=dict)


class ContextualChunker:
    """
    Wraps any chunker and adds contextual prefixes to chunks.

    The contextualized_text is what gets embedded into the vector DB,
    while the original text is preserved in the payload for display.
    """

    def __init__(self, framework_context: dict | None = None):
        self.framework_context = framework_context or FRAMEWORK_CONTEXT

    def enrich_chunks(self, chunks: list, framework: str = "") -> list[ContextualChunk]:
        """
        Add contextual prefixes to chunks from the legal chunker.

        Args:
            chunks: List of LegalChunk objects from EURLexHTMLChunker
            framework: Framework key (e.g., "CSRD", "GDPR")

        Returns:
            List of ContextualChunk objects with enriched text
        """
        enriched = []
        framework_name = self.framework_context.get(framework, framework)

        for chunk in chunks:
            # Build context prefix from metadata
            context_parts = []

            if framework_name:
                context_parts.append(framework_name)

            article = chunk.metadata.get("article_number", "")
            if article:
                context_parts.append(article)

            section = chunk.metadata.get("section_title", "")
            if section:
                context_parts.append(section)

            hierarchy = chunk.metadata.get("hierarchy", "")
            if hierarchy and hierarchy != section:
                context_parts.append(hierarchy)

            chunk_type = chunk.metadata.get("chunk_type", "")
            if chunk_type and chunk_type not in ["article", "paragraph"]:
                context_parts.append(f"({chunk_type})")

            # Build contextualized text
            if context_parts:
                context_prefix = " | ".join(context_parts)
                contextualized = f"[{context_prefix}]\n{chunk.text}"
            else:
                contextualized = chunk.text

            enriched.append(
                ContextualChunk(
                    text=chunk.text,
                    contextualized_text=contextualized,
                    metadata={
                        **chunk.metadata,
                        "framework": framework,
                        "has_context": True,
                    },
                )
            )

        logger.info(
            f"Enriched {len(enriched)} chunks with contextual prefixes " f"(framework: {framework})"
        )
        return enriched

    def enrich_single(
        self, text: str, framework: str = "", article: str = "", section: str = ""
    ) -> ContextualChunk:
        """Enrich a single text string with context."""
        framework_name = self.framework_context.get(framework, framework)
        parts = [p for p in [framework_name, article, section] if p]

        if parts:
            prefix = " | ".join(parts)
            contextualized = f"[{prefix}]\n{text}"
        else:
            contextualized = text

        return ContextualChunk(
            text=text,
            contextualized_text=contextualized,
            metadata={
                "framework": framework,
                "article_number": article,
                "section_title": section,
                "has_context": True,
            },
        )
