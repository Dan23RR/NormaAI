"""
NormaAI API - FastAPI backend for EU regulatory intelligence.

Thin orchestration module: app creation, CORS, router registration.
Business logic lives in dedicated modules:
- app_state.py: Shared state singleton
- rate_limit.py: Rate limiter with user-based keys
- middleware.py: Request ID, timing, metrics, security headers
- lifespan.py: Startup/shutdown lifecycle
- landing.py: Landing page HTML
- schemas.py: Shared enums (FrameworkEnum)
"""

import os

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.config import get_settings

# ─── Structured Logging ──────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

# ─── Backward-compatible re-exports ──────────────────────────────
# Existing code may import these from src.api.main; keep them available.
from src.api.app_state import app_state  # noqa: F401

# ─── Imports for app setup ────────────────────────────────────────
from src.api.lifespan import lifespan
from src.api.middleware import (
    metrics,  # noqa: F401
    register_middleware,
)
from src.api.rate_limit import limiter  # noqa: F401

# ─── API Tags ─────────────────────────────────────────────────────
tags_metadata = [
    {
        "name": "Intelligence",
        "description": "AI-powered regulatory analysis: Q&A, gap analysis, and impact monitoring.",
    },
    {"name": "Data", "description": "EUR-Lex crawler and regulatory data management."},
    {"name": "System", "description": "Health checks and system statistics."},
    {"name": "Auth", "description": "Authentication and authorization endpoints."},
    {"name": "Clients", "description": "Client company management and CRUD operations."},
    {"name": "Alerts", "description": "Regulatory compliance alerts and notifications."},
    {
        "name": "Reports",
        "description": "PDF report generation: gap analysis and executive summaries.",
    },
    {"name": "Conversations", "description": "Multi-turn Q&A conversation management."},
]

DESCRIPTION = """
## EU Regulatory Intelligence Monitor

NormaAI monitors **7 EU regulatory frameworks** in real-time and provides AI-powered compliance intelligence:

| Framework | Status |
|-----------|--------|
| **CSRD** - Corporate Sustainability Reporting | Active |
| **CSDDD** - Corporate Sustainability Due Diligence | Active |
| **AI Act** - Artificial Intelligence Regulation | Active |
| **DORA** - Digital Operational Resilience | Active |
| **NIS2** - Network & Information Security | Active |
| **EU Taxonomy** - Sustainable Finance Classification | Active |
| **GDPR** - General Data Protection | Active |

### Core capabilities
- **Q&A** - Ask questions about EU regulations with cited answers
- **Gap Analysis** - Compliance assessment with scoring per framework
- **Monitor** - Impact analysis of regulatory changes on your company
- **Crawl** - Real-time EUR-Lex data via SPARQL endpoint
"""

# ─── App ──────────────────────────────────────────────────────────
app = FastAPI(
    title="NormaAI",
    description=DESCRIPTION,
    version="0.3.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Rate Limiter ─────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS ─────────────────────────────────────────────────────────
_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=[m.strip() for m in _cors_settings.cors_allow_methods.split(",")],
    allow_headers=[h.strip() for h in _cors_settings.cors_allow_headers.split(",")],
    max_age=_cors_settings.cors_max_age,
)

# ─── Middleware (security headers, request ID, timing) ────────────
register_middleware(app)

# ─── Optional Integrations ────────────────────────────────────────
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("opentelemetry_instrumented")
except ImportError:
    pass

try:
    import sentry_sdk

    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=os.getenv("APP_ENV", "development"),
        )
        logger.info("sentry_initialized")
except ImportError:
    pass


# ─── Router Registration ─────────────────────────────────────────


# Security/compliance-critical routers. A failed import of any of these must
# ABORT startup rather than silently degrade: a missing auth router would ship
# an API with no login/token surface; a missing GDPR router would drop a
# compliance-mandated surface. Membership here is the SOURCE OF TRUTH for
# fail-fast: a registered router aborts startup even if a call site omits
# `critical=True` (the flag stays as an explicit, self-documenting marker).
CRITICAL_ROUTERS: frozenset[str] = frozenset(
    {
        "src.auth.router",
        "src.api.routers.gdpr",
    }
)


def _safe_include(
    router_module: str,
    router_attr: str = "router",
    prefix: str = "",
    *,
    critical: bool = False,
    **kwargs,
):
    """Import and register a router.

    Optional routers (``critical=False``) degrade gracefully: an ImportError is
    logged and swallowed so the app can boot without a non-essential surface.
    Security/compliance-critical routers (members of ``CRITICAL_ROUTERS`` -- or
    explicitly ``critical=True``) are fail-fast: ANY import-time failure
    (ImportError, SyntaxError, a broken dependency, a missing ``router``
    attribute) aborts startup loudly instead of shipping an API with a missing
    authentication/compliance surface.
    """
    # Registry membership drives fail-fast so a future edit dropping the
    # `critical=True` kwarg from an auth/gdpr call site cannot silently regress
    # to shipping without that surface. The flag is still sanity-checked against
    # the registry (forward direction) to catch a mis-flagged optional router.
    is_critical = critical or router_module in CRITICAL_ROUTERS
    if critical and router_module not in CRITICAL_ROUTERS:
        raise AssertionError(f"{router_module} flagged critical but not in CRITICAL_ROUTERS")
    try:
        import importlib

        mod = importlib.import_module(router_module)
        r = getattr(mod, router_attr)
        app.include_router(r, prefix=prefix, **kwargs)
        logger.info("router_loaded", module=router_module)
    except Exception as e:  # noqa: BLE001
        if is_critical:
            logger.error("critical_router_failed", module=router_module, error=str(e))
            raise RuntimeError(
                f"Critical router '{router_module}' failed to load: {e}. "
                "Refusing to start with a missing security/compliance surface."
            ) from e
        if isinstance(e, ImportError):
            logger.warning("router_not_available", module=router_module, error=str(e))
        else:
            # An optional router that imports but is internally broken (e.g. a
            # missing `router` attribute) is a real bug -> do not swallow it.
            raise


# Landing page
_safe_include("src.api.landing")

# Auth (CRITICAL: never ship without authentication endpoints)
_safe_include("src.auth.router", prefix="/api/v1", critical=True)

# API routers
_safe_include("src.api.routers.intelligence")
_safe_include("src.api.routers.data")
_safe_include("src.api.routers.system")
_safe_include("src.api.routers.alerts")
_safe_include("src.api.routers.reports")
_safe_include("src.api.routers.clients")
_safe_include("src.api.routers.conversations")
_safe_include("src.api.routers.leads")
# GDPR (CRITICAL: data-subject-rights endpoints are compliance-mandated)
_safe_include("src.api.routers.gdpr", critical=True)
