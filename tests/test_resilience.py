"""Tests for the enterprise resilience layer (src.resilience).

Tests cover:
- Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Thread-safety of circuit breaker under concurrent access
- LLM concurrency semaphore creation
- ServiceUnavailableError when circuit is open
- require_circuit() helper
"""

import asyncio
import threading
import time

import pytest

from src.resilience import (
    CircuitBreaker,
    CircuitState,
    ServiceUnavailableError,
    get_llm_semaphore,
    require_circuit,
)

# ------------------------------------------------------------------ #
#  Circuit Breaker State Transitions                                   #
# ------------------------------------------------------------------ #


class TestCircuitBreakerStates:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_remains_closed_under_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After success, another 2 failures should not open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_reset_returns_to_closed(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True


# ------------------------------------------------------------------ #
#  Thread Safety                                                       #
# ------------------------------------------------------------------ #


class TestCircuitBreakerThreadSafety:
    def test_concurrent_failures_open_circuit_exactly_once(self):
        cb = CircuitBreaker("test", failure_threshold=5, recovery_timeout=60)
        errors = []

        def record():
            try:
                for _ in range(10):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cb.state == CircuitState.OPEN


# ------------------------------------------------------------------ #
#  ServiceUnavailableError                                             #
# ------------------------------------------------------------------ #


class TestRequireCircuit:
    def test_passes_when_closed(self):
        cb = CircuitBreaker("test", failure_threshold=5, recovery_timeout=60)
        require_circuit(cb)  # Should not raise

    def test_raises_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        with pytest.raises(ServiceUnavailableError) as exc:
            require_circuit(cb)
        assert "test" in str(exc.value)
        assert exc.value.service == "test"


# ------------------------------------------------------------------ #
#  LLM Semaphore                                                       #
# ------------------------------------------------------------------ #


class TestLLMSemaphore:
    def test_semaphore_is_created(self):
        # Reset the singleton for test isolation
        import src.resilience as res

        original = res._semaphore
        res._semaphore = None
        try:
            sem = get_llm_semaphore()
            assert isinstance(sem, asyncio.Semaphore)
        finally:
            res._semaphore = original

    def test_semaphore_is_singleton(self):
        sem1 = get_llm_semaphore()
        sem2 = get_llm_semaphore()
        assert sem1 is sem2
