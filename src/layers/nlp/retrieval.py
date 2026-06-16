"""
Unified retrieval interface for regulatory document search.

Wraps HybridIndexer with:
- Multi-framework parallel search
- Result re-ranking based on regulatory relevance
- Citation extraction from results
- Source attribution (EUR-Lex vs Normattiva)
"""

import logging
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CitationInfo(BaseModel):
    """Citation extracted from a retrieved chunk."""

    celex: str = Field(..., description="CELEX identifier")
    article: str = Field(default="", description="Article number if applicable")
    framework: str = Field(..., description="Framework code (CSRD, GDPR, etc)")
    source: str = Field(default="eur-lex", description="Source (eur-lex, normattiva)")
    url: str | None = Field(default=None, description="URL to the regulation")


class RetrievedChunk(BaseModel):
    """A single retrieved chunk."""

    text: str = Field(..., description="Chunk text")
    celex: str = Field(..., description="CELEX identifier")
    framework: str = Field(..., description="Framework code")
    article_number: str = Field(default="", description="Article number")
    section_title: str = Field(default="", description="Section title")
    chunk_type: str = Field(default="", description="Type of chunk")
    score: float = Field(ge=0.0, le=1.0, description="Retrieval score")
    relevance_score: float | None = Field(default=None, description="Re-ranked relevance score")


class RetrievalResult(BaseModel):
    """Result of a retrieval query."""

    chunks: list[RetrievedChunk] = Field(..., description="Retrieved chunks")
    citations: list[CitationInfo] = Field(..., description="Extracted citations")
    frameworks_found: list[str] = Field(..., description="Unique frameworks in results")
    total_results: int = Field(..., description="Total number of results returned")
    query: str = Field(..., description="Original query")
    query_frameworks: list[str] = Field(
        default_factory=list, description="Frameworks that were queried"
    )


class RetrievalService:
    """
    Unified retrieval interface for regulatory document search.

    Wraps HybridIndexer with multi-framework parallel search,
    result re-ranking, and citation extraction.
    """

    def __init__(self, indexer):
        """
        Initialize retrieval service.

        Args:
            indexer: HybridIndexer instance
        """
        self.indexer = indexer

    async def search(
        self,
        query: str,
        frameworks: list[str] | None = None,
        org_id: str | None = None,
        limit: int = 15,
        include_sources: bool = True,
        rerank: bool = True,
    ) -> RetrievalResult:
        """
        Search with automatic multi-framework handling.

        Workflow:
        1. If frameworks is None, search all frameworks in parallel
        2. If frameworks is specified, search only those frameworks
        3. Re-rank results by regulatory relevance (boost exact article matches)
        4. Extract citations from results
        5. Return aggregated result

        Args:
            query: Search query text
            frameworks: Frameworks to search (None = all, list = specific)
            org_id: Organization ID for multi-tenant filtering
            limit: Maximum results to return
            include_sources: Include source URL attribution
            rerank: Whether to re-rank results by relevance

        Returns:
            RetrievalResult with chunks, citations, and metadata
        """
        # If no specific frameworks, search all
        if frameworks is None:
            frameworks = [
                "CSRD",
                "CSDDD",
                "AI_ACT",
                "DORA",
                "NIS2",
                "TAXONOMY",
                "GDPR",
                "CRA",
                "EIDAS",
                "PSD2",
                "MiFID2",
            ]

        logger.info(f"Retrieval query: '{query[:50]}...' | frameworks={frameworks} | limit={limit}")

        # Perform hybrid search (handles multiple frameworks internally)
        raw_results = self.indexer.hybrid_search(
            query=query,
            limit=limit * 2,  # Get extra results for re-ranking
            framework_filter=frameworks,
            org_id=org_id,
        )

        # Convert to RetrievedChunk objects
        chunks = [
            RetrievedChunk(
                text=r.get("text", ""),
                celex=r.get("celex", ""),
                framework=r.get("framework", ""),
                article_number=r.get("article_number", ""),
                section_title=r.get("section_title", ""),
                chunk_type=r.get("chunk_type", ""),
                score=r.get("score", 0.0),
            )
            for r in raw_results
        ]

        # Re-rank by regulatory relevance
        if rerank and chunks:
            chunks = self._rerank_results(chunks, query)

        # Limit to requested count after re-ranking
        chunks = chunks[:limit]

        # Extract citations
        citations = self._extract_citations(chunks)

        # Add source URLs if requested
        if include_sources:
            chunks = self._add_sources(chunks)

        # Aggregate unique frameworks found
        frameworks_found = sorted(set(c.framework for c in chunks if c.framework))

        result = RetrievalResult(
            chunks=chunks,
            citations=citations,
            frameworks_found=frameworks_found,
            total_results=len(chunks),
            query=query,
            query_frameworks=frameworks,
        )

        logger.info(
            f"Retrieved {len(chunks)} chunks across {len(frameworks_found)} frameworks | "
            f"citations={len(citations)}"
        )

        return result

    def _rerank_results(self, chunks: list[RetrievedChunk], query: str) -> list[RetrievedChunk]:
        """
        Re-rank chunks by regulatory relevance.

        Scoring:
        - Exact article match in query → +0.3
        - Exact framework match → +0.2
        - Article chunk type → +0.1
        - Title match with query terms → +0.15

        Args:
            chunks: Retrieved chunks
            query: Original query

        Returns:
            Re-ranked chunks
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        for chunk in chunks:
            score_boost = 0.0

            # Boost exact article matches
            if chunk.article_number and chunk.article_number.lower() in query_lower:
                score_boost += 0.3
                logger.debug(f"Boosted {chunk.article_number}: exact article match")

            # Boost article chunk type
            if chunk.chunk_type and chunk.chunk_type.lower() == "article":
                score_boost += 0.1

            # Boost title matches
            if chunk.section_title:
                title_terms = set(chunk.section_title.lower().split())
                title_overlap = len(query_terms & title_terms) / len(query_terms)
                if title_overlap > 0.3:
                    score_boost += title_overlap * 0.15

            # Apply boost (capped at 1.0)
            chunk.relevance_score = min(1.0, chunk.score + score_boost)

        # Sort by relevance score
        chunks.sort(key=lambda x: x.relevance_score or x.score, reverse=True)

        return chunks

    def _extract_citations(self, chunks: list[RetrievedChunk]) -> list[CitationInfo]:
        """
        Extract citation metadata from retrieved chunks.

        Each unique CELEX gets one citation entry with all its articles.

        Args:
            chunks: Retrieved chunks

        Returns:
            List of CitationInfo objects
        """
        citations_map = {}

        for chunk in chunks:
            if not chunk.celex:
                continue

            if chunk.celex not in citations_map:
                citations_map[chunk.celex] = CitationInfo(
                    celex=chunk.celex,
                    framework=chunk.framework,
                    source=self._infer_source(chunk.celex),
                    url=self._build_url(chunk.celex, chunk.framework),
                )

            # Collect all articles for this CELEX
            if (
                chunk.article_number
                and chunk.article_number not in citations_map[chunk.celex].article
            ):
                citations_map[chunk.celex].article += f"{chunk.article_number}, "

        # Clean up article lists
        for citation in citations_map.values():
            citation.article = citation.article.rstrip(", ")

        return sorted(citations_map.values(), key=lambda x: x.celex)

    def _add_sources(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Add source URL attribution to chunks."""
        for _chunk in chunks:
            # Source URL could be added to chunk metadata here
            # For now, handled at display layer
            pass
        return chunks

    @staticmethod
    def _infer_source(celex: str) -> str:
        """Infer source (EUR-Lex vs Normattiva) from CELEX."""
        if celex.startswith("IT"):
            return "normattiva"
        return "eur-lex"

    @staticmethod
    def _build_url(celex: str, framework: str = "") -> str | None:
        """Build a URL to the regulation."""
        if not celex:
            return None

        if celex.startswith("IT"):
            # Normattiva URLs are complex, would need mapping
            return None

        # EUR-Lex URL format: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"

    @staticmethod
    def parse_articles_from_text(text: str) -> list[str]:
        """
        Extract article references from text.

        Looks for patterns like "Article 5", "Art. 29", etc.
        """
        patterns = [
            r"Article\s+(\d+(?:\s*\(.\))?)",
            r"Art\.\s+(\d+(?:\s*\(.\))?)",
            r"Article\s+(\d+[a-z]?)",
        ]

        articles = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            articles.update(matches)

        return sorted(articles)

    @staticmethod
    def parse_celex_from_text(text: str) -> str | None:
        """
        Extract CELEX identifier from text.

        CELEX format: e.g., 32022L2464, IT0000000000
        """
        # Standard EU CELEX format
        match = re.search(r"CELEX[:\s=]*([A-Z]{2}\d{4}[A-Z0-9]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)

        # Direct CELEX code
        match = re.search(r"([A-Z]{2}\d{4}[A-Z0-9]{4,})", text)
        if match:
            return match.group(1)

        return None
