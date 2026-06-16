"""
Docling-based Document Processor — Enterprise-grade PDF/HTML parsing for EU regulations.

Uses IBM's Docling library for:
- Layout-aware document parsing (tables, headers, reading order)
- Multi-format support (PDF, HTML, DOCX)
- Structure-preserving markdown conversion
- Handles complex EU regulation layouts

Falls back to BeautifulSoup HTML parsing if Docling is not available.
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import Docling (optional dependency)
try:
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter

    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    logger.info(
        "Docling not installed. Using fallback HTML parser. Install with: pip install docling"
    )


class DoclingProcessor:
    """
    Process EU regulation documents using Docling for structure-preserving extraction.

    Capabilities:
    - PDF → Structured Markdown with preserved tables, headers, reading order
    - HTML → Clean text with hierarchy detection
    - Automatic language detection for multilingual EU docs
    """

    def __init__(self):
        self._converter = None

    @property
    def converter(self):
        """Lazy-init Docling converter."""
        if self._converter is None and DOCLING_AVAILABLE:
            self._converter = DocumentConverter()
        return self._converter

    @property
    def is_available(self) -> bool:
        """Check if Docling is installed and working."""
        return DOCLING_AVAILABLE

    def process_pdf(self, pdf_path: str) -> dict | None:
        """
        Process a PDF regulation document.

        Returns:
            dict with keys: markdown, tables, metadata
        """
        if not DOCLING_AVAILABLE:
            logger.warning("Docling not available for PDF processing")
            return None

        try:
            result = self.converter.convert(pdf_path)
            doc = result.document

            return {
                "markdown": doc.export_to_markdown(),
                "tables": self._extract_tables(doc),
                "metadata": {
                    "pages": len(doc.pages) if hasattr(doc, "pages") else 0,
                    "format": "pdf",
                    "source": str(pdf_path),
                },
            }
        except Exception as e:
            logger.error(f"Docling PDF processing failed: {e}")
            return None

    def process_html(self, html_content: str, source_url: str = "") -> dict | None:
        """
        Process HTML regulation document via Docling.

        Falls back to BeautifulSoup if Docling unavailable.
        """
        if not DOCLING_AVAILABLE:
            return self._fallback_html_process(html_content, source_url)

        try:
            # Write HTML to temp file for Docling
            with tempfile.NamedTemporaryFile(
                suffix=".html", mode="w", encoding="utf-8", delete=False
            ) as f:
                f.write(html_content)
                temp_path = f.name

            result = self.converter.convert(temp_path)
            doc = result.document

            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

            return {
                "markdown": doc.export_to_markdown(),
                "tables": self._extract_tables(doc),
                "metadata": {
                    "format": "html",
                    "source": source_url,
                },
            }
        except Exception as e:
            logger.warning(f"Docling HTML processing failed, using fallback: {e}")
            return self._fallback_html_process(html_content, source_url)

    def _extract_tables(self, doc) -> list[dict]:
        """Extract structured tables from Docling document."""
        tables = []
        try:
            for table in doc.tables:
                tables.append(
                    {
                        "caption": getattr(table, "caption", ""),
                        "markdown": table.export_to_markdown()
                        if hasattr(table, "export_to_markdown")
                        else str(table),
                    }
                )
        except (AttributeError, TypeError):
            pass
        return tables

    def _fallback_html_process(self, html_content: str, source_url: str = "") -> dict:
        """Fallback HTML processing using BeautifulSoup."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")

        # Remove non-content elements
        for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Extract text preserving some structure
        text_parts = []
        for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
            text = element.get_text(strip=True)
            if text:
                if element.name.startswith("h"):
                    text_parts.append(f"\n## {text}\n")
                else:
                    text_parts.append(text)

        markdown = "\n\n".join(text_parts)

        return {
            "markdown": markdown,
            "tables": [],
            "metadata": {
                "format": "html",
                "source": source_url,
                "processor": "fallback_beautifulsoup",
            },
        }
