"""Data endpoints: EUR-Lex crawl, document upload, document processing."""

import asyncio
import re
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Data"])

from src.api.rate_limit import limiter
from src.api.schemas import FrameworkEnum


class CrawlTypeEnum(str, Enum):
    full_crawl = "full_crawl"
    amendment_check = "amendment_check"


class CrawlRequest(BaseModel):
    """Trigger a regulatory crawl."""

    crawl_type: CrawlTypeEnum = Field(
        default=CrawlTypeEnum.amendment_check, description="full_crawl or amendment_check"
    )
    days_back: int = Field(default=7, ge=1, le=90, description="Days to look back")


# ─── Dependency checks ────────────────────────────────────────────


def _require_qdrant():
    from src.api.app_state import app_state

    if not app_state.qdrant_available:
        raise HTTPException(status_code=503, detail="Qdrant vector database is not available.")


# ─── Endpoints ────────────────────────────────────────────────────


@router.post("/crawl")
@limiter.limit("2/minute")
async def trigger_crawl(
    request: Request, payload: CrawlRequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Trigger a EUR-Lex regulatory crawl.**

    - `full_crawl`: Re-download and re-index all 9 core regulations
    - `amendment_check`: Check for new amendments to tracked regulations (default)

    Requires authentication.
    """
    audit_log(
        AuditAction.CRAWL_TRIGGERED,
        user_id=str(user.user_id) if user else None,
        org_id=str(user.org_id) if user else None,
        ip_address=get_client_ip(request),
        resource="/api/v1/crawl",
        detail=f"{payload.crawl_type.value}, days_back={payload.days_back}",
    )

    try:
        from src.crawler.eurlex.client import CORE_FRAMEWORKS, EurLexClient

        client = EurLexClient()

        if payload.crawl_type == CrawlTypeEnum.full_crawl:
            regulations = await asyncio.to_thread(client.crawl_all_core_frameworks)
            return {
                "status": "success",
                "message": f"Full crawl complete: {len(regulations)} regulations processed",
                "data": {
                    "regulations_count": len(regulations),
                    "frameworks": list(set(r.framework for r in regulations)),
                },
            }
        else:
            all_celex = []
            for celex_map in CORE_FRAMEWORKS.values():
                all_celex.extend(celex_map.keys())

            amendments = await asyncio.to_thread(client.check_for_new_amendments, all_celex)
            return {
                "status": "success",
                "message": f"Amendment check complete: {len(amendments)} amendments found",
                "data": {"amendments_count": len(amendments)},
            }
    except Exception as e:
        logger.error("crawl_error", error=str(e))
        raise HTTPException(
            status_code=500, detail="EUR-Lex crawl failed. Check server logs for details."
        )


@router.post("/documents/upload")
@limiter.limit("5/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Document to process (PDF, HTML, PNG, JPEG)"),
    framework: FrameworkEnum | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Upload and process a compliance document.**

    Supports PDF, HTML, PNG, JPEG, TIFF files.
    The document will be processed through the NLP pipeline:
    1. Text extraction (dots.ocr / Docling / BeautifulSoup)
    2. Legal chunking (article/section-aware)
    3. Contextual enrichment
    4. Vector indexing into Qdrant

    Requires authentication.
    """
    _require_qdrant()

    allowed_extensions = {".pdf", ".html", ".htm", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    safe_filename = (
        re.sub(r"[^\w.\-]", "_", file.filename or "upload") if file.filename else "upload"
    )
    file_ext = ""
    if safe_filename and "." in safe_filename:
        file_ext = "." + safe_filename.rsplit(".", 1)[-1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    max_size = 50 * 1024 * 1024
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large. Maximum size: 50MB")

    audit_log(
        AuditAction.DOCUMENT_UPLOAD,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource="/api/v1/documents/upload",
        detail=f"{safe_filename} ({len(content)} bytes)",
        extra={"content_type": file.content_type},
    )

    try:
        import os
        import tempfile

        suffix = file_ext or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            from src.pipeline import IngestionPipeline

            pipeline = IngestionPipeline()
            fw_value = framework.value if framework else None
            result = await asyncio.to_thread(
                pipeline.process_document,
                tmp_path,
                framework=fw_value,
                org_id=str(user.org_id),  # tenant-scope the upload (SEC-01)
            )

            return {
                "status": "success",
                "message": f"Document processed: {safe_filename}",
                "data": {
                    "filename": safe_filename,
                    "size_bytes": len(content),
                    "chunks_indexed": result.get("chunks_indexed", 0)
                    if isinstance(result, dict)
                    else 0,
                    "framework": fw_value,
                },
            }
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logger.error("document_upload_error", error=str(e), filename=safe_filename)
        raise HTTPException(
            status_code=500, detail="Document processing failed. Check server logs for details."
        )


@router.get("/processors")
async def get_processor_status():
    """
    **Check available document processing engines.**

    Returns which OCR / document processors are available.
    Public endpoint (no authentication required).
    """
    try:
        from src.nlp.processing.dots_ocr_processor import UnifiedDocumentProcessor

        processor = UnifiedDocumentProcessor()
        return {
            "status": "success",
            "engines": processor.available_engines,
            "dots_ocr": {
                "available": processor.dots_ocr.is_available,
                "mode": processor.dots_ocr.mode,
            },
            "docling": {
                "available": processor.docling.is_available,
            },
        }
    except Exception as e:
        logger.warning("processor_status_check_failed", error=str(e))
        return {
            "status": "degraded",
            "engines": ["beautifulsoup (fallback)"],
        }
