"""
Legal Document Chunker — Semantic chunking that respects EU regulation structure.

EU legislation follows a strict hierarchy:
  Regulation/Directive → Part → Title → Chapter → Section → Article → Paragraph → Point

This chunker:
1. Parses HTML from EUR-Lex into structured sections
2. Creates chunks that respect article boundaries (never split mid-article)
3. Attaches rich metadata (framework, article number, section, recital vs article)
4. Handles tables and annexes as atomic units
"""

import logging
import re
import warnings
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

# CELLAR serves XHTML; we parse it with the lxml HTML parser on purpose (it
# handles both CELLAR XHTML and the legal-content HTML). Silence the noisy
# "looks like an XML document" advisory so seed logs stay readable.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)


@dataclass
class LegalChunk:
    """A semantically meaningful chunk of EU legal text."""

    text: str
    metadata: dict = field(default_factory=dict)

    # Metadata fields:
    # - celex: str — CELEX number of source regulation
    # - framework: str — CSRD, CSDDD, AI_ACT, etc.
    # - chunk_type: str — recital, article, annex, preamble, table
    # - article_number: str — "Art. 29" or "Recital 45"
    # - section_title: str — "Chapter III - Sustainability Reporting"
    # - hierarchy: str — "Part I > Title II > Chapter III > Art. 29"
    # - page_ref: str — reference for citation
    # - char_count: int — length of text


class EURLexHTMLChunker:
    """
    Chunk EUR-Lex HTML into semantically meaningful pieces.

    Strategy:
    - Parse the HTML structure to identify articles, recitals, annexes
    - Each article becomes 1 chunk (unless very long → split at paragraph level)
    - Recitals grouped in batches of 5-10 for context
    - Tables and annexes kept as atomic units
    - Max chunk size: ~2000 chars (optimal for embedding + retrieval)
    """

    MAX_CHUNK_SIZE = 2000
    MIN_CHUNK_SIZE = 100
    RECITAL_BATCH_SIZE = 5

    # Block-level tags we segment on. We walk only LEAF blocks (elements that
    # nest no other block): EUR-Lex CELLAR serves deeply nested Formex XHTML
    # (div > table > p), and iterating raw find_all() there re-extracts every
    # ancestor's text at each nesting level (~6x inflation) and mangles layout
    # tables into joined-cell rows. Leaf-only visits each text span exactly
    # once and works equally on the flatter legal-content HTML.
    BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "li", "table"]

    def __init__(self, celex: str, framework: str):
        self.celex = celex
        self.framework = framework

    def _iter_leaf_blocks(self, soup) -> list:
        """Return block elements that nest no other block element.

        Visiting only leaves makes chunking robust to deeply nested XHTML
        (CELLAR Formex) as well as flat legal-content HTML: each text span is
        seen once, at its finest granularity, and layout tables dissolve into
        their inner paragraphs instead of being mangled as data tables.
        """
        return [el for el in soup.find_all(self.BLOCK_TAGS) if not el.find(self.BLOCK_TAGS)]

    def chunk_html(self, html: str) -> list[LegalChunk]:
        """Parse EUR-Lex HTML and return structured chunks."""
        soup = BeautifulSoup(html, "lxml")
        chunks: list[LegalChunk] = []

        # Remove scripts, styles, nav elements
        for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Strategy 1: Try to find article-level structure
        articles = self._extract_articles(soup)
        if articles:
            chunks.extend(articles)

        # Strategy 2: Extract recitals
        recitals = self._extract_recitals(soup)
        if recitals:
            chunks.extend(recitals)

        # Strategy 3: Extract annexes
        annexes = self._extract_annexes(soup)
        if annexes:
            chunks.extend(annexes)

        # Strategy 4: If no structured content found, fall back to paragraph-based chunking
        if not chunks:
            logger.warning(f"No structured content found for {self.celex}, using fallback chunking")
            chunks = self._fallback_paragraph_chunking(soup)

        # Add char_count metadata
        for chunk in chunks:
            chunk.metadata["char_count"] = len(chunk.text)
            chunk.metadata["celex"] = self.celex
            chunk.metadata["framework"] = self.framework

        logger.info(f"Chunked {self.celex}: {len(chunks)} chunks created")
        return chunks

    def _extract_articles(self, soup: BeautifulSoup) -> list[LegalChunk]:
        """Extract individual articles from EU legislation HTML."""
        chunks = []
        current_section = ""
        current_hierarchy = ""

        # EUR-Lex uses specific class patterns for articles
        # Common patterns: div.eli-subdivision, p.sti-art, ti-section-1
        article_patterns = [
            # Standard EUR-Lex HTML pattern
            re.compile(r"(?:Article|Artikel|Articolo|Article)\s+(\d+[a-z]?)"),
        ]

        # Find all text elements and group by article
        current_article_text = ""
        current_article_num = ""

        for element in self._iter_leaf_blocks(soup):
            text = element.get_text(strip=True)
            if not text:
                continue

            # Check if this is a section/chapter heading
            if element.name in ["h1", "h2", "h3", "h4"]:
                current_section = text
                current_hierarchy = text
                continue

            # Check if this starts a new article
            is_new_article = False
            for pattern in article_patterns:
                match = pattern.search(text)
                if match and len(text) < 50:  # Article headers are short
                    is_new_article = True
                    new_article_num = match.group(1)
                    break

            if is_new_article:
                # Save previous article if exists
                if current_article_text and len(current_article_text) >= self.MIN_CHUNK_SIZE:
                    chunks.extend(
                        self._split_if_needed(
                            current_article_text,
                            chunk_type="article",
                            article_number=f"Art. {current_article_num}",
                            section_title=current_section,
                            hierarchy=current_hierarchy,
                        )
                    )
                current_article_text = text + "\n"
                current_article_num = new_article_num
            elif element.name == "table":
                # Tables are atomic — save as separate chunk
                table_text = self._extract_table_text(element)
                if table_text and len(table_text) >= self.MIN_CHUNK_SIZE:
                    chunks.append(
                        LegalChunk(
                            text=table_text,
                            metadata={
                                "chunk_type": "table",
                                "article_number": f"Art. {current_article_num}"
                                if current_article_num
                                else "",
                                "section_title": current_section,
                                "hierarchy": current_hierarchy,
                            },
                        )
                    )
            else:
                current_article_text += text + "\n"

        # Don't forget the last article
        if current_article_text and len(current_article_text) >= self.MIN_CHUNK_SIZE:
            chunks.extend(
                self._split_if_needed(
                    current_article_text,
                    chunk_type="article",
                    article_number=f"Art. {current_article_num}",
                    section_title=current_section,
                    hierarchy=current_hierarchy,
                )
            )

        return chunks

    def _extract_recitals(self, soup: BeautifulSoup) -> list[LegalChunk]:
        """Extract recitals (preamble 'whereas' clauses)."""
        chunks = []
        recital_texts = []
        recital_count = 0

        recital_pattern = re.compile(r"^\((\d+)\)")

        for p in self._iter_leaf_blocks(soup):
            text = p.get_text(strip=True)
            match = recital_pattern.match(text)
            if match:
                recital_count += 1
                recital_texts.append(text)

                # Batch recitals
                if len(recital_texts) >= self.RECITAL_BATCH_SIZE:
                    batch_text = "\n\n".join(recital_texts)
                    start_num = recital_count - len(recital_texts) + 1
                    chunks.append(
                        LegalChunk(
                            text=batch_text,
                            metadata={
                                "chunk_type": "recital",
                                "article_number": f"Recitals ({start_num}-{recital_count})",
                                "section_title": "Preamble",
                                "hierarchy": "Preamble > Recitals",
                            },
                        )
                    )
                    recital_texts = []

        # Remaining recitals
        if recital_texts:
            batch_text = "\n\n".join(recital_texts)
            start_num = recital_count - len(recital_texts) + 1
            chunks.append(
                LegalChunk(
                    text=batch_text,
                    metadata={
                        "chunk_type": "recital",
                        "article_number": f"Recitals ({start_num}-{recital_count})",
                        "section_title": "Preamble",
                        "hierarchy": "Preamble > Recitals",
                    },
                )
            )

        return chunks

    def _extract_annexes(self, soup: BeautifulSoup) -> list[LegalChunk]:
        """Extract annexes as separate chunks."""
        chunks = []
        annex_pattern = re.compile(r"ANNEX\s*([IVXLCDM]+|\d+)", re.IGNORECASE)

        current_annex = ""
        current_annex_text = ""

        for element in self._iter_leaf_blocks(soup):
            text = element.get_text(strip=True)
            match = annex_pattern.match(text)

            if match and len(text) < 100:
                # Save previous annex
                if current_annex_text and len(current_annex_text) >= self.MIN_CHUNK_SIZE:
                    chunks.extend(
                        self._split_if_needed(
                            current_annex_text,
                            chunk_type="annex",
                            article_number=current_annex,
                            section_title=current_annex,
                            hierarchy=f"Annexes > {current_annex}",
                        )
                    )
                current_annex = text
                current_annex_text = text + "\n"
            elif current_annex:
                current_annex_text += text + "\n"

        # Last annex
        if current_annex_text and len(current_annex_text) >= self.MIN_CHUNK_SIZE:
            chunks.extend(
                self._split_if_needed(
                    current_annex_text,
                    chunk_type="annex",
                    article_number=current_annex,
                    section_title=current_annex,
                    hierarchy=f"Annexes > {current_annex}",
                )
            )

        return chunks

    def _split_if_needed(self, text: str, **metadata) -> list[LegalChunk]:
        """Split text into chunks if it exceeds MAX_CHUNK_SIZE."""
        if len(text) <= self.MAX_CHUNK_SIZE:
            return [LegalChunk(text=text.strip(), metadata=metadata)]

        # Split at paragraph boundaries
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # If a single paragraph exceeds MAX_CHUNK_SIZE, hard-split at sentence/word boundaries
            if len(para) > self.MAX_CHUNK_SIZE:
                if current_chunk.strip():
                    chunks.append(
                        LegalChunk(
                            text=current_chunk.strip(),
                            metadata={**metadata, "part": f"{len(chunks) + 1}"},
                        )
                    )
                    current_chunk = ""
                for sub in self._hard_split(para):
                    chunks.append(
                        LegalChunk(
                            text=sub.strip(),
                            metadata={**metadata, "part": f"{len(chunks) + 1}"},
                        )
                    )
            elif len(current_chunk) + len(para) > self.MAX_CHUNK_SIZE and current_chunk:
                chunks.append(
                    LegalChunk(
                        text=current_chunk.strip(),
                        metadata={**metadata, "part": f"{len(chunks) + 1}"},
                    )
                )
                current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"

        if current_chunk.strip():
            chunks.append(
                LegalChunk(
                    text=current_chunk.strip(),
                    metadata={**metadata, "part": f"{len(chunks) + 1}"},
                )
            )

        return chunks

    def _hard_split(self, text: str) -> list[str]:
        """Hard-split a single long text block that has no paragraph breaks."""
        # Try splitting on sentence boundaries first
        sentences = re.split(r"(?<=[.;])\s+", text)
        parts = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) > self.MAX_CHUNK_SIZE and current:
                parts.append(current)
                current = sent
            else:
                current = (current + " " + sent).strip() if current else sent
        if current:
            # If a single segment still exceeds, split at word boundaries
            while len(current) > self.MAX_CHUNK_SIZE:
                split_at = current.rfind(" ", 0, self.MAX_CHUNK_SIZE)
                if split_at <= 0:
                    split_at = self.MAX_CHUNK_SIZE
                parts.append(current[:split_at])
                current = current[split_at:].lstrip()
            if current:
                parts.append(current)
        return parts

    def _extract_table_text(self, table_tag: Tag) -> str:
        """Convert HTML table to readable text format."""
        rows = []
        for tr in table_tag.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _fallback_paragraph_chunking(self, soup: BeautifulSoup) -> list[LegalChunk]:
        """Fallback: chunk by paragraphs when structure is not recognized."""
        chunks = []
        current_text = ""

        for p in self._iter_leaf_blocks(soup):
            text = p.get_text(strip=True)
            if not text or len(text) < 20:
                continue

            if len(current_text) + len(text) > self.MAX_CHUNK_SIZE and current_text:
                chunks.append(
                    LegalChunk(
                        text=current_text.strip(),
                        metadata={
                            "chunk_type": "paragraph",
                            "article_number": "",
                            "section_title": "",
                            "hierarchy": "",
                        },
                    )
                )
                current_text = text + "\n"
            else:
                current_text += text + "\n"

        if current_text.strip():
            chunks.append(
                LegalChunk(
                    text=current_text.strip(),
                    metadata={
                        "chunk_type": "paragraph",
                        "article_number": "",
                        "section_title": "",
                        "hierarchy": "",
                    },
                )
            )

        return chunks
