"""Intelligence endpoints: Q&A, Gap Analysis, Monitor.

Tenant isolation enforced via:
- org_id-scoped cache keys (prevents cross-tenant cache leakage)
- org_id in all audit log entries
- org_id in response metadata for client-side verification
- Circuit breaker for graceful LLM degradation
"""

import json
import traceback
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.streaming.generators import (
    gap_analysis_stream_generator,
    monitor_stream_generator,
    qa_stream_generator,
)
from src.api.streaming.sse import sse_generator
from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user
from src.config import get_settings
from src.resilience import ServiceUnavailableError

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Intelligence"])

from src.api.rate_limit import limiter
from src.api.schemas import FrameworkEnum


class CompanyProfile(BaseModel):
    """Client company profile for personalized analysis."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Company name",
        json_schema_extra={"examples": ["Acme Srl"]},
    )
    sector: str = Field(
        default="", description="Industry sector", json_schema_extra={"examples": ["Manufacturing"]}
    )
    employee_count: int = Field(
        default=0, ge=0, description="Number of employees", json_schema_extra={"examples": [2500]}
    )
    revenue_eur: int = Field(
        default=0,
        ge=0,
        description="Annual revenue in EUR",
        json_schema_extra={"examples": [200000000]},
    )
    jurisdictions: list[str] = Field(
        default_factory=list,
        description="EU country codes",
        json_schema_extra={"examples": [["IT", "DE"]]},
    )
    applicable_frameworks: list[str] = Field(
        default_factory=list,
        description="Tracked frameworks",
        json_schema_extra={"examples": [["CSRD", "CSDDD"]]},
    )
    existing_documents: str = Field(default="", description="Summary of existing compliance docs")


class LanguageEnum(str, Enum):
    EN = "en"
    IT = "it"
    DE = "de"
    FR = "fr"


class QARequest(BaseModel):
    """Q&A request payload."""

    question: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Question about EU regulations",
        json_schema_extra={
            "examples": ["Does my company with 800 employees need to file a CSRD report?"]
        },
    )
    company_profile: CompanyProfile | None = None
    language: LanguageEnum = Field(default=LanguageEnum.EN, description="Response language")
    conversation_id: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Conversation ID for multi-turn context",
    )
    stream: bool = Field(default=False, description="Enable SSE streaming response")
    enable_cove: bool = Field(default=False, description="Enable CoVe verification pipeline")


class GapAnalysisRequest(BaseModel):
    """Gap analysis request payload."""

    framework: FrameworkEnum = Field(
        ..., description="Framework to assess", json_schema_extra={"examples": ["CSRD"]}
    )
    company_profile: CompanyProfile
    stream: bool = Field(default=False, description="Enable SSE streaming response")
    enable_cove: bool = Field(default=False, description="Enable CoVe verification pipeline")


class MonitorRequest(BaseModel):
    """Regulatory change monitoring request."""

    regulation_change: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Description of the regulatory change to analyze",
        json_schema_extra={
            "examples": ["The Omnibus I Package raised CSRD threshold from 250 to 1000 employees"]
        },
    )
    company_profile: CompanyProfile
    stream: bool = Field(default=False, description="Enable SSE streaming response")
    enable_cove: bool = Field(default=False, description="Enable CoVe verification pipeline")


# ─── Dependency checks ────────────────────────────────────────────


def _require_qdrant(request: Request):
    """Raise 503 if Qdrant is not available."""
    from src.api.app_state import app_state

    if not app_state.qdrant_available:
        raise HTTPException(
            status_code=503,
            detail="Qdrant vector database is not available. Check Docker services.",
        )


def _require_llm():
    """Raise 503 if LLM is not configured."""
    from src.api.app_state import app_state

    if not app_state.llm_available:
        settings = get_settings()
        key_name = "GOOGLE_API_KEY" if settings.llm_provider == "gemini" else "ANTHROPIC_API_KEY"
        raise HTTPException(
            status_code=503,
            detail=f"{key_name} not configured. Add it to your .env file to use intelligence endpoints.",
        )


def _build_metadata(
    user: CurrentUser,
    *,
    cached: bool = False,
    framework: str | None = None,
) -> dict:
    """Build response metadata with tenant context."""
    settings = get_settings()
    meta = {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": settings.active_model,
        "org_id": str(user.org_id),
        "ai_generated": True,
        "disclaimer": "AI-assisted analysis. Not legal advice. Expert review recommended.",
    }
    # Corpus freshness signal: the regulatory corpus is frozen between manual
    # re-seeds, so tell the client how current the law is (empty => not configured).
    if settings.corpus_as_of:
        meta["corpus_as_of"] = settings.corpus_as_of
    if cached:
        meta["cached"] = True
    if framework:
        meta["framework"] = framework
    return meta


# ─── SSE Streaming Helper ────────────────────────────────────────


async def _sse_stream(result: dict) -> AsyncIterator[str]:
    """Stream a complete result as Server-Sent Events.

    This is the SSE infrastructure stub - sends the full result
    in a single data event. When live LLM streaming is enabled,
    this will be replaced with token-by-token streaming from
    LangGraph's astream_events().
    """
    yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ─── Endpoints ────────────────────────────────────────────────────


@router.post("/qa")
@limiter.limit("10/minute")
async def ask_question(
    request: Request, payload: QARequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Ask a question about EU regulations.**

    Returns an AI-generated answer grounded in the regulatory knowledge base,
    with precise citations to specific articles and paragraphs.

    Set `stream: true` in the request body to receive Server-Sent Events.

    Requires authentication. Cache is org-scoped for tenant isolation.
    """
    _require_qdrant(request)
    _require_llm()

    org_id = str(user.org_id)

    audit_log(
        AuditAction.QA_QUERY,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/qa",
        detail=payload.question[:80],
    )

    try:
        from src.agents.graph import arun_qa

        profile_dict = payload.company_profile.model_dump() if payload.company_profile else None

        # Check org-scoped cache
        try:
            from src.cache import response_cache

            # CoVe-verified answers differ from the cached non-CoVe draft and the
            # cache key does not include the flag, so bypass the cache when CoVe
            # is requested (avoids cross-serving a verified vs unverified result).
            cached = (
                None
                if payload.enable_cove
                else await response_cache.get("qa", payload.question, profile_dict, org_id=org_id)
            )
            if cached:
                response_body = {
                    "status": "success",
                    "data": cached,
                    "metadata": _build_metadata(user, cached=True),
                }
                if payload.stream:
                    return StreamingResponse(
                        _sse_stream(response_body),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                    )
                return response_body
        except Exception as cache_err:
            logger.debug("cache_get_failed", endpoint="qa", error=str(cache_err))

        result = await arun_qa(
            payload.question, profile_dict, cove_enabled=payload.enable_cove, org_id=org_id
        )

        # Cache with org isolation (skip when CoVe ran - see cache-read note above)
        try:
            from src.cache import response_cache

            if not payload.enable_cove:
                await response_cache.set(
                    "qa", payload.question, result, profile_dict, org_id=org_id
                )
        except Exception as cache_err:
            logger.debug("cache_set_failed", endpoint="qa", error=str(cache_err))

        response_body = {
            "status": "success",
            "data": result,
            "metadata": _build_metadata(user),
        }

        if payload.stream:
            return StreamingResponse(
                _sse_stream(response_body),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        return response_body

    except HTTPException:
        raise
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(
            "qa_error", error=str(e), error_type=type(e).__name__, traceback=traceback.format_exc()
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during Q&A analysis. Please try again.",
        )


@router.post("/gap-analysis")
@limiter.limit("5/minute")
async def run_gap_analysis_endpoint(
    request: Request, payload: GapAnalysisRequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Run compliance gap analysis for a specific EU framework.**

    Analyzes the company profile against framework requirements and returns:
    - Qualitative compliance assessment (High/Medium/Requires Review)
    - Per-requirement status
    - Gap descriptions with remediation effort estimates
    - Prioritized recommendations

    Requires authentication. Cache is org-scoped for tenant isolation.
    """
    _require_qdrant(request)
    _require_llm()

    org_id = str(user.org_id)

    audit_log(
        AuditAction.GAP_ANALYSIS,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/gap-analysis",
        detail=f"{payload.framework.value} for {payload.company_profile.name}",
    )

    try:
        from src.agents.graph import arun_gap_analysis

        profile_dict = payload.company_profile.model_dump()

        # Check org-scoped cache
        try:
            from src.cache import response_cache

            cached = (
                None
                if payload.enable_cove
                else await response_cache.get(
                    "gap_analysis", payload.framework.value, profile_dict, org_id=org_id
                )
            )
            if cached:
                return {
                    "status": "success",
                    "data": cached,
                    "metadata": _build_metadata(
                        user, cached=True, framework=payload.framework.value
                    ),
                }
        except Exception as cache_err:
            logger.debug("cache_get_failed", endpoint="gap_analysis", error=str(cache_err))

        result = await arun_gap_analysis(
            payload.framework.value, profile_dict, cove_enabled=payload.enable_cove, org_id=org_id
        )

        # Cache with org isolation (skip when CoVe ran)
        try:
            from src.cache import response_cache

            if not payload.enable_cove:
                await response_cache.set(
                    "gap_analysis", payload.framework.value, result, profile_dict, org_id=org_id
                )
        except Exception as cache_err:
            logger.debug("cache_set_failed", endpoint="gap_analysis", error=str(cache_err))

        return {
            "status": "success",
            "data": result,
            "metadata": _build_metadata(user, framework=payload.framework.value),
        }
    except HTTPException:
        raise
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(
            "gap_analysis_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during gap analysis. Please try again.",
        )


@router.post("/monitor")
@limiter.limit("10/minute")
async def monitor_change(
    request: Request, payload: MonitorRequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Analyze the impact of a regulatory change on a specific company.**

    Returns:
    - Applicability assessment (YES / NO / CONDITIONAL)
    - Urgency level (CRITICAL to INFORMATIONAL)
    - Impact summary in plain business language
    - Required actions with effort estimates
    - Cross-framework implications

    Requires authentication. Cache is org-scoped for tenant isolation.
    """
    _require_qdrant(request)
    _require_llm()

    org_id = str(user.org_id)

    audit_log(
        AuditAction.MONITOR_CHECK,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/monitor",
        detail=f"Monitor for {payload.company_profile.name}",
    )

    try:
        from src.agents.graph import arun_monitor_check

        profile_dict = payload.company_profile.model_dump()

        # Check org-scoped cache
        try:
            from src.cache import response_cache

            cached = (
                None
                if payload.enable_cove
                else await response_cache.get(
                    "monitor", payload.regulation_change, profile_dict, org_id=org_id
                )
            )
            if cached:
                return {
                    "status": "success",
                    "data": cached,
                    "metadata": _build_metadata(user, cached=True),
                }
        except Exception as cache_err:
            logger.debug("cache_get_failed", endpoint="monitor", error=str(cache_err))

        result = await arun_monitor_check(
            payload.regulation_change, profile_dict, cove_enabled=payload.enable_cove, org_id=org_id
        )

        # Cache with org isolation (skip when CoVe ran)
        try:
            from src.cache import response_cache

            if not payload.enable_cove:
                await response_cache.set(
                    "monitor", payload.regulation_change, result, profile_dict, org_id=org_id
                )
        except Exception as cache_err:
            logger.debug("cache_set_failed", endpoint="monitor", error=str(cache_err))

        return {
            "status": "success",
            "data": result,
            "metadata": _build_metadata(user),
        }
    except HTTPException:
        raise
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(
            "monitor_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during monitor analysis. Please try again.",
        )


# ─── SSE Streaming Endpoints ──────────────────────────────────────


@router.post("/qa/stream")
@limiter.limit("10/minute")
async def ask_question_stream(
    request: Request, payload: QARequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Ask a question about EU regulations with SSE streaming.**

    Returns a stream of Server-Sent Events containing:
    - Phase change events (draft → planning → verification → revision → validation)
    - Token events (incremental response text)
    - Citation events (regulatory references with verification status)
    - Verification events (if CoVe is enabled)
    - Completion event with metadata

    Streaming is real-time and bypasses cache. Set `enable_cove: true` to enable
    Chain-of-Verification anti-hallucination pipeline.

    Requires authentication.
    """
    _require_qdrant(request)
    _require_llm()

    org_id = str(user.org_id)

    audit_log(
        AuditAction.QA_QUERY,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/qa/stream",
        detail=payload.question[:80],
    )

    try:
        profile_dict = payload.company_profile.model_dump() if payload.company_profile else None

        # Streaming bypasses cache by design (real-time responses)
        return StreamingResponse(
            sse_generator(
                qa_stream_generator(
                    payload.question,
                    profile_dict,
                    user,
                    payload.enable_cove,
                )
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(
            "qa_stream_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during Q&A streaming. Please try again.",
        )


@router.post("/gap-analysis/stream")
@limiter.limit("5/minute")
async def run_gap_analysis_stream(
    request: Request, payload: GapAnalysisRequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Run compliance gap analysis with SSE streaming.**

    Returns a stream of Server-Sent Events containing analysis progress and results.
    Set `enable_cove: true` to verify gap analysis with Chain-of-Verification.

    Requires authentication.
    """
    _require_qdrant(request)
    _require_llm()

    org_id = str(user.org_id)

    audit_log(
        AuditAction.GAP_ANALYSIS,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/gap-analysis/stream",
        detail=f"{payload.framework.value} for {payload.company_profile.name}",
    )

    try:
        profile_dict = payload.company_profile.model_dump()

        # Streaming bypasses cache by design
        return StreamingResponse(
            sse_generator(
                gap_analysis_stream_generator(
                    payload.framework.value,
                    profile_dict,
                    user,
                    payload.enable_cove,
                )
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(
            "gap_analysis_stream_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during gap analysis streaming. Please try again.",
        )


@router.post("/monitor/stream")
@limiter.limit("10/minute")
async def monitor_change_stream(
    request: Request, payload: MonitorRequest, user: CurrentUser = Depends(get_current_user)
):
    """
    **Analyze regulatory change impact with SSE streaming.**

    Returns a stream of Server-Sent Events containing impact analysis progress.
    Set `enable_cove: true` to verify applicability and urgency with Chain-of-Verification.

    Requires authentication.
    """
    _require_qdrant(request)
    _require_llm()

    org_id = str(user.org_id)

    audit_log(
        AuditAction.MONITOR_CHECK,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/monitor/stream",
        detail=f"Monitor for {payload.company_profile.name}",
    )

    try:
        profile_dict = payload.company_profile.model_dump()

        # Streaming bypasses cache by design
        return StreamingResponse(
            sse_generator(
                monitor_stream_generator(
                    payload.regulation_change,
                    profile_dict,
                    user,
                    payload.enable_cove,
                )
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(
            "monitor_stream_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during monitor streaming. Please try again.",
        )
