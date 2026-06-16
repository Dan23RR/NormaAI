"""Enterprise resilience: circuit breaker, concurrency limiter, graceful degradation.

Provides:
- LLM concurrency semaphore (prevents thread-pool exhaustion)
- Circuit breaker for LLM calls (stops cascading failures)
- Graceful degradation helpers for Redis, Qdrant, OCR
"""

import asyncio
import logging
import threading
import time
from enum import Enum

from src.config import get_settings

logger = logging.getLogger(__name__)


# ─── Concurrency Limiter ─────────────────────────────────────────

_semaphore: asyncio.Semaphore | None = None
_semaphore_loop = None
_semaphore_lock = threading.Lock()


def get_llm_semaphore() -> asyncio.Semaphore:
    """Get or create the LLM concurrency semaphore, bound to the running loop.

    Caps concurrent calls to the LLM PROVIDER (acquired per-LLM-call, not
    per-request) so the SNC/CoVe fan-out cannot trigger a 429-storm / bill-shock.
    An asyncio.Semaphore is bound to the loop it is created on; we recreate it if
    the running loop changed (multi-worker / test) to avoid 'bound to a different
    event loop' errors.
    """
    global _semaphore, _semaphore_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _semaphore is None or _semaphore_loop is not loop:
        with _semaphore_lock:
            if _semaphore is None or _semaphore_loop is not loop:
                settings = get_settings()
                _semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
                _semaphore_loop = loop
                logger.info(
                    "llm_semaphore_created",
                    extra={"max_concurrent": settings.max_concurrent_requests},
                )
    return _semaphore


# ─── Circuit Breaker ─────────────────────────────────────────────


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — reject requests fast
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Thread-safe circuit breaker for external service calls.

    State transitions:
    - CLOSED: Normal. On failure_threshold consecutive failures → OPEN.
    - OPEN: Fast-fail all calls. After recovery_timeout → HALF_OPEN.
    - HALF_OPEN: Allow one probe. On success → CLOSED. On failure → OPEN.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._success_count = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("circuit_half_open", extra={"service": self.name})
            return self._state

    @property
    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._success_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("circuit_closed", extra={"service": self.name})

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_open",
                    extra={
                        "service": self.name,
                        "failures": self._failure_count,
                        "recovery_in_seconds": self.recovery_timeout,
                    },
                )

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0


# ─── Service Circuit Breakers (Singletons) ────────────────────────

llm_circuit = CircuitBreaker("llm", failure_threshold=5, recovery_timeout=60.0)
qdrant_circuit = CircuitBreaker("qdrant", failure_threshold=3, recovery_timeout=30.0)
redis_circuit = CircuitBreaker("redis", failure_threshold=3, recovery_timeout=15.0)
local_llm_circuit = CircuitBreaker("local_llm", failure_threshold=3, recovery_timeout=30.0)


# ─── Graceful Degradation Helpers ─────────────────────────────────


class ServiceUnavailableError(Exception):
    """Raised when a service circuit is open."""

    def __init__(self, service: str):
        self.service = service
        super().__init__(f"{service} is temporarily unavailable (circuit open)")


def require_circuit(circuit: CircuitBreaker) -> None:
    """Raise ServiceUnavailableError if the circuit is open."""
    if not circuit.is_available:
        raise ServiceUnavailableError(circuit.name)
