"""NormaAI configuration - single source of truth for all settings."""

import logging
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings

_config_logger = logging.getLogger("normaai.config")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ─── LLM Provider ─────────────────────────────────────────
    # Supported: "gemini", "anthropic", "openrouter"
    llm_provider: str = "gemini"

    # Google Gemini
    google_api_key: str = ""
    gemini_model_analysis: str = "gemini-2.5-flash-preview-05-20"
    gemini_model_classification: str = "gemini-2.0-flash"

    # Anthropic (fallback)
    anthropic_api_key: str = ""
    anthropic_model_analysis: str = "claude-sonnet-4-5-20250514"

    # OpenRouter (OpenAI-compatible gateway - many models, free tiers for
    # real-LLM testing without burning paid quota; also a BYO-key path)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default: strongest broadly-available free tier as of 2026-06
    # (list live models: GET https://openrouter.ai/api/v1/models)
    openrouter_model_analysis: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # Shared LLM settings
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 120
    llm_max_tokens: int = 4096

    # ─── Local LLM (Ollama - Qwen micro-agents) ───────────────
    local_llm_enabled: bool = False
    local_llm_base_url: str = "http://localhost:11434"
    local_llm_model: str = "qwen3.5:4b"
    local_llm_timeout_seconds: int = 10
    local_llm_max_tokens: int = 512
    local_llm_temperature: float = 0.0

    # ─── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://normaai:changeme@localhost:5432/normaai"

    # ─── Qdrant ───────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "eu_regulations"
    qdrant_timeout: int = 30

    # ─── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600

    # ─── EUR-Lex ──────────────────────────────────────────────
    eurlex_sparql_endpoint: str = "https://publications.europa.eu/webapi/rdf/sparql"
    eurlex_crawl_interval_hours: int = 6

    # ─── Background acquisition scheduler ─────────────────────
    # OFF by default: the periodic EUR-Lex/Normattiva refresh loop only runs
    # when explicitly enabled (so a single-process deploy can opt in, while
    # tests/CI and multi-replica deploys - where a dedicated worker should own
    # it - leave it off). Without this, "updated nightly" never actually ran.
    acquisition_scheduler_enabled: bool = False

    # ─── Normattiva Open Data ─────────────────────────────────
    normattiva_enabled: bool = True
    normattiva_api_base_url: str = "https://www.normattiva.it/opendata"
    normattiva_rate_limit_delay: float = 1.0
    normattiva_bulk_download_enabled: bool = False

    # ─── Data Sources ─────────────────────────────────────────
    data_source: str = "both"  # "eurlex", "normattiva", or "both"

    # ─── Embedding ────────────────────────────────────────────
    # Multilingual by default: the corpus mixes EU-English (EUR-Lex) and Italian
    # (Normattiva) and most user queries are Italian. The previous English-only
    # bge-base-en degraded retrieval on Italian legal text. This model keeps the
    # same 768-dim space (drop-in for the Qdrant collection) and needs no e5-style
    # query/passage prefixes. NOTE: switching the model requires re-seeding the
    # corpus (vectors live in a model-specific space) - see ADR-005.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    embedding_dimension: int = 768
    embedding_batch_size: int = 32

    # ─── App ──────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    max_concurrent_requests: int = 10

    # ─── Chain-of-Verification (CoVe) ────────────────────────
    cove_enabled: bool = False
    cove_max_claims: int = 10
    cove_timeout_per_phase: float = 30.0
    cove_skip_citation_check: bool = False

    # ─── SNC Trust Layer (Behavioral Trust Clustering) ───────
    # Wraps the existing pipeline with K-sample stochastic generation and
    # applies a closed-form thermodynamic trust score to drive a three-way
    # routing decision (ADMIT_HIGH / ADMIT_MID / ABSTAIN). Sits between the
    # agent nodes and the existing confidence_check -> CoVe gate.
    snc_enabled: bool = True
    snc_k: int = 3
    """Number of stochastic samples for trust calibration (>= 2)."""
    snc_temperature: float = 0.7
    """Sampling temperature for the K-1 additional samples."""
    snc_theta_high: float = 0.85
    """Trust threshold above which the system admits and skips CoVe."""
    snc_theta_low: float = 0.50
    """Trust threshold below which the system abstains and flags for expert review."""

    # ─── Streaming ────────────────────────────────────────────
    sse_keepalive_interval: int = 15
    sse_enabled: bool = True

    # ─── Auth ───────────────────────────────────────────────
    app_secret_key: str = "change-me-in-production-use-64-chars-minimum"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ─── JWT RS256 Keys ──────────────────────────────────────
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_private_key: str = ""  # PEM content directly (alternative to path)
    jwt_public_key: str = ""  # PEM content directly (alternative to path)

    # ─── JWT issuer / audience claims ────────────────────────
    # Set on every minted token and verified (required) on decode. Defaults
    # match the single-service deployment; override if you split the API behind
    # a gateway or issue tokens for multiple audiences.
    jwt_issuer: str = "normaai"
    jwt_audience: str = "normaai-api"
    # Set False only during a migration window where legacy tokens (minted
    # before aud/iss existed) must still be accepted until they expire.
    jwt_require_aud_iss: bool = True

    # ─── CORS ───────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"  # comma-separated
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS"
    cors_allow_headers: str = "Authorization,Content-Type,X-Request-ID,Accept"
    cors_max_age: int = 600  # preflight cache in seconds

    # ─── Public URL ─────────────────────────────────────────
    normaai_public_url: str = "https://normaai.org"

    # ─── Observability scrape auth ──────────────────────────
    # Static bearer token Prometheus presents when scraping
    # /api/v1/metrics/prometheus. Empty = endpoint admin-JWT only.
    prometheus_bearer_token: str = ""

    # ─── Resend (transactional email outbound) ─────────────
    resend_api_key: str = ""
    resend_from_email: str = "info@normaai.org"
    resend_from_name: str = "Daniel Culotta - NormaAI"
    resend_reply_to: str = "info@normaai.org"
    resend_webhook_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string.

        In production, this MUST be set to specific origins.
        Wildcard '*' is blocked in production mode.
        """
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.app_env == "production" and "*" in origins:
            _config_logger.critical("CORS wildcard '*' is not allowed in production!")
            origins = []
        return origins

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def active_api_key(self) -> str:
        """Return the API key for the active LLM provider."""
        if self.llm_provider == "gemini":
            return self.google_api_key
        if self.llm_provider == "openrouter":
            return self.openrouter_api_key
        return self.anthropic_api_key

    @property
    def active_model(self) -> str:
        """Return the model name for the active LLM provider."""
        if self.llm_provider == "gemini":
            return self.gemini_model_analysis
        if self.llm_provider == "openrouter":
            return self.openrouter_model_analysis
        return self.anthropic_model_analysis


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def validate_settings_or_exit() -> Settings:
    """Validate critical settings at startup, exit if misconfigured."""
    settings = get_settings()
    warnings = []

    if settings.llm_provider not in ("gemini", "anthropic", "openrouter"):
        _config_logger.error(
            "Invalid LLM_PROVIDER '%s'. Must be 'gemini', 'anthropic' or 'openrouter'.",
            settings.llm_provider,
        )
        sys.exit(1)

    if settings.llm_provider == "gemini" and not settings.google_api_key:
        warnings.append(
            "GOOGLE_API_KEY is not set. "
            "Intelligence endpoints (Q&A, gap analysis, monitor) will fail. "
            "Add it to your .env file."
        )
    elif settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        warnings.append(
            "ANTHROPIC_API_KEY is not set. "
            "Intelligence endpoints will fail. "
            "Add it to your .env file."
        )
    elif settings.llm_provider == "openrouter" and not settings.openrouter_api_key:
        warnings.append(
            "OPENROUTER_API_KEY is not set. "
            "Intelligence endpoints will fail. "
            "Add it to your .env file."
        )

    if settings.app_secret_key.startswith("change-me") or len(settings.app_secret_key) < 32:
        if settings.app_env == "production":
            _config_logger.critical(
                "APP_SECRET_KEY must be changed from default in production (min 32 chars). "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
            sys.exit(1)
        else:
            warnings.append(
                "APP_SECRET_KEY is still default or too short. Generate a real key for security."
            )

    # CORS: main.py registers CORSMiddleware with allow_credentials=True. A '*'
    # origin under credentialed CORS is a footgun (the browser rejects it, but
    # Starlette would still echo the header). cors_origin_list already fails
    # closed by emptying the list; refuse to even start in production so the
    # misconfiguration is loud, not a silently broken CORS surface.
    if settings.app_env == "production":
        raw_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        if "*" in raw_origins:
            _config_logger.critical(
                "CORS_ORIGINS contains '*' in production with credentialed CORS. "
                "Set CORS_ORIGINS to explicit https origins (e.g. https://normaai.org)."
            )
            sys.exit(1)

    for w in warnings:
        _config_logger.warning(w)

    provider = settings.llm_provider.upper()
    model = settings.active_model
    has_key = bool(settings.active_api_key)
    _config_logger.info(
        "LLM Provider: %s | Model: %s | Key configured: %s", provider, model, has_key
    )

    if settings.local_llm_enabled:
        _config_logger.info(
            "Local LLM: ENABLED | Model: %s | URL: %s | Timeout: %ds",
            settings.local_llm_model,
            settings.local_llm_base_url,
            settings.local_llm_timeout_seconds,
        )
    else:
        _config_logger.info("Local LLM: DISABLED (set LOCAL_LLM_ENABLED=true to activate)")

    # Data sources
    _config_logger.info("Data Sources: %s", settings.data_source.upper())
    if settings.normattiva_enabled:
        _config_logger.info(
            "Normattiva: ENABLED | Rate limit: %.1fs | Bulk download: %s",
            settings.normattiva_rate_limit_delay,
            "ON" if settings.normattiva_bulk_download_enabled else "OFF",
        )
    else:
        _config_logger.info("Normattiva: DISABLED")

    # Chain-of-Verification
    if settings.cove_enabled:
        _config_logger.info(
            "CoVe: ENABLED | Max claims: %d | Timeout: %.1fs | Citation check: %s",
            settings.cove_max_claims,
            settings.cove_timeout_per_phase,
            "ON" if not settings.cove_skip_citation_check else "OFF",
        )
    else:
        _config_logger.info("CoVe: DISABLED")

    # Streaming
    _config_logger.info(
        "Streaming: %s | Keepalive: %ds",
        "ENABLED" if settings.sse_enabled else "DISABLED",
        settings.sse_keepalive_interval,
    )

    return settings
