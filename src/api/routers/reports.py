"""Report generation endpoints: PDF gap analysis and executive summary reports."""

import asyncio
import io
import re
import traceback

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.errors import raise_for_result
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

        # An agent error is an honest upstream HTTP error (503/502/504), with
        # the Italian detail the UI shows; the raw message is only logged.
        raise_for_result(gap_data, endpoint="reports.gap_analysis")

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


def _first_text(source: dict, *keys: str) -> str:
    """First non-empty string-ish value among ``keys`` (trimmed), else ''."""
    for key in keys:
        value = source.get(key)
        if value is None or isinstance(value, bool):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


# Priority token inside a free-text recommendation ("P1: ...", "[P2] ...", "(P3)").
_PRIORITY_TOKEN = re.compile(r"\b(P[1-4])\b", re.IGNORECASE)


def _normalise_requirement(r: dict) -> dict:
    """Map one requirement to the generator schema.

    Field names follow prompts/gap_analyst.txt (``requirement_id``,
    ``article_reference``, ``gap_description``, ``remediation_effort``,
    ``priority``) with the older ``name``/``remediation``/``effort`` spellings
    still accepted. Before this, only ``name``/``requirement`` were read, so
    every requirement in a real report was called "Unknown".
    """
    name = _first_text(r, "name", "requirement", "requirement_id", "title")
    article = _first_text(r, "article_reference", "article", "reference")
    description = _first_text(r, "description", "gap_description", "requirement_text")
    if not name:
        name = article or description[:80] or "Unknown"
    elif article and article.lower() not in name.lower():
        name = f"{name} ({article})"
    return {
        "name": name[:200],
        "status": _normalise_status(r.get("status", "NON_COMPLIANT")),
        "description": description[:500],
        "remediation": _first_text(r, "remediation", "remediation_steps", "gap_description")[:500],
        "effort": _normalise_effort(_first_text(r, "effort", "remediation_effort")),
        "article_reference": article[:100],
        "evidence": _first_text(r, "evidence")[:300],
        "priority": _first_text(r, "priority")[:4].upper(),
        "notes": _first_text(r, "notes")[:300],
    }


def _normalise_recommendation(rec: object) -> dict | None:
    """Map one recommendation (dict or the prompt's plain string) to the schema."""
    if isinstance(rec, dict):
        action = _first_text(rec, "action", "recommendation", "text", "description")
        priority = _first_text(rec, "priority")[:4].upper()
        effort = _first_text(rec, "effort")[:20]
        deadline = _first_text(rec, "deadline")[:20]
    elif isinstance(rec, str) and rec.strip():
        # prompts/gap_analyst.txt: top_recommendations is a list of strings
        # "actionable recommendation with priority and effort".
        action = rec.strip()
        match = _PRIORITY_TOKEN.search(action)
        priority = match.group(1).upper() if match else ""
        effort = ""
        deadline = ""
    else:
        return None
    if not action:
        return None
    return {
        "priority": priority,
        "action": action[:300],
        "effort": effort,
        "deadline": deadline,
    }


def _score_from_requirements(requirements: list[dict]) -> float | None:
    """Overall score per the prompt's formula when the LLM did not report one:
    (COMPLIANT + 0.5 * PARTIALLY_COMPLIANT) / (Total - NOT_APPLICABLE) * 100."""
    statuses = [r.get("status") for r in requirements]
    assessable = [s for s in statuses if s != "NOT_APPLICABLE"]
    if not assessable:
        return None
    compliant = sum(1 for s in assessable if s == "COMPLIANT")
    partial = sum(1 for s in assessable if s == "PARTIALLY_COMPLIANT")
    return round((compliant + 0.5 * partial) / len(assessable) * 100, 1)


def _normalise_gap_data(raw: dict, framework: str) -> dict:
    """Ensure gap_data has a consistent structure for the report generator.

    The field names are the ones the gap_analyst prompt actually produces
    (see prompts/gap_analyst.txt), with the older spellings still accepted.
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
        "framework": raw.get("framework") or framework,
        "overall_score": 0.0,
        "confidence_score": _safe_float(raw.get("confidence_score", 0.0)),
        "requirements": [],
        "recommendations": [],
    }

    raw_reqs = raw.get("requirements", raw.get("gaps", []))
    if isinstance(raw_reqs, list):
        normalised["requirements"] = [
            _normalise_requirement(r) for r in raw_reqs if isinstance(r, dict)
        ]

    raw_score = raw.get("overall_score", raw.get("score"))
    if raw_score is None:
        # Not reported by the model: derive it from the statuses rather than
        # printing a fake 0.0 on the cover page.
        raw_score = _score_from_requirements(normalised["requirements"])
    normalised["overall_score"] = _safe_float(raw_score if raw_score is not None else 0.0)

    raw_recs = raw.get("recommendations") or raw.get("top_recommendations") or []
    if isinstance(raw_recs, list):
        normalised["recommendations"] = [
            item for item in (_normalise_recommendation(rec) for rec in raw_recs) if item
        ]

    for key in ("assessment_date", "next_assessment_date", "status_summary"):
        if raw.get(key) is not None:
            normalised[key] = raw[key]

    return normalised


def _safe_float(value: object) -> float:
    """Safely convert a value to float, defaulting to 0.0."""
    try:
        return max(0.0, min(100.0, float(value)))
    except (ValueError, TypeError):
        return 0.0


_VALID_STATUSES = frozenset(
    {"COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE", "IN_EVOLUTION"}
)


def _normalise_status(status: object) -> str:
    """Map status strings to canonical values (the prompt's five statuses)."""
    s = str(status).upper().strip().replace(" ", "_").replace("-", "_")
    if s in _VALID_STATUSES:
        return s
    # Fuzzy matching
    if "EVOL" in s or "PENDING" in s:
        return "IN_EVOLUTION"
    if "PARTIAL" in s:
        return "PARTIALLY_COMPLIANT"
    if "N/A" in s or "NOT_APP" in s:
        return "NOT_APPLICABLE"
    if "NON" in s or "NOT_COMP" in s or "GAP" in s:
        return "NON_COMPLIANT"
    if "COMP" in s or "MET" in s or "YES" in s:
        return "COMPLIANT"
    return "NON_COMPLIANT"


# Duration like "2-3 days", "1 week", "4 settimane", "40 hours": (upper bound, unit).
_DURATION = re.compile(
    r"(\d+(?:[.,]\d+)?)(?:\s*(?:-|–|to|a)\s*(\d+(?:[.,]\d+)?))?\s*"
    r"(HOUR|HR|ORA|ORE|DAY|GIORN|WEEK|SETTIMAN|MONTH|MES)",
)


def _normalise_effort(effort: object) -> str:
    """Map effort strings to HIGH / MEDIUM / LOW.

    Accepts the canonical words and the prompt's duration estimates
    ("2-3 days", "4-6 weeks"); unknown or empty input yields '' (shown blank)
    rather than a made-up MEDIUM.
    """
    e = str(effort or "").upper().strip()
    if not e:
        return ""
    if "HIGH" in e or "ALTO" in e:
        return "HIGH"
    if "MED" in e:
        return "MEDIUM"
    if "LOW" in e or "BASSO" in e:
        return "LOW"
    match = _DURATION.search(e)
    if not match:
        return ""
    amount = float((match.group(2) or match.group(1)).replace(",", "."))
    unit = match.group(3)
    if unit.startswith(("HOUR", "HR", "ORA", "ORE")):
        return "LOW"
    if unit.startswith(("DAY", "GIORN")):
        return "LOW" if amount <= 5 else "MEDIUM"
    if unit.startswith(("WEEK", "SETTIMAN")):
        return "MEDIUM" if amount <= 2 else "HIGH"
    return "HIGH"  # months
