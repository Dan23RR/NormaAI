"""Where the document check reads the official texts by default.

One place for callers (the CLI, the API, the scheduled re-check) to get the
source and its cache folder, so that all of them read the same texts: EU acts
from CELLAR and Italian acts from Normattiva, behind one object.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from src.document_check.normattiva import NormattivaTextSource
from src.document_check.official import CellarTextSource

if TYPE_CHECKING:
    from src.document_check.normattiva import ItalianTextSource
    from src.document_check.official import ArticleText, TextSource, Version

# Overrides the cache folder (a volume in production, a temporary folder in tests).
CACHE_ENV = "NORMAAI_TEXT_CACHE"
# Italian articles are cached in this folder inside the cache folder.
NORMATTIVA_FOLDER = "normattiva"


def default_cache_dir() -> Path:
    """Folder of the downloaded official texts.

    ``$NORMAAI_TEXT_CACHE`` when set (the production container, whose root file
    system is read-only); otherwise the user cache, ``~/.cache/normaai/cellar``;
    when that cannot be created (no home, or a home that is not writable), a
    folder under the system temporary directory.
    """
    override = os.environ.get(CACHE_ENV, "").strip()
    if override:
        return Path(override)
    try:
        home = Path.home() / ".cache" / "normaai" / "cellar"
        home.mkdir(parents=True, exist_ok=True)
        if os.access(home, os.W_OK):
            return home
    except (OSError, RuntimeError):
        pass
    return Path(tempfile.gettempdir()) / "normaai" / "cellar"


class OfficialSources:
    """EU acts and Italian acts behind one source.

    ``versions`` and ``articles`` are those of the EU source (the ``TextSource``
    protocol); ``italian`` reads Italian law article by article. ``check`` asks
    for ``italian`` only when a document cites an Italian act, and a source
    without it leaves those references unchecked.
    """

    def __init__(self, eu: TextSource, italian: ItalianTextSource | None = None) -> None:
        self.eu = eu
        self.italian = italian

    def versions(self, celex: str) -> list[Version]:
        return self.eu.versions(celex)

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        return self.eu.articles(version, lang)

    @property
    def stale(self) -> dict[str, str]:
        """Acts whose list of versions is an older one, as the EU source reports them."""
        stale: dict[str, str] = getattr(self.eu, "stale", {})
        return stale


def default_source(cache_dir: Path | None = None) -> TextSource:
    """The source every caller should use: CELLAR for EU acts, Normattiva for Italian ones."""
    folder = cache_dir or default_cache_dir()
    return OfficialSources(
        CellarTextSource(folder), NormattivaTextSource(folder / NORMATTIVA_FOLDER)
    )
