"""get_indexer: one indexer configuration for the API, the scheduler and the data router.

Found on 2026-10-26: the scheduler's update jobs and the data router's in-force
refresh built HybridIndexer() with its defaults, so inside Docker they looked
for Qdrant on localhost and ignored QDRANT_COLLECTION and EMBEDDING_MODEL.
"""

from types import SimpleNamespace
from unittest.mock import patch

from src.api.app_state import app_state, get_indexer


def test_reuses_the_api_indexer():
    shared = object()
    with patch.object(app_state, "indexer", shared):
        assert get_indexer() is shared


def test_builds_from_the_settings_outside_the_api():
    settings = SimpleNamespace(
        qdrant_host="qdrant",
        qdrant_port=6333,
        embedding_model="intfloat/multilingual-e5-large",
        embedding_dimension=1024,
        qdrant_collection="eu_regulations_e5",
    )
    with (
        patch.object(app_state, "indexer", None),
        patch("src.config.get_settings", return_value=settings),
        patch("src.nlp.embedding.indexer.HybridIndexer") as indexer_cls,
    ):
        get_indexer()
    indexer_cls.assert_called_once_with(
        qdrant_host="qdrant",
        qdrant_port=6333,
        embedding_model="intfloat/multilingual-e5-large",
        embedding_dim=1024,
        collection_name="eu_regulations_e5",
    )
