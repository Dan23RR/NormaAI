"""Shared application state singleton.

Extracted from main.py to break circular dependency:
graph.py needs app_state.indexer, and main.py needs graph imports.
This module has zero dependencies on main.py or graph.py.
"""

import time
from typing import Any

# How long one process reuses the corpus date read from the collection.
CORPUS_DATE_TTL_SECONDS = 300.0
# (when it was read, the indexer it was read from, the date or None)
_corpus_date: tuple[float, Any, str | None] | None = None


class AppState:
    """Shared application state initialized at startup."""

    indexer = None
    reranker = None  # CrossEncoderReranker when RERANKER_MODEL_DIR is set
    qdrant_available: bool = False
    llm_available: bool = False
    local_llm_available: bool = False
    scheduler = None  # AcquisitionScheduler when the opt-in refresh loop is on
    # Read by CoVe to validate Italian URNs; None since the old Normattiva client
    # (endpoints answering HTTP 409) was removed, so CoVe skips them.
    normattiva_client = None


app_state = AppState()


def corpus_as_of(fallback: str | None = None) -> str | None:
    """The corpus date the API shows ("Corpus al ..."), or ``fallback``.

    The date the seed or ``python -m src.pipeline --action update`` recorded
    in the collection (its corpus_meta point, HybridIndexer.get_corpus_info()),
    so it moves with the corpus instead of waiting for someone to edit
    CORPUS_AS_OF. Without Qdrant, without the point (a collection seeded
    before it existed) or without a date in it: ``fallback``, the CORPUS_AS_OF
    setting the caller passes. Read once every 5 minutes per process; never
    raises.
    """
    global _corpus_date
    indexer = app_state.indexer
    fallback = str(fallback).strip() if fallback else None
    if indexer is None or not app_state.qdrant_available:
        return fallback or None
    now = time.monotonic()
    if (
        _corpus_date is not None
        and _corpus_date[1] is indexer
        and now - _corpus_date[0] < CORPUS_DATE_TTL_SECONDS
    ):
        return _corpus_date[2] or fallback or None
    recorded: str | None = None
    try:
        info = indexer.get_corpus_info()
        if isinstance(info, dict) and isinstance(info.get("corpus_as_of"), str):
            recorded = info["corpus_as_of"].strip() or None
    except Exception:  # noqa: BLE001 - Qdrant down: the setting, as before
        recorded = None
    _corpus_date = (now, indexer, recorded)
    return recorded or fallback or None


def reset_corpus_date() -> None:
    """Forget the cached date (tests; the next call reads the collection again)."""
    global _corpus_date
    _corpus_date = None


def get_indexer():
    """The API's shared HybridIndexer, or one built from the settings outside the API.

    A bare HybridIndexer() uses its own defaults (localhost, the default
    collection and dense model), which miss Qdrant inside Docker and any other
    configured collection or model. Reusing the API's instance also avoids
    loading the dense model twice in one process.
    """
    if app_state.indexer is not None:
        return app_state.indexer
    from src.config import get_settings
    from src.nlp.embedding.indexer import HybridIndexer, indexer_kwargs_from_settings

    return HybridIndexer(**indexer_kwargs_from_settings(get_settings()))
