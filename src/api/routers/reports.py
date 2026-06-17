"""Report generation endpoints: PDF gap analysis and executive summary reports."""

import asyncio
import io
import traceback

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.rate_limit import limiter
from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Reports"])


# ---- Request / Response Models -------------------------------------------


# Shared across routers - single source of truth (includes CRA).
from src.api.schemas import FrameworkEnum  # noqa: E402


class CompanyProfile(BaseModel):
    """Client company profile for personalised analysis."""

    name: str = Field(..., min_length=1, max_length=200, description="Company name")
    sector: str = Field(default="", description="Industry sector")
    employee_count: int = Field(default=0, ge=0, description="Number of employees")
    revenue_eur: int = Field(default=0, ge=0, description="Annual revenue in EUR")
    jurisdictions: list[str] = Field(default_factory=list, description="EU country codes")
    applicable_frameworks: list[str] = Field(default_factory=list, description="Tracked frameworks")
    existing_documents: str = Field(default="", description="Summary of existing compliance docs")


class GapReportRequest(BaseModel):
    """Request to generate a single-framework gap analysis PDF."""

    framework: FrameworkEnum = Field(..., description="EU framework to assess")
    company_profile: CompanyProfile


class ExecutiveSummaryRequest(BaseModel):
    """Request to generate a multi-framework executive summary PDF."""

    frameworks: list[FrameworkEnum] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="List of frameworks to include in the summary",
    )
    company_profile: CompanyProfile


class ReportHistoryItem(BaseModel):
    """Metadata for a previously generated report."""

    report_id: str
    report_type: str
    framework: str | None = None
    company_name: str
    generated_at: str
    overall_score: float | None = None


# ---- Dependency checks ---------------------------------------------------


def _require_services(request: Request) -> None:
    """Raise 503 if LLM or Qdrant are unavailable (needed for report generation)."""
    from src.api.app_state import app_state
    from src.config import get_settings

    if not app_state.qdrant_available:
        raise HTTPException(
            status_code=503,
            detail="Qdrant vector database is not available. Report generation requires the knowledge base.",
        )
    if not app_state.llm_available:
        settings = get_settings()
        key_name = "GOOGLE_API_KEY" if settings.llm_provider == "gemini" else "ANTHROPIC_API_KEY"
        raise HTTPException(
            status_code=503,
            detail=f"{key_name} not configured. Report generation requires an active LLM provider.",
        )


# ---- Endpoints -----------------------------------------------------------


@router.post("/reports/gap-analysis")
@limiter.limit("3/minute")
async def generate_gap_report(
    request: Request,
    payload: GapReportRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Generate a PDF gap analysis report for a single EU framework.**

    Runs the AI gap analysis agent, then renders results into a professional
    PDF report with requirements table, risk matrix, and recommendations.

    Returns the PDF as a downloadable file.

    Rate limit: 3 per minute (reports are computationally expensive).
    Requires authentication.
    """
    _require_services(request)

    audit_log(
        AuditAction.DATA_EXPORT,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource="/api/v1/reports/gap-analysis",
        detail=f"PDF report: {payload.framework.value} for {payload.company_profile.name}",
    )

    try:
        # Run gap analysis via the agent graph
        from src.agents.graph import arun_gap_analysis

        profile_dict = payload.company_profile.model_dump()
        gap_data = await arun_gap_analysis(payload.framework.value, profile_dict)

        # Check for agent errors
        if isinstance(gap_data, dict) and gap_data.get("error"):
            logger.warning(
                "gap_analysis_returned_error",
                framework=payload.framework.value,
                error=gap_data["error"],
            )
            raise HTTPException(
                status_code=502,
                detail=f"Gap analysis failed: {gap_data['error']}",
            )

        # Normalise gap_data: ensure it has the expected structure
        gap_data = _normalise_gap_data(gap_data, payload.framework.value)

        # Generate PDF
        from src.reports.generator import ComplianceReportGenerator

        generator = ComplianceReportGenerator()
        pdf_bytes = await asyncio.to_thread(
            generator.generate_gap_report,
            company_name=payload.company_profile.name,
            framework=payload.framework.value,
            gap_data=gap_data,
            company_profile=profile_dict,
        )

        # Build safe filename
        safe_name = payload.company_profile.name.replace(" ", "_")[:30]
        filename = f"NormaAI_{payload.framework.value}_Gap_Report_{safe_name}.pdf"

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "report_generation_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during report generation. Please try again.",
        )


@router.post("/reports/executive-summary")
@limiter.limit("1/minute")
async def generate_executive_summary(
    request: Request,
    payload: ExecutiveSummaryRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Generate a multi-framework executive summary PDF.**

    Runs gap analysis for each requested framework, then consolidates
    results into a single executive overview report.

    Rate limit: 1 per minute (multiple LLM calls required).
    Requires authentication.
    """
    _require_services(request)

    frameworks_str = ", ".join(f.value for f in payload.frameworks)
    audit_log(
        AuditAction.DATA_EXPORT,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource="/api/v1/reports/executive-summary",
        detail=f"Executive summary: [{frameworks_str}] for {payload.company_profile.name}",
    )

    try:
        from src.agents.graph import arun_gap_analysis

        profile_dict = payload.company_profile.model_dump()

        # Run gap analysis for each framework concurrently
        tasks = [arun_gap_analysis(fw.value, profile_dict) for fw in payload.frameworks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        frameworks_data: list[dict] = []
        errors: list[str] = []

        for fw, result in zip(payload.frameworks, results, strict=False):
            if isinstance(result, Exception):
                logger.warning(
                    "executive_summary_framework_error",
                    framework=fw.value,
                    error=str(result),
                )
                errors.append(f"{fw.value}: {str(result)}")
                continue

            if isinstance(result, dict) and result.get("error"):
                errors.append(f"{fw.value}: {result['error']}")
                continue

            normalised = _normalise_gap_data(result, fw.value)
            frameworks_data.append(normalised)

        if not frameworks_data:
            raise HTTPException(
                status_code=502,
                detail=f"All framework analyses failed: {'; '.join(errors)}",
            )

        # Generate PDF
        from src.reports.generator import ComplianceReportGenerator

        generator = ComplianceReportGenerator()
        pdf_bytes = await asyncio.to_thread(
            generator.generate_executive_summary,
            company_name=payload.company_profile.name,
            frameworks_data=frameworks_data,
        )

        safe_name = payload.company_profile.name.replace(" ", "_")[:30]
        filename = f"NormaAI_Executive_Summary_{safe_name}.pdf"

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "executive_summary_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during executive summary generation. Please try again.",
        )


@router.get("/reports/history")
@limiter.limit("20/minute")
async def get_report_history(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    **List previously generated reports for the authenticated user's organisation.**

    Returns report metadata (no PDF content) sorted by generation date descending.
    Requires authentication.
    """
    try:
        from sqlalchemy import desc, func, select

        from src.db.engine import db_manager
        from src.db.models import Assessment

        async with db_manager.session(org_id=str(user.org_id)) as session:
            # Query assessments scoped to the user's org via client relationship
            stmt = (
                select(Assessment)
                .join(Assessment.client)
                .where(Assessment.client.has(org_id=user.org_id))
                .order_by(desc(Assessment.assessed_at))
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            assessments = result.scalars().all()

            # Count total
            count_stmt = (
                select(func.count())
                .select_from(Assessment)
                .join(Assessment.client)
                .where(Assessment.client.has(org_id=user.org_id))
            )
            count_result = await session.execute(count_stmt)
            total = count_result.scalar() or 0

            items = []
            for a in assessments:
                items.append(
                    ReportHistoryItem(
                        report_id=str(a.id),
                        report_type="gap_analysis",
                        framework=a.framework,
                        company_name=a.client.name if a.client else "Unknown",
                        generated_at=a.assessed_at.isoformat() if a.assessed_at else "",
                        overall_score=a.overall_score,
                    ).model_dump()
                )

            return {
                "status": "success",
                "data": items,
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                },
            }

    except HTTPException:
        raise
    except RuntimeError as e:
        # Database not initialised
        if "not initialized" in str(e).lower():
            logger.warning("report_history_db_unavailable", error=str(e))
            return {
                "status": "success",
                "data": [],
                "pagination": {"total": 0, "limit": limit, "offset": offset},
                "warning": "Database not available. No report history.",
            }
        raise
    except Exception as e:
        logger.error("report_history_error", error=str(e), traceback=traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve report history.",
        )


# ---- Helpers -------------------------------------------------------------


def _normalise_gap_data(raw: dict, framework: str) -> dict:
    """Ensure gap_data has a consistent structure for the report generator.

    The LLM agent may return data with slightly different key names or
    missing fields. This function normalises it to the expected schema.
    """
    if not isinstance(raw, dict):
        return {
            "framework": framework,
            "overall_score": 0.0,
            "requirements": [],
            "recommendations": [],
            "confidence_score": 0.0,
        }

    normalised: dict = {
        "framework": raw.get("framework", framework),
        "overall_score": _safe_float(raw.get("overall_score", raw.get("score", 0.0))),
        "confidence_score": _safe_float(raw.get("confidence_score", 0.0)),
        "requirements": [],
        "recommendations": [],
    }

    # Normalise requirements
    raw_reqs = raw.get("requirements", raw.get("gaps", []))
    if isinstance(raw_reqs, list):
        for r in raw_reqs:
            if not isinstance(r, dict):
                continue
            normalised["requirements"].append(
                {
                    "name": str(r.get("name", r.get("requirement", "Unknown")))[:200],
                    "status": _normalise_status(r.get("status", "NON_COMPLIANT")),
                    "description": str(r.get("description", r.get("gap_description", "")))[:500],
                    "remediation": str(r.get("remediation", r.get("remediation_steps", "")))[:500],
                    "effort": _normalise_effort(
                        r.get("effort", r.get("remediation_effort", "MEDIUM"))
                    ),
                }
            )

    # Normalise recommendations
    raw_recs = raw.get("recommendations", [])
    if isinstance(raw_recs, list):
        for rec in raw_recs:
            if not isinstance(rec, dict):
                continue
            normalised["recommendations"].append(
                {
                    "priority": str(rec.get("priority", "P3"))[:4],
                    "action": str(rec.get("action", rec.get("recommendation", "")))[:300],
                    "effort": str(rec.get("effort", ""))[:20],
                    "deadline": str(rec.get("deadline", ""))[:20],
                }
            )

    return normalised


def _safe_float(value: object) -> float:
    """Safely convert a value to float, defaulting to 0.0."""
    try:
        return max(0.0, min(100.0, float(value)))
    except (ValueError, TypeError):
        return 0.0


def _normalise_status(status: object) -> str:
    """Map status strings to canonical values."""
    s = str(status).upper().strip().replace(" ", "_")
    valid = {"COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE"}
    if s in valid:
        return s
    # Fuzzy matching
    if "PARTIAL" in s:
        return "PARTIALLY_COMPLIANT"
    if "NON" in s or "NOT_COMP" in s or "GAP" in s:
        return "NON_COMPLIANT"
    if "COMP" in s or "MET" in s or "YES" in s:
        return "COMPLIANT"
    if "N/A" in s or "NOT_APP" in s:
        return "NOT_APPLICABLE"
    return "NON_COMPLIANT"


def _normalise_effort(effort: object) -> str:
    """Map effort strings to canonical values."""
    e = str(effort).upper().strip()
    if "HIGH" in e:
        return "HIGH"
    if "MED" in e:
        return "MEDIUM"
    if "LOW" in e:
        return "LOW"
    return "MEDIUM"
