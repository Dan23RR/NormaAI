"""
Confidence-based processor routing — automatically selects between dots.ocr and Docling.

Routes documents to the best processor based on quality analysis:
- Digital PDFs with extractable text → Docling (faster, cheaper)
- Scanned PDFs / complex layouts / images → dots.ocr (VLM, more accurate)

Returns processing metadata including processor used, confidence score, and timing.
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProcessingResult(BaseModel):
    """Result of document processing through the router."""

    text: str = Field(..., description="Extracted text content")
    markdown: str = Field(default="", description="Structured markdown output")
    tables: list[dict] = Field(default_factory=list, description="Extracted tables")
    processor_used: str = Field(
        ..., description="Processor that was used (dots_ocr, docling, fallback)"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in extraction quality (0-1)")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ProcessorRouter:
    """Routes documents to the best processor based on quality analysis."""

    def __init__(
        self,
        dots_ocr_url: str = "http://localhost:8001/v1",
        text_threshold: float = 0.3,
    ):
        """
        Initialize the processor router.

        Args:
            dots_ocr_url: URL to the dots.ocr vLLM service
            text_threshold: Minimum text/page ratio to consider a PDF "digital" (0.0-1.0)
        """
        self.dots_ocr_url = dots_ocr_url
        self.text_threshold = text_threshold
        self._dots_ocr = None
        self._docling = None

    @property
    def dots_ocr(self):
        """Lazy-load dots.ocr processor."""
        if self._dots_ocr is None:
            from src.nlp.processing.dots_ocr_processor import DotsOCRProcessor

            self._dots_ocr = DotsOCRProcessor(vllm_url=self.dots_ocr_url)
        return self._dots_ocr

    @property
    def docling(self):
        """Lazy-load Docling processor."""
        if self._docling is None:
            from src.nlp.processing.docling_processor import DoclingProcessor

            self._docling = DoclingProcessor()
        return self._docling

    async def route(self, file_path: str) -> ProcessingResult:
        """
        Analyze document and route to optimal processor.

        Workflow:
        1. Check file type
        2. For PDFs: analyze text layer to determine if digital or scanned
        3. Route to best processor
        4. Return result with metadata
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        start_time = time.time()

        # Route based on file type
        if suffix == ".pdf":
            result = await self._route_pdf(str(file_path))
        elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
            result = await self._route_image(str(file_path))
        elif suffix in (".html", ".htm"):
            result = await self._route_html(str(file_path))
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Add timing
        processing_time_ms = int((time.time() - start_time) * 1000)
        result.processing_time_ms = processing_time_ms

        logger.info(
            f"Routed {file_path.name} → {result.processor_used} "
            f"(confidence={result.confidence:.2f}, time={processing_time_ms}ms)"
        )

        return result

    async def _route_pdf(self, file_path: str) -> ProcessingResult:
        """Route PDF to dots.ocr or Docling based on quality analysis."""
        quality = self._analyze_pdf_quality(file_path)

        logger.info(
            f"PDF analysis: digital_score={quality['digital_score']:.2f}, "
            f"text_ratio={quality['text_ratio']:.2f}, pages={quality['page_count']}"
        )

        # If high text ratio and not too many images → use Docling (faster)
        if quality["digital_score"] > 0.7 and quality["image_density"] < 0.3:
            return await self._try_docling(file_path, "pdf", quality)

        # Otherwise use dots.ocr (better with scans/complex layouts)
        return await self._try_dots_ocr(file_path, "pdf", quality)

    async def _route_image(self, file_path: str) -> ProcessingResult:
        """Route image to dots.ocr (Docling doesn't handle images well)."""
        quality = {"type": "image", "image_density": 1.0}

        # Images → dots.ocr always
        return await self._try_dots_ocr(file_path, "image", quality)

    async def _route_html(self, file_path: str) -> ProcessingResult:
        """Route HTML to Docling."""
        quality = {"type": "html", "image_density": 0.0}

        return await self._try_docling(file_path, "html", quality)

    async def _try_docling(self, file_path: str, doc_type: str, quality: dict) -> ProcessingResult:
        """Attempt processing with Docling."""
        try:
            if doc_type == "pdf":
                result = self.docling.process_pdf(file_path)
            elif doc_type == "html":
                html_content = Path(file_path).read_text(encoding="utf-8")
                result = self.docling.process_html(html_content, source_url=str(file_path))
            else:
                result = None

            if result and result.get("markdown"):
                return ProcessingResult(
                    text=result.get("markdown", ""),
                    markdown=result.get("markdown", ""),
                    tables=result.get("tables", []),
                    processor_used="docling",
                    confidence=min(0.95, 0.7 + quality.get("digital_score", 0.0) / 10.0),
                    processing_time_ms=0,
                    metadata={
                        "quality_analysis": quality,
                        "format": doc_type,
                        "source": str(file_path),
                    },
                )
        except Exception as e:
            logger.warning(f"Docling processing failed: {e}")

        # Fallback to dots.ocr
        return await self._try_dots_ocr(file_path, doc_type, quality)

    async def _try_dots_ocr(self, file_path: str, doc_type: str, quality: dict) -> ProcessingResult:
        """Attempt processing with dots.ocr."""
        try:
            if doc_type == "pdf":
                result = self.dots_ocr.process_pdf(file_path)
            elif doc_type in ("image", "png", "jpg"):
                result = self.dots_ocr.process_image(file_path)
            else:
                result = None

            if result and result.get("markdown"):
                return ProcessingResult(
                    text=result.get("markdown", ""),
                    markdown=result.get("markdown", ""),
                    tables=result.get("tables", []),
                    processor_used=f"dots_ocr_{self.dots_ocr.mode}",
                    confidence=0.92,  # dots.ocr is highly accurate
                    processing_time_ms=0,
                    metadata={
                        "quality_analysis": quality,
                        "format": doc_type,
                        "source": str(file_path),
                        **result.get("metadata", {}),
                    },
                )
        except Exception as e:
            logger.warning(f"dots.ocr processing failed: {e}")

        # Both failed
        return ProcessingResult(
            text="",
            markdown="",
            tables=[],
            processor_used="none",
            confidence=0.0,
            processing_time_ms=0,
            metadata={
                "error": "All processors failed",
                "source": str(file_path),
            },
        )

    def _analyze_pdf_quality(self, file_path: str) -> dict:
        """
        Analyze PDF to determine if it's digital or scanned.

        Returns dict with:
        - text_ratio: Extractable text / total content (0-1)
        - digital_score: Confidence that PDF is digital (0-1)
        - page_count: Number of pages
        - image_density: Estimated proportion of images
        """
        try:
            import pypdf
        except ImportError:
            logger.warning("pypdf not installed, assuming scanned PDF")
            return {
                "text_ratio": 0.0,
                "digital_score": 0.0,
                "page_count": 0,
                "image_density": 1.0,
            }

        try:
            with open(file_path, "rb") as f:
                pdf = pypdf.PdfReader(f)
                page_count = len(pdf.pages)

                if page_count == 0:
                    return {
                        "text_ratio": 0.0,
                        "digital_score": 0.0,
                        "page_count": 0,
                        "image_density": 1.0,
                    }

                # Sample first 5 pages (or fewer if PDF is short)
                sample_pages = pdf.pages[: min(5, page_count)]
                total_chars = 0
                total_objects = 0

                for page in sample_pages:
                    text = page.extract_text()
                    total_chars += len(text) if text else 0
                    # Rough estimate: count content streams
                    total_objects += len(page["/Contents"]) if "/Contents" in page else 1

                # Digital PDFs have significant extractable text
                text_ratio = total_chars / (page_count * 1000) if total_objects > 0 else 0.0
                text_ratio = min(1.0, text_ratio)  # Clamp to [0, 1]

                # Digital score: high text ratio = high score
                digital_score = min(1.0, text_ratio)

                # Image density: rough inverse of text ratio
                image_density = 1.0 - digital_score

                return {
                    "text_ratio": text_ratio,
                    "digital_score": digital_score,
                    "page_count": page_count,
                    "image_density": image_density,
                    "sampled_pages": min(5, page_count),
                    "sampled_chars": total_chars,
                }

        except Exception as e:
            logger.warning(f"PDF quality analysis failed: {e}, assuming scanned")
            return {
                "text_ratio": 0.0,
                "digital_score": 0.0,
                "page_count": 0,
                "image_density": 1.0,
                "error": str(e),
            }
