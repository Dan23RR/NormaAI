"""Where the document check reads the official texts by default.

One place for callers (the CLI, the API, the scheduled re-check) to get the
source and its cache folder, so that all of them read the same texts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from src.document_check.official import CellarTextSource

if TYPE_CHECKING:
    from src.document_check.official import TextSource

# Overrides the cache folder (a volume in production, a temporary folder in tests).
CACHE_ENV = "NORMAAI_TEXT_CACHE"


def default_cache_dir() -> Path:
    """Folder of the downloaded official texts: ``$NORMAAI_TEXT_CACHE`` or the user cache."""
    override = os.environ.get(CACHE_ENV, "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "normaai" / "cellar"


def default_source(cache_dir: Path | None = None) -> TextSource:
    """The source every caller should use: EU acts from CELLAR, cached on disk."""
    return CellarTextSource(cache_dir or default_cache_dir())
