"""Data endpoints: EUR-Lex crawl, the closed legacy upload, document processing."""

import asyncio
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, require_staff

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Data"])

from src.api.rate_limit import limiter


class CrawlTypeEnum(str, Enum):
    full_crawl = "full_crawl"
    amendment_check = "amendment_check"


class CrawlRequest(BaseModel):
    """Trigger a regulatory crawl."""

    crawl_type: CrawlTypeEnum = Field(
        default=CrawlTypeEnum.amendment_check, description="full_crawl or amendment_check"
    )
    days_back: int = Field(default=7, ge=1, le=90, description="Days to look back")


# ─── Endpoints ────────────────────────────────────────────────────


@router.post("/crawl")
@limiter.limit("2/minute")
async def trigger_crawl(
    request: Request, payload: CrawlRequest, user: CurrentUser = Depends(require_staff)
):
    """
    **Trigger a EUR-Lex regulatory crawl.**

    - `full_crawl`: Re-download and re-index all 9 core regulations
    - `amendment_check`: Check for new amendments to tracked regulations (default)

    Staff only (``require_staff``: users.is_staff on a verified email): the
    crawl re-indexes the SHARED regulatory corpus every tenant reads from, so
    no customer admin may run it.
    """
    audit_log(
        AuditAction.CRAWL_TRIGGERED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
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

            # Apply temporal freshness: mark chunks of regulations no longer in
            # force as superseded - not just count amendments.
            from src.api.app_state import get_indexer
            from src.pipeline import refresh_in_force_status

            freshness = await asyncio.to_thread(
                refresh_in_force_status, client, get_indexer(), all_celex, amendments
            )
            return {
                "status": "success",
                "message": (
                    f"Amendment check complete: {len(amendments)} amendments, "
                    f"{freshness['superseded_chunks']} chunks superseded"
                ),
                "data": {
                    "amendments_count": len(amendments),
                    "regulations_superseded": freshness["superseded_regulations"],
                    "chunks_superseded": freshness["superseded_chunks"],
                },
            }
    except Exception as e:
        logger.error("crawl_error", error=str(e))
        raise HTTPException(
            status_code=500, detail="EUR-Lex crawl failed. Check server logs for details."
        )


LEGACY_UPLOAD_GONE_DETAIL = (
    "Questo indirizzo non è più attivo: i documenti non vengono più caricati e indicizzati. "
    "Per controllare i riferimenti di legge di un documento usa POST /api/v1/documents/check: "
    "il file è letto in memoria e non viene conservato."
)


@router.post(
    "/documents/upload",
    status_code=410,
    deprecated=True,
    responses={410: {"description": "Gone: use POST /api/v1/documents/check."}},
)
async def upload_document(request: Request):
    """
    **Gone (410).** This route used to index an uploaded document into the
    search index of the organisation, where it stayed until the organisation
    was erased. It is closed: nothing is read, nothing is stored.

    To check the legal references of a document use `POST /api/v1/documents/check`:
    the file is read in memory and not kept. Text indexed by this route before it
    closed is deleted by the GDPR erasure (`POST /api/v1/gdpr/erase`).
    """
    raise HTTPException(status_code=410, detail=LEGACY_UPLOAD_GONE_DETAIL)


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
