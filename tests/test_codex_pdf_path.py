"""The Codex PDF served by GET /api/v1/codex/download must resolve to a real file.

Production used to answer 503 "Codex temporaneamente non disponibile" because
the router pointed at marketing/codex_post_omnibus_v1.pdf, a gitignored render
that never reached the image. The router now honours CODEX_PDF_PATH (set by the
Dockerfile to the copy baked into the image) and otherwise falls back to the
tracked copy under frontend/public/.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def leads_module():
    """Import the router and evict it afterwards: test_leads re-imports it
    against a MagicMock engine via sys.modules patching (see test_system_router)."""
    from src.api.routers import leads

    try:
        yield leads
    finally:
        sys.modules.pop("src.api.routers.leads", None)


def test_default_resolution_finds_a_pdf_in_the_repository(leads_module):
    assert leads_module.CODEX_PDF_PATH.is_file()
    assert leads_module.CODEX_PDF_PATH in leads_module._CODEX_PDF_CANDIDATES


def test_the_tracked_frontend_copy_is_a_candidate(leads_module):
    tracked = REPO_ROOT / "frontend" / "public" / "codex-post-omnibus-2025-2029.pdf"
    assert tracked.is_file(), "the Dockerfile COPYs this file into the image"
    assert tracked in leads_module._CODEX_PDF_CANDIDATES


def test_configured_path_wins_over_repository_candidates(leads_module):
    settings = MagicMock(codex_pdf_path="/app/assets/codex-post-omnibus-2025-2029.pdf")
    with patch.object(leads_module, "get_settings", return_value=settings):
        assert leads_module.resolve_codex_pdf_path() == Path(
            "/app/assets/codex-post-omnibus-2025-2029.pdf"
        )
