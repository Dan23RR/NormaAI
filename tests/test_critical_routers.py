"""Security/compliance-critical routers must fail-fast.

A broken import of the auth or GDPR router must ABORT startup, not silently ship
an API with a missing authentication/compliance surface. Optional routers keep
degrading gracefully.
"""

import importlib
import sys
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """This file imports ``src.api.main`` (to exercise ``_safe_include``), which
    caches it and the router submodules bound to the REAL ``src.db.engine``. That
    breaks the ``sys.modules``-patching isolation used by test_leads /
    test_api_integration, which re-import the routers fresh against a MagicMock
    engine. Evict those modules after each test so this file does not leak that
    state into later test files (which would surface as a spurious
    "DatabaseSessionManager is not initialized" in the leads tests).
    """
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


def test_critical_routers_set_includes_auth_and_gdpr():
    from src.api.main import CRITICAL_ROUTERS

    assert "src.auth.router" in CRITICAL_ROUTERS
    assert "src.api.routers.gdpr" in CRITICAL_ROUTERS


def test_safe_include_aborts_for_critical_router_on_import_error():
    from src.api.main import _safe_include

    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "src.auth.router":
            raise ImportError("simulated broken auth module")
        return real_import(name, *args, **kwargs)

    with (
        patch("importlib.import_module", side_effect=fake_import),
        pytest.raises(RuntimeError, match="Critical router 'src.auth.router'"),
    ):
        _safe_include("src.auth.router", prefix="/api/v1", critical=True)


def test_safe_include_aborts_for_critical_router_on_any_error():
    # Not only ImportError: a SyntaxError/NameError raised at import time of a
    # critical module is fatal too (the whole point of fail-fast).
    from src.api.main import _safe_include

    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "src.api.routers.gdpr":
            raise RuntimeError("simulated broken module body")
        return real_import(name, *args, **kwargs)

    with (
        patch("importlib.import_module", side_effect=fake_import),
        pytest.raises(RuntimeError, match="Critical router 'src.api.routers.gdpr'"),
    ):
        _safe_include("src.api.routers.gdpr", critical=True)


def test_safe_include_swallows_import_error_for_optional_router():
    from src.api.main import _safe_include

    real_import = importlib.import_module
    attempted = []

    def fake_import(name, *args, **kwargs):
        if name == "src.api.routers.leads":
            attempted.append(name)
            raise ImportError("simulated broken optional module")
        return real_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=fake_import):
        _safe_include("src.api.routers.leads")  # must NOT raise

    assert attempted == ["src.api.routers.leads"]  # it was actually attempted


def test_critical_flag_requires_registry_membership():
    from src.api.main import _safe_include

    with pytest.raises(AssertionError):
        # system router is not in CRITICAL_ROUTERS -> flagging it critical is a bug.
        _safe_include("src.api.routers.system", critical=True)


def test_registry_member_fails_fast_without_explicit_flag():
    # Membership in CRITICAL_ROUTERS is the source of truth: a registered router
    # aborts startup on import failure even when the call site OMITS critical=True.
    # Guards against a future edit silently dropping the flag from auth/gdpr.
    from src.api.main import _safe_include

    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "src.api.routers.gdpr":
            raise ImportError("simulated broken gdpr module")
        return real_import(name, *args, **kwargs)

    with (
        patch("importlib.import_module", side_effect=fake_import),
        pytest.raises(RuntimeError, match="Critical router 'src.api.routers.gdpr'"),
    ):
        _safe_include("src.api.routers.gdpr")  # NOTE: no critical=True
