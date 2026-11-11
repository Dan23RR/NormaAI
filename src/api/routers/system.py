"""System endpoints: health, stats, metrics."""

import secrets
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from src.api.app_state import app_state
from src.api.middleware import metrics
from src.auth.dependencies import CurrentUser, get_current_user, get_optional_user, require_role
from src.config import get_settings

logger = structlog.get_logger()

router = APIRouter(tags=["System"])

# ─── Corpus freshness ─────────────────────────────────────────────
# Written by the nightly job `python -m src.pipeline --action check-freshness`
# (src.pipeline.corpus_freshness), which compares the version of each tracked EU
# act in the corpus with the latest one CELLAR lists.

FRESHNESS_UNKNOWN: dict[str, Any] = {"status": "unknown", "checked_at": None, "outdated": []}
# /api/v1/stats is public and polled: one read of the stored outcome a minute.
_FRESHNESS_TTL_SECONDS = 60.0
_freshness_cache: tuple[float, dict[str, Any]] | None = None


def _public_freshness(value: Any) -> dict[str, Any]:
    """The stored outcome in the shape of the `freshness` field of the stats."""
    if not isinstance(value, dict):
        return dict(FRESHNESS_UNKNOWN)
    outdated = [
        {
            "celex": entry.get("celex"),
            "indexed": entry.get("indexed"),
            "latest": entry.get("latest"),
            "langs": list(entry.get("langs") or []),
        }
        for entry in value.get("outdated") or []
        if isinstance(entry, dict)
    ]
    return {
        "status": str(value.get("status") or "unknown"),
        "checked_at": value.get("checked_at"),
        "outdated": outdated,
        "missing": [str(celex) for celex in value.get("missing") or []],
        "unknown": [str(celex) for celex in value.get("unknown") or []],
    }


async def corpus_freshness() -> dict[str, Any]:
    """Outcome of the last freshness check, or "unknown" when there is none.

    Never raises: the stats must answer also when the database does not.
    """
    global _freshness_cache
    now = time.monotonic()
    if _freshness_cache is not None and now - _freshness_cache[0] < _FRESHNESS_TTL_SECONDS:
        return dict(_freshness_cache[1])
    value: Any = None
    try:
        from src.db.engine import db_manager
        from src.db.models import CORPUS_FRESHNESS_KEY, SystemState

        async with db_manager.session() as session:
            result = await session.execute(
                select(SystemState.value).where(SystemState.key == CORPUS_FRESHNESS_KEY)
            )
            value = result.scalar_one_or_none()
    except Exception as e:  # noqa: BLE001 - no database, no table yet: unknown
        logger.debug("freshness_read_failed", error=type(e).__name__)
    freshness = _public_freshness(value)
    _freshness_cache = (now, freshness)
    return dict(freshness)


async def require_scrape_auth(request: Request) -> None:
    """Authorize the Prometheus scrape endpoint.

    Accepts EITHER the static PROMETHEUS_BEARER_TOKEN (what the bundled
    Prometheus presents - a static token can never be an admin JWT, which
    is why admin-JWT-only auth here would break scraping entirely) OR a
    valid admin JWT, so a human operator can still curl the endpoint.
    """
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    settings = get_settings()

    if (
        settings.prometheus_bearer_token
        and token
        and secrets.compare_digest(token, settings.prometheus_bearer_token)
    ):
        return

    # Fall back to admin JWT (raises 401/403 on failure).
    from fastapi.security import HTTPAuthorizationCredentials

    from src.auth.dependencies import get_current_user

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/api/v1/stats")
async def get_stats(user: CurrentUser | None = Depends(get_optional_user)):
    stats = {
        "status": "healthy",
        "version": "0.3.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "qdrant_available": app_state.qdrant_available,
        "llm_available": app_state.llm_available,
    }

    if user and hasattr(user, "is_admin") and user.is_admin:
        settings = get_settings()
        stats["environment"] = settings.app_env
        stats["llm_provider"] = settings.llm_provider
        stats["llm_model"] = settings.active_model
        stats["metrics"] = metrics.summary()

    if app_state.indexer and app_state.qdrant_available:
        try:
            qdrant_stats = app_state.indexer.get_collection_stats()
            stats["qdrant"] = qdrant_stats
            # Corpus metadata point written by the seed: the date the UI shows
            # as "Corpus al ...". Missing on collections seeded before it existed.
            corpus = app_state.indexer.get_corpus_info()
            if isinstance(corpus, dict):
                stats["corpus_as_of"] = corpus.get("corpus_as_of")
                stats["corpus"] = {
                    key: corpus.get(key)
                    for key in ("corpus_as_of", "acts", "embedding_model", "built_at")
                }
        except Exception as e:
            logger.warning("qdrant_stats_fetch_failed", error=str(e))
            stats["qdrant"] = {"status": "unavailable"}
            stats["qdrant_available"] = False
    else:
        stats["qdrant"] = {"status": "unavailable"}

    # Is the corpus the law in force? {"status", "checked_at", "outdated": [{"celex",
    # "indexed", "latest"}], ...}; "unknown" until the nightly job has run.
    stats["freshness"] = await corpus_freshness()

    if not app_state.qdrant_available or not app_state.llm_available:
        stats["status"] = "degraded"

    return stats


@router.get("/api/v1/metrics")
async def get_metrics(user: CurrentUser = Depends(require_role("admin"))):
    return metrics.summary()


@router.get("/api/v1/system/quota")
async def get_llm_quota(user: CurrentUser = Depends(get_current_user)):
    """Today's LLM request quota for the caller's organization (for the UI).

    Shape: ``{org_id, date, limit, used, remaining, unlimited,
    resets_in_seconds, resets_at}`` - ``remaining`` is -1 when unlimited.
    """
    from src.quotas import llm_quota

    status = await llm_quota.usage(str(user.org_id))
    return status.as_dict()


@router.get("/api/v1/metrics/prometheus", dependencies=[Depends(require_scrape_auth)])
async def get_prometheus_metrics():
    """Prometheus-compatible metrics endpoint for scraping.

    Auth: static PROMETHEUS_BEARER_TOKEN (scraper) or admin JWT (operator).
    """
    from fastapi.responses import Response

    from src.observability import get_metrics_response

    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)


@router.get("/health")
async def health_check():
    """Liveness probe: the process is up and serving requests.

    Always returns 200 while the event loop is responsive - do NOT gate
    on dependencies here, or a Qdrant outage would make the orchestrator
    kill healthy app containers.

    ``version`` is the git SHA baked into the image (APP_VERSION, "dev"
    outside a build) so the deploy workflow can confirm the running build.
    """
    return {
        "status": "ok",
        "version": get_settings().app_version,
        "qdrant": "up" if app_state.qdrant_available else "down",
        "llm": "configured" if app_state.llm_available else "missing_key",
    }


@router.get("/readyz")
async def readiness_check():
    """Readiness probe: the instance can serve meaningful traffic.

    Returns 503 when core dependencies are unavailable so a load
    balancer can drain this instance without killing it (liveness
    stays green, readiness goes red).
    """
    from fastapi.responses import JSONResponse

    # Corpus gate: an EMPTY Qdrant collection still passes ``qdrant_available``
    # (the collection merely EXISTS), but it cannot answer anything with a
    # citation - so readiness must go red until it is actually seeded. Default
    # True so a missing indexer (e.g. tests) never spuriously fails readiness;
    # only a KNOWN-empty collection flips it down.
    corpus_ok = True
    _idx = getattr(app_state, "indexer", None)
    if app_state.qdrant_available and _idx is not None:
        try:
            corpus_ok = ((_idx.get_collection_stats() or {}).get("points_count", 0) or 0) > 0
        except Exception as e:  # noqa: BLE001
            logger.warning("readyz_corpus_check_failed", error=str(e))
            corpus_ok = False

    checks = {
        "qdrant": app_state.qdrant_available,
        "llm": app_state.llm_available,
        "corpus": corpus_ok,
    }
    ready = all(checks.values())
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {k: ("up" if v else "down") for k, v in checks.items()},
    }
    return JSONResponse(status_code=200 if ready else 503, content=body)
