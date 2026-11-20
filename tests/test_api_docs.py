"""/docs, /redoc and /openapi.json are not served in production.

The app is built at import time from the settings, so each case imports
src.api.main afresh under the settings it needs (and evicts it afterwards, like
the router tests do). The landing page drops its links to the docs there too.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _restore_module_cache():
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
            or name == "src.api.landing"
        ):
            sys.modules.pop(name, None)


def _app_under(app_env: str):
    settings = get_settings().model_copy(update={"app_env": app_env})
    for name in ("src.api.main", "src.api.landing"):
        sys.modules.pop(name, None)
    with (
        patch("src.config.get_settings", return_value=settings),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        from src.api.main import app

        client = TestClient(app)
        responses = {path: client.get(path) for path in ("/docs", "/redoc", "/openapi.json", "/")}
    return app, responses


def test_production_serves_no_docs():
    app, responses = _app_under("production")
    assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert responses[path].status_code == 404, path
    landing = responses["/"]
    assert landing.status_code == 200
    assert 'href="/docs"' not in landing.text
    assert 'href="/redoc"' not in landing.text


@pytest.mark.parametrize("app_env", ["development", "testing", "staging"])
def test_elsewhere_the_docs_are_served(app_env):
    app, responses = _app_under(app_env)
    assert app.openapi_url == "/openapi.json"
    assert responses["/docs"].status_code == 200
    assert responses["/openapi.json"].status_code == 200
    assert "/api/v1/auth/password-reset" in responses["/openapi.json"].json()["paths"]
    assert 'href="/docs"' in responses["/"].text


def test_the_setting():
    base = {"_env_file": None, "app_secret_key": "x" * 40}
    assert Settings(**base, app_env="production").api_docs_enabled is False
    assert Settings(**base, app_env="development").api_docs_enabled is True
