"""Application lifespan manager: startup validation and shutdown.

Extracted from main.py for single-responsibility.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.api.app_state import app_state
from src.config import validate_settings_or_exit

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup validation and graceful shutdown."""
    settings = validate_settings_or_exit()
    logger.info("normaai_starting", env=settings.app_env)

    # Initialize database
    try:
        from src.db.engine import db_manager

        db_manager.init()
        logger.info("database_initialized")
    except Exception as e:
        logger.warning("database_initialization_failed", error=str(e))

    # Fail-fast: in production the app MUST connect as a NON-superuser DB role.
    # PostgreSQL silently bypasses every Row-Level-Security policy for superusers
    # and table owners, so connecting as such makes multi-tenant isolation INERT
    # (one tenant could read another's data). Refuse to start rather than serve
    # real client data unprotected. No-op outside production / non-PostgreSQL
    # (e.g. the sqlite test backend).
    if settings.app_env == "production" and "postgresql" in (settings.database_url or ""):
        from sqlalchemy import text as _sql_text

        from src.db.engine import db_manager

        try:
            async with db_manager.session() as _role_chk:
                _row = (
                    await _role_chk.execute(
                        _sql_text(
                            "SELECT rolsuper, rolbypassrls FROM pg_roles "
                            "WHERE rolname = current_user"
                        )
                    )
                ).first()
            if _row is not None and (_row[0] or _row[1]):
                raise RuntimeError(
                    "FATAL: the app connects to PostgreSQL as a SUPERUSER or "
                    f"BYPASSRLS role (rolsuper={_row[0]}, rolbypassrls={_row[1]}). "
                    "PostgreSQL ignores Row-Level Security for such roles, so tenant "
                    "isolation would be inert. Point DATABASE_URL at the non-superuser "
                    "'normaai_app' role and deploy with the docker-compose.rls.yml "
                    "overlay (see docs/DEPLOY_HETZNER.md)."
                )
            logger.info("rls_role_verified", superuser=False)
        except RuntimeError:
            raise  # propagate the fatal superuser error: do NOT start the app
        except Exception as e:
            # Could not verify (DB unreachable / transient): warn but do not block
            # startup on a connectivity blip - the ROLE is the risk, not an outage.
            logger.warning("rls_role_check_skipped", error=str(e))

    # Check Qdrant
    try:
        from src.nlp.embedding.indexer import HybridIndexer

        indexer = HybridIndexer(
            qdrant_host=settings.qdrant_host,
            qdrant_port=settings.qdrant_port,
        )
        indexer.setup_collection(recreate=False)
        app_state.indexer = indexer
        app_state.qdrant_available = True
        logger.info("qdrant_ready")
    except Exception as e:
        logger.error("qdrant_unavailable", error=str(e))
        app_state.qdrant_available = False

    # Check API key for configured provider
    app_state.llm_available = bool(settings.active_api_key)
    if not app_state.llm_available:
        key_name = "GOOGLE_API_KEY" if settings.llm_provider == "gemini" else "ANTHROPIC_API_KEY"
        logger.warning("llm_api_key_missing", provider=settings.llm_provider, key=key_name)
    else:
        logger.info("llm_ready", provider=settings.llm_provider, model=settings.active_model)

    # Check local LLM (Ollama)
    if settings.local_llm_enabled:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.local_llm_base_url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]
                    app_state.local_llm_available = True
                    logger.info(
                        "local_llm_ready",
                        model=settings.local_llm_model,
                        available_models=model_names,
                    )
                else:
                    logger.warning("local_llm_unhealthy", status=resp.status_code)
        except Exception as e:
            logger.warning("local_llm_unavailable", error=str(e))
            app_state.local_llm_available = False
    else:
        logger.info("local_llm_disabled")

    # Connect Redis cache
    try:
        from src.cache import response_cache

        await response_cache.connect()
    except Exception as e:
        logger.warning("redis_cache_init_failed", error=str(e))

    # Connect token blacklist (Redis)
    try:
        from src.auth.security import token_blacklist

        await token_blacklist.connect()
    except Exception as e:
        logger.warning("token_blacklist_init_failed", error=str(e))

    # Initialize observability (OpenTelemetry + Prometheus)
    try:
        from src.observability import setup_observability

        setup_observability(app)
    except Exception as e:
        logger.warning("observability_init_failed", error=str(e))

    # Shared Normattiva client for CoVe Italian-law (URN) citation validation.
    app_state.normattiva_client = None
    if settings.normattiva_enabled:
        try:
            from src.crawler.normattiva.client import NormattivaOpenDataClient

            app_state.normattiva_client = NormattivaOpenDataClient(
                base_url=settings.normattiva_api_base_url,
                rate_limit_delay=settings.normattiva_rate_limit_delay,
            )
            logger.info("normattiva_client_ready")
        except Exception as e:
            logger.warning("normattiva_client_init_failed", error=str(e))

    # Background acquisition scheduler (opt-in) - the periodic EUR-Lex/Normattiva
    # refresh that makes "updated nightly" actually true. Off unless enabled.
    app_state.scheduler = None
    if settings.acquisition_scheduler_enabled:
        try:
            from src.crawler.scheduler import AcquisitionScheduler

            scheduler = AcquisitionScheduler(interval_hours=settings.eurlex_crawl_interval_hours)
            await scheduler.start()
            app_state.scheduler = scheduler
            logger.info(
                "acquisition_scheduler_started",
                interval_h=settings.eurlex_crawl_interval_hours,
            )
        except Exception as e:
            logger.error("acquisition_scheduler_start_failed", error=str(e))
    else:
        logger.info("acquisition_scheduler_disabled")

    yield

    # ─── Shutdown ─────────────────────────────────────────────

    # Stop the acquisition scheduler first (drains the in-flight cycle).
    if getattr(app_state, "scheduler", None) is not None:
        try:
            await app_state.scheduler.stop()
        except Exception as e:
            logger.warning("acquisition_scheduler_stop_failed", error=str(e))

    # Close the shared Normattiva HTTP client.
    if getattr(app_state, "normattiva_client", None) is not None:
        try:
            await app_state.normattiva_client.close()
        except Exception as e:
            logger.warning("normattiva_client_close_failed", error=str(e))

    # Close token blacklist
    try:
        from src.auth.security import token_blacklist

        await token_blacklist.close()
    except Exception as e:
        logger.warning("token_blacklist_close_failed", error=str(e))

    # Close Redis cache
    try:
        from src.cache import response_cache

        await response_cache.close()
    except Exception as e:
        logger.warning("redis_cache_close_failed", error=str(e))

    logger.info("normaai_shutting_down")

    # Close database
    try:
        from src.db.engine import db_manager

        await db_manager.close()
        logger.info("database_closed")
    except Exception as e:
        logger.error("database_close_error", error=str(e))
