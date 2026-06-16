"""Tests for Row-Level Security enforcement on tenant-scoped endpoints.

Verifies that all tenant-scoped routers pass org_id to db_manager.session()
to ensure PostgreSQL RLS policies are activated.
"""

import ast
import inspect
from pathlib import Path

# Directory containing all API routers
ROUTERS_DIR = Path(__file__).parent.parent / "src" / "api" / "routers"

# Routers that must enforce RLS (tenant-scoped data)
TENANT_ROUTERS = ["clients.py", "alerts.py", "conversations.py", "reports.py"]

# Routers where db_manager.session() WITHOUT org_id is acceptable
# (auth endpoints, system endpoints that span organizations)
EXEMPT_ROUTERS = ["intelligence.py", "data.py", "system.py"]


class TestRLSEnforcement:
    """Verify all tenant-scoped routers pass org_id to db_manager.session()."""

    def test_tenant_routers_use_org_id(self):
        """Every db_manager.session() call in tenant routers must include org_id."""
        violations = []

        for router_name in TENANT_ROUTERS:
            router_path = ROUTERS_DIR / router_name
            if not router_path.exists():
                continue

            source = router_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(router_path))

            for node in ast.walk(tree):
                # Find calls like: db_manager.session(...)
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "session":
                    continue
                # Check the object is db_manager
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "db_manager":
                    # Check if org_id is passed as keyword argument
                    has_org_id = any(kw.arg == "org_id" for kw in node.keywords)
                    if not has_org_id:
                        violations.append(
                            f"{router_name}:{node.lineno} — "
                            f"db_manager.session() called without org_id"
                        )

        assert violations == [], (
            "RLS violation: the following db_manager.session() calls are missing org_id:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_all_tenant_routers_exist(self):
        """Ensure all expected tenant routers exist."""
        for router_name in TENANT_ROUTERS:
            router_path = ROUTERS_DIR / router_name
            assert router_path.exists(), f"Missing tenant router: {router_name}"

    def test_db_engine_session_supports_org_id(self):
        """Verify db_manager.session() accepts org_id parameter."""
        from src.db.engine import DatabaseSessionManager

        sig = inspect.signature(DatabaseSessionManager.session)
        assert (
            "org_id" in sig.parameters
        ), "DatabaseSessionManager.session() must accept org_id parameter for RLS"

    def test_db_engine_session_org_id_is_optional(self):
        """Verify org_id parameter has a default (Optional[str] = None)."""
        from src.db.engine import DatabaseSessionManager

        sig = inspect.signature(DatabaseSessionManager.session)
        param = sig.parameters["org_id"]
        assert (
            param.default is None
        ), "org_id parameter must default to None for backward compatibility"
