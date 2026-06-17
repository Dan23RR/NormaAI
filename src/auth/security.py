"""JWT token creation and verification for NormaAI.

Security features:
- RS256 asymmetric signing (private key signs, public key verifies)
- Fallback to HS256 if RSA keys not configured (development only)
- JTI (JWT ID) for token blacklisting/revocation
- Refresh token rotation with family tracking
- Redis-backed token blacklist for instant revocation
"""

import logging
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from src.config import get_settings

logger = logging.getLogger(__name__)


# Token configuration - loaded from settings (src/config.py)
def _get_access_token_expire_minutes() -> int:
    return get_settings().access_token_expire_minutes


def _get_refresh_token_expire_days() -> int:
    return get_settings().refresh_token_expire_days


# Algorithm selection: RS256 preferred, HS256 fallback for dev
_rs256_private_key: str | None = None
_rs256_public_key: str | None = None
_algorithm: str = "HS256"


def _load_rsa_keys() -> None:
    """Load RSA keys from file paths or environment variables."""
    global _rs256_private_key, _rs256_public_key, _algorithm

    settings = get_settings()

    # Try loading from PEM content first (env var)
    if settings.jwt_private_key and settings.jwt_public_key:
        _rs256_private_key = settings.jwt_private_key
        _rs256_public_key = settings.jwt_public_key
        _algorithm = "RS256"
        logger.info("jwt_keys_loaded_from_env")
        return

    # Try loading from file paths
    private_path = settings.jwt_private_key_path
    public_path = settings.jwt_public_key_path

    if private_path and public_path:
        try:
            private_pem = Path(private_path).read_text()
            public_pem = Path(public_path).read_text()
            if "BEGIN" in private_pem and "BEGIN" in public_pem:
                _rs256_private_key = private_pem
                _rs256_public_key = public_pem
                _algorithm = "RS256"
                logger.info("jwt_keys_loaded_from_files", private=private_path, public=public_path)
                return
        except (FileNotFoundError, PermissionError) as e:
            logger.warning("jwt_key_files_not_found", error=str(e))

    # Fallback to HS256
    if settings.app_env == "production":
        logger.critical(
            "FATAL: RSA keys not configured in production. "
            "HS256 fallback is BLOCKED in production for security. "
            "Generate RSA keys: openssl genrsa -out jwt_private.pem 2048 && "
            "openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem"
        )
        sys.exit(1)

    _algorithm = "HS256"
    logger.warning("jwt_using_hs256_fallback - Generate RSA keys for production")


def _get_signing_key() -> str:
    """Get the key used to sign tokens."""
    if _algorithm == "RS256" and _rs256_private_key:
        return _rs256_private_key
    return get_settings().app_secret_key


def _get_verification_key() -> str:
    """Get the key used to verify tokens."""
    if _algorithm == "RS256" and _rs256_public_key:
        return _rs256_public_key
    return get_settings().app_secret_key


def get_algorithm() -> str:
    """Return current JWT algorithm."""
    return _algorithm


# Initialize keys at module load
_load_rsa_keys()


class TokenPayload(BaseModel):
    sub: str  # user_id
    org_id: str  # organization_id
    role: str  # admin, member, viewer
    exp: datetime
    type: str  # access or refresh
    jti: str  # unique token ID for blacklisting
    family: str | None = None  # refresh token family for rotation


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ─── Token Blacklist (Redis-backed) ─────────────────────────────


class TokenBlacklist:
    """Redis-backed token blacklist for instant revocation.

    Blacklisted JTIs are stored with TTL matching token expiration,
    so entries auto-expire and don't accumulate forever.
    """

    KEY_PREFIX = "normaai:token:blacklist:"

    def __init__(self):
        self._client = None
        self._available = False

    async def connect(self) -> bool:
        """Connect to Redis for token blacklisting."""
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            self._client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._client.ping()
            self._available = True
            logger.info("token_blacklist_connected")
            return True
        except Exception as e:
            logger.warning("token_blacklist_unavailable: %s", e)
            self._available = False
            return False

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._available = False

    async def blacklist_token(self, jti: str, expires_at: datetime) -> bool:
        """Add a token JTI to the blacklist until its natural expiration."""
        if not self._available or not self._client:
            return False
        try:
            ttl_seconds = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
            await self._client.setex(f"{self.KEY_PREFIX}{jti}", ttl_seconds, "1")
            logger.info("token_blacklisted", jti=jti[:8])
            return True
        except Exception as e:
            logger.warning("blacklist_set_error: %s", e)
            return False

    async def blacklist_token_family(self, family: str) -> bool:
        """Blacklist an entire refresh token family (compromised token rotation)."""
        if not self._available or not self._client:
            return False
        try:
            ttl_seconds = _get_refresh_token_expire_days() * 86400
            await self._client.setex(f"{self.KEY_PREFIX}family:{family}", ttl_seconds, "1")
            logger.warning("token_family_blacklisted", family=family[:8])
            return True
        except Exception as e:
            logger.warning("blacklist_family_error: %s", e)
            return False

    async def is_blacklisted(self, jti: str, family: str | None = None) -> bool:
        """Check if a token JTI or its family is blacklisted.

        SECURITY: Fail-closed in production - if Redis is down, all tokens
        are treated as blacklisted to prevent unauthorized access.
        """
        if not self._available or not self._client:
            if get_settings().app_env == "production":
                logger.error("blacklist_unavailable_in_production - fail closed")
                return True  # Fail closed: deny access if we can't verify
            return False
        try:
            # Check specific JTI
            if await self._client.exists(f"{self.KEY_PREFIX}{jti}"):
                return True
            # Check token family
            if family and await self._client.exists(f"{self.KEY_PREFIX}family:{family}"):
                return True
            return False
        except Exception as e:
            logger.warning("blacklist_check_error: %s", e)
            if get_settings().app_env == "production":
                return True  # Fail closed in production
            return False

    @property
    def available(self) -> bool:
        return self._available


# Singleton
token_blacklist = TokenBlacklist()


# ─── Password Hashing ───────────────────────────────────────────


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    pw_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))


def hash_password(password: str) -> str:
    """Hash a password using bcrypt directly."""
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


# ─── Token Creation ─────────────────────────────────────────────


def create_access_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=_get_access_token_expire_minutes())
    )
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "exp": expire,
        "type": "access",
        "jti": jti,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, _get_signing_key(), algorithm=_algorithm)


def create_refresh_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    family: str | None = None,
) -> str:
    expire = datetime.now(UTC) + timedelta(days=_get_refresh_token_expire_days())
    jti = str(uuid.uuid4())
    token_family = family or str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "exp": expire,
        "type": "refresh",
        "jti": jti,
        "family": token_family,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, _get_signing_key(), algorithm=_algorithm)


def create_token_pair(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    family: str | None = None,
) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user_id, org_id, role),
        refresh_token=create_refresh_token(user_id, org_id, role, family=family),
        expires_in=_get_access_token_expire_minutes() * 60,
    )


# ─── Token Decoding ─────────────────────────────────────────────


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, _get_verification_key(), algorithms=[_algorithm])
        # Ensure JTI exists (backward compatibility with old tokens)
        if "jti" not in payload:
            payload["jti"] = "legacy-" + str(uuid.uuid4())
        return TokenPayload(**payload)
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
