"""Shared application state singleton.

Extracted from main.py to break circular dependency:
graph.py needs app_state.indexer, and main.py needs graph imports.
This module has zero dependencies on main.py or graph.py.
"""


class AppState:
    """Shared application state initialized at startup."""

    indexer = None
    qdrant_available: bool = False
    llm_available: bool = False
    local_llm_available: bool = False
    scheduler = None  # AcquisitionScheduler when the opt-in refresh loop is on
    normattiva_client = None  # shared async client for CoVe URN validation


app_state = AppState()
