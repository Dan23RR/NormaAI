"""
dots.ocr Document Processor - Vision-language model for complex document extraction.

dots.ocr (by rednote-hilab) is a 3B-parameter vision-language model that unifies
layout detection, text recognition, and reading order reconstruction.

Key advantages for NormaAI:
- Handles noisy scans of old EU regulations and official gazettes
- Extracts complex financial tables with 88.6% structural accuracy (TEDS)
- Preserves reading order in multi-column legal documents
- Processes signed/stamped official documents
- Multilingual support (critical for EU docs in 24 languages)

Integration architecture:
    Document → [dots.ocr] → Structured JSON (layout + text + tables)
                   ↓
              [Markdown converter] → Clean text for chunking pipeline

Deployment modes:
1. vLLM server (recommended for production - fast, supports batching)
2. HuggingFace Transformers (simpler, for dev/testing)
3. HTTP client (connect to external dots.ocr service)

Falls back to Docling → BeautifulSoup if dots.ocr is not available.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── Availability Detection ────────────────────────────────────

DOTS_OCR_AVAILABLE = False
DOTS_OCR_MODE = "unavailable"  # "local", "vllm", "unavailable"

# Check for local installation
try:
    from dots_ocr.parser import DotsOCRParser

    DOTS_OCR_AVAILABLE = True
    DOTS_OCR_MODE = "local"
    logger.info("dots.ocr available (local installation)")
except ImportError:
    pass

# Check for vLLM client
if not DOTS_OCR_AVAILABLE:
    try:
        import httpx

        DOTS_OCR_MODE = "vllm"  # Will verify connection later
        logger.info("dots.ocr client available (vLLM mode via httpx)")
    except ImportError:
        pass


class DotsOCRProcessor:
    """
    Process documents using dots.ocr for high-fidelity text extraction.

    Excels at:
    - Scanned PDFs with noise, stamps, signatures
    - Dense multi-column legal documents (EU Official Journal format)
    - Complex financial tables (annual reports, balance sheets)
    - Forms with irregular layouts (compliance questionnaires)

    Configuration:
        vllm_url: URL of running vLLM server with dots.ocr model
        model_path: Local path to dots.ocr model weights
        dpi: Target DPI for image preprocessing (default 200)
        max_pages: Maximum pages to process per document (default 100)
    """

    def __init__(
        self,
        vllm_url: str = "http://localhost:8001/v1",
        model_path: str = "",
        dpi: int = 200,
        max_pages: int = 100,
    ):
        self.vllm_url = vllm_url
        self.model_path = model_path
        self.dpi = dpi
        self.max_pages = max_pages
        self._local_parser = None
        self._vllm_available = None

    @property
    def is_available(self) -> bool:
        """Check if any dots.ocr backend is available."""
        if DOTS_OCR_MODE == "local":
            return True
        if DOTS_OCR_MODE == "vllm":
            return self._check_vllm_health()
        return False

    @property
    def mode(self) -> str:
        """Current operational mode."""
        if DOTS_OCR_MODE == "local":
            return "local"
        if self._check_vllm_health():
            return "vllm"
        return "unavailable"

    def _check_vllm_health(self) -> bool:
        """Check if vLLM server is running and healthy."""
        if self._vllm_available is not None:
            return self._vllm_available
        try:
            import httpx

            response = httpx.get(f"{self.vllm_url}/models", timeout=5.0)
            self._vllm_available = response.status_code == 200
        except Exception:
            self._vllm_available = False
        return self._vllm_available

    def process_pdf(self, pdf_path: str) -> dict | None:
        """
        Process a PDF document with dots.ocr.

        Returns:
            dict with keys:
            - markdown: Full document text in structured markdown
            - tables: List of extracted tables with structure
            - layout: Layout analysis with bounding boxes
            - metadata: Processing metadata (pages, dpi, mode)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return None

        mode = self.mode
        if mode == "local":
            return self._process_local(str(pdf_path))
        elif mode == "vllm":
            return self._process_vllm(str(pdf_path))
        else:
            logger.warning("dots.ocr not available, cannot process PDF")
            return None

    def process_image(self, image_path: str) -> dict | None:
        """
        Process a single image (scanned page, photo of document).

        Returns structured text extraction result.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return None

        mode = self.mode
        if mode == "local":
            return self._process_local(str(image_path))
        elif mode == "vllm":
            return self._process_vllm(str(image_path))
        else:
            logger.warning("dots.ocr not available, cannot process image")
            return None

    def _process_local(self, file_path: str) -> dict | None:
        """Process document using local dots.ocr installation."""
        try:
            from dots_ocr.parser import DotsOCRParser

            parser = DotsOCRParser(model_path=self.model_path or None)
            result = parser.parse(file_path)

            return self._normalize_result(result, file_path, "local")

        except Exception as e:
            logger.error(f"dots.ocr local processing failed: {e}")
            return None

    def _process_vllm(self, file_path: str) -> dict | None:
        """Process document via vLLM server running dots.ocr model."""
        try:
            import base64

            import httpx

            # Read file and encode
            file_path = Path(file_path)
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode("utf-8")

            # Determine mime type
            suffix = file_path.suffix.lower()
            mime_map = {
                ".pdf": "application/pdf",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".tiff": "image/tiff",
                ".bmp": "image/bmp",
            }
            mime_type = mime_map.get(suffix, "application/octet-stream")

            # Call vLLM chat completions API with vision
            payload = {
                "model": "rednote-hilab/dots.ocr-1.5",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{file_data}"},
                            },
                            {
                                "type": "text",
                                "text": "<ocr>",
                            },
                        ],
                    }
                ],
                "max_completion_tokens": 8192,
                "temperature": 0.0,
            }

            response = httpx.post(
                f"{self.vllm_url}/chat/completions",
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            return self._parse_ocr_output(content, str(file_path), "vllm")

        except Exception as e:
            logger.error(f"dots.ocr vLLM processing failed: {e}")
            return None

    def _normalize_result(self, raw_result: dict, file_path: str, mode: str) -> dict:
        """Normalize dots.ocr output to standard format."""
        # dots.ocr returns structured JSON with layout elements
        elements = raw_result if isinstance(raw_result, list) else raw_result.get("elements", [])

        markdown_parts = []
        tables = []

        for elem in elements:
            elem_type = elem.get("category", elem.get("type", "text"))
            text = elem.get("text", elem.get("content", ""))

            if elem_type in ("title", "section_header"):
                markdown_parts.append(f"\n## {text}\n")
            elif elem_type == "table":
                tables.append(
                    {
                        "content": text,
                        "html": elem.get("html", ""),
                        "bbox": elem.get("bbox", []),
                    }
                )
                markdown_parts.append(f"\n[TABLE]\n{text}\n")
            elif elem_type == "formula":
                markdown_parts.append(f"\n$${text}$$\n")
            elif elem_type in ("text", "paragraph", "list_item"):
                markdown_parts.append(text)
            else:
                if text:
                    markdown_parts.append(text)

        return {
            "markdown": "\n\n".join(markdown_parts),
            "tables": tables,
            "layout": elements,
            "metadata": {
                "source": file_path,
                "processor": f"dots_ocr_{mode}",
                "dpi": self.dpi,
                "elements_count": len(elements),
                "tables_count": len(tables),
            },
        }

    def _parse_ocr_output(self, content: str, file_path: str, mode: str) -> dict:
        """Parse raw OCR text output into structured format."""
        # Try to parse as JSON first (dots.ocr structured output)
        try:
            parsed = json.loads(content)
            return self._normalize_result(parsed, file_path, mode)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: treat as plain text/markdown
        return {
            "markdown": content,
            "tables": [],
            "layout": [],
            "metadata": {
                "source": file_path,
                "processor": f"dots_ocr_{mode}",
                "dpi": self.dpi,
                "output_format": "raw_text",
            },
        }


# ─── Unified Document Processor ────────────────────────────────


class UnifiedDocumentProcessor:
    """
    Smart document processing pipeline that routes to the best processor.

    Routing logic:
    - Scanned PDFs / images → dots.ocr (layout + OCR)
    - Clean digital PDFs → Docling (structure-preserving)
    - HTML → Docling → BeautifulSoup fallback
    - If dots.ocr unavailable → Docling for everything
    - If both unavailable → BeautifulSoup fallback

    This dual-engine approach gives NormaAI best-in-class document ingestion:
    - dots.ocr handles the hard cases (scans, stamps, complex tables)
    - Docling handles the easy cases efficiently (clean digital docs)
    """

    def __init__(
        self,
        dots_ocr_url: str = "http://localhost:8001/v1",
        prefer_dots_ocr: bool = True,
    ):
        self.dots_ocr = DotsOCRProcessor(vllm_url=dots_ocr_url)
        self.prefer_dots_ocr = prefer_dots_ocr

        # Lazy-init Docling
        self._docling = None

    @property
    def docling(self):
        """Lazy-load Docling processor."""
        if self._docling is None:
            from src.nlp.processing.docling_processor import DoclingProcessor

            self._docling = DoclingProcessor()
        return self._docling

    @property
    def available_engines(self) -> list[str]:
        """List of available processing engines."""
        engines = []
        if self.dots_ocr.is_available:
            engines.append(f"dots_ocr ({self.dots_ocr.mode})")
        if self.docling.is_available:
            engines.append("docling")
        engines.append("beautifulsoup (fallback)")
        return engines

    def process(
        self,
        file_path: str,
        force_engine: str | None = None,
    ) -> dict:
        """
        Process any document, routing to the best available engine.

        Args:
            file_path: Path to PDF, image, or HTML file
            force_engine: Override routing ("dots_ocr", "docling", "fallback")

        Returns:
            Standardized dict: {markdown, tables, layout, metadata}
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        # Determine document type
        is_image = suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp")
        is_pdf = suffix == ".pdf"
        is_html = suffix in (".html", ".htm")

        logger.info(
            f"Processing {path.name} | type={'image' if is_image else suffix} | "
            f"engines={', '.join(self.available_engines)}"
        )

        # Force specific engine
        if force_engine == "dots_ocr":
            return self._try_dots_ocr(file_path) or self._empty_result(
                file_path, "dots_ocr forced but failed"
            )
        elif force_engine == "docling":
            return self._try_docling(file_path) or self._empty_result(
                file_path, "docling forced but failed"
            )

        # Smart routing
        if is_image:
            # Images → dots.ocr only (Docling doesn't handle images well)
            result = self._try_dots_ocr(file_path)
            if result:
                return result
            return self._empty_result(file_path, "No image processor available. Install dots.ocr.")

        elif is_pdf:
            if self.prefer_dots_ocr and self.dots_ocr.is_available:
                # Try dots.ocr first for PDFs (better with scans)
                result = self._try_dots_ocr(file_path)
                if result:
                    return result

            # Fallback to Docling
            result = self._try_docling_pdf(file_path)
            if result:
                return result

            # Last resort: dots.ocr if we haven't tried it
            if not self.prefer_dots_ocr and self.dots_ocr.is_available:
                result = self._try_dots_ocr(file_path)
                if result:
                    return result

            return self._empty_result(
                file_path, "No PDF processor available. Install docling or dots.ocr."
            )

        elif is_html:
            # HTML → always Docling/BS4 (dots.ocr is for visual docs)
            result = self._try_docling_html(file_path)
            if result:
                return result
            return self._empty_result(file_path, "HTML processing failed")

        else:
            return self._empty_result(file_path, f"Unsupported file type: {suffix}")

    def _try_dots_ocr(self, file_path: str) -> dict | None:
        """Attempt processing with dots.ocr."""
        if not self.dots_ocr.is_available:
            return None
        try:
            suffix = Path(file_path).suffix.lower()
            if suffix == ".pdf":
                return self.dots_ocr.process_pdf(file_path)
            else:
                return self.dots_ocr.process_image(file_path)
        except Exception as e:
            logger.warning(f"dots.ocr processing failed: {e}")
            return None

    def _try_docling_pdf(self, file_path: str) -> dict | None:
        """Attempt PDF processing with Docling."""
        if not self.docling.is_available:
            return None
        try:
            return self.docling.process_pdf(file_path)
        except Exception as e:
            logger.warning(f"Docling PDF processing failed: {e}")
            return None

    def _try_docling_html(self, file_path: str) -> dict | None:
        """Attempt HTML processing with Docling/BS4."""
        try:
            html_content = Path(file_path).read_text(encoding="utf-8")
            return self.docling.process_html(html_content, source_url=str(file_path))
        except Exception as e:
            logger.warning(f"HTML processing failed: {e}")
            return None

    def _empty_result(self, file_path: str, reason: str) -> dict:
        """Return empty result with error info."""
        logger.error(f"Document processing failed: {reason}")
        return {
            "markdown": "",
            "tables": [],
            "layout": [],
            "metadata": {
                "source": str(file_path),
                "processor": "none",
                "error": reason,
            },
        }
