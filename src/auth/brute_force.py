"""Brute-force protection for authentication endpoints.

Redis-backed login attempt tracking with automatic lockout.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Configuration
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes
KEY_PREFIX = "normaai:bruteforce:"

# In-memory fallback cap: bounds memory if Redis is down during an attack that
# sprays many distinct emails. Per-account brute force stays capped; once the
# cap is hit, genuinely new keys degrade to open (a single account under attack
# is still limited by the entries already tracked).
_MEMORY_MAX_KEYS = 10_000


class BruteForceProtection:
    """Redis-backed brute-force protection for login.

    Tracks failed login attempts per email/IP combination.
    After MAX_ATTEMPTS failures, the account is locked for LOCKOUT_SECONDS.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._available = False
        # Best-effort in-process fallback used ONLY when Redis is unavailable:
        # key -> (attempts, expiry_epoch_seconds). Per-instance (in a multi-replica
        # deploy the effective limit is MAX_ATTEMPTS x replicas), but far better
        # than failing fully open during a Redis outage.
        self._memory: dict[str, tuple[int, float]] = {}

    async def connect(self, redis_client: Any) -> None:
        """Use an existing Redis connection."""
        self._client = redis_client
        self._available = redis_client is not None

    async def _get_redis(self) -> Any:
        """Lazily connect to Redis if needed."""
        if self._client is not None:
            return self._client

        try:
            import redis.asyncio as aioredis

            from src.config import get_settings

            settings = get_settings()
            self._client = aioredis.from_url(  # type: ignore[no-untyped-call]  # redis.asyncio untyped
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
            # Redis down: degrade to a bounded in-memory counter, not fail-open.
            return self._memory_check_and_increment(email.lower())

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
            return self._memory_check_and_increment(email.lower())

    def _memory_check_and_increment(self, key: str) -> str | None:
        """Bounded in-process fallback mirroring the Redis lockout logic."""
        now = time.time()
        # Drop expired entries; if still over the cap the dict is full of active
        # locks (an ongoing spray) -> stop tracking genuinely new keys.
        if len(self._memory) > _MEMORY_MAX_KEYS:
            self._memory = {k: v for k, v in self._memory.items() if v[1] > now}

        entry = self._memory.get(key)
        if entry and entry[1] > now:
            attempts, expiry = entry
            if attempts >= MAX_ATTEMPTS:
                remaining = int(expiry - now)
                return (
                    f"Too many failed login attempts. "
                    f"Account locked for {remaining // 60 + 1} minute(s). "
                    f"Please try again later."
                )
            self._memory[key] = (attempts + 1, expiry)
            return None

        # New or expired key: start a fresh window unless the cap is reached.
        if len(self._memory) >= _MEMORY_MAX_KEYS:
            return None
        self._memory[key] = (1, now + LOCKOUT_SECONDS)
        return None

    async def reset(self, email: str) -> None:
        """Reset attempt counter on successful login."""
        self._memory.pop(email.lower(), None)  # clear any in-memory fallback entry
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
            entry = self._memory.get(email.lower())
            if entry and entry[1] > time.time():
                return max(0, MAX_ATTEMPTS - entry[0])
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
