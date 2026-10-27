"""Shared application state singleton.

Extracted from main.py to break circular dependency:
graph.py needs app_state.indexer, and main.py needs graph imports.
This module has zero dependencies on main.py or graph.py.
"""


class AppState:
    """Shared application state initialized at startup."""

    indexer = None
    reranker = None  # CrossEncoderReranker when RERANKER_MODEL_DIR is set
    qdrant_available: bool = False
    llm_available: bool = False
    local_llm_available: bool = False
    scheduler = None  # AcquisitionScheduler when the opt-in refresh loop is on
    normattiva_client = None  # shared async client for CoVe URN validation


app_state = AppState()


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
