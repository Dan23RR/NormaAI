"""Brute-force protection for authentication endpoints.

Redis-backed login attempt tracking with automatic lockout.
"""

import logging

logger = logging.getLogger(__name__)

# Configuration
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes
KEY_PREFIX = "normaai:bruteforce:"


class BruteForceProtection:
    """Redis-backed brute-force protection for login.

    Tracks failed login attempts per email/IP combination.
    After MAX_ATTEMPTS failures, the account is locked for LOCKOUT_SECONDS.
    """

    def __init__(self):
        self._client = None
        self._available = False

    async def connect(self, redis_client) -> None:
        """Use an existing Redis connection."""
        self._client = redis_client
        self._available = redis_client is not None

    async def _get_redis(self):
        """Lazily connect to Redis if needed."""
        if self._client is not None:
            return self._client

        try:
            import redis.asyncio as aioredis

            from src.config import get_settings

            settings = get_settings()
            self._client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await self._client.ping()
            self._available = True
            return self._client
        except Exception as e:
            logger.warning("brute_force_redis_unavailable: %s", e)
            self._available = False
            return None

    def _key(self, identifier: str) -> str:
        """Generate Redis key for tracking attempts."""
        return f"{KEY_PREFIX}{identifier}"

    async def check_and_increment(self, email: str, ip: str) -> str | None:
        """Check if login is allowed and increment attempt counter.

        Returns:
            None if login is allowed.
            Error message string if account is locked out.
        """
        redis = await self._get_redis()
        if redis is None:
            return None  # Fail open if Redis unavailable (log warning above)

        # Use email as primary key to prevent account enumeration attacks
        key = self._key(email.lower())

        try:
            attempts = await redis.get(key)
            if attempts is not None and int(attempts) >= MAX_ATTEMPTS:
                ttl = await redis.ttl(key)
                logger.warning(
                    "brute_force_lockout",
                    extra={
                        "email": email[:3] + "***",
                        "ip": ip,
                        "remaining_seconds": ttl,
                    },
                )
                return (
                    f"Too many failed login attempts. "
                    f"Account locked for {ttl // 60 + 1} minute(s). "
                    f"Please try again later."
                )

            # Increment attempts with TTL
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, LOCKOUT_SECONDS)
            await pipe.execute()
            return None

        except Exception as e:
            logger.warning("brute_force_check_error: %s", e)
            return None  # Fail open on Redis errors

    async def reset(self, email: str) -> None:
        """Reset attempt counter on successful login."""
        redis = await self._get_redis()
        if redis is None:
            return

        try:
            await redis.delete(self._key(email.lower()))
        except Exception as e:
            logger.warning("brute_force_reset_error: %s", e)

    async def get_remaining_attempts(self, email: str) -> int:
        """Get remaining attempts before lockout."""
        redis = await self._get_redis()
        if redis is None:
            return MAX_ATTEMPTS

        try:
            attempts = await redis.get(self._key(email.lower()))
            if attempts is None:
                return MAX_ATTEMPTS
            return max(0, MAX_ATTEMPTS - int(attempts))
        except Exception:
            return MAX_ATTEMPTS


# Singleton
brute_force = BruteForceProtection()
