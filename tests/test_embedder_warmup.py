"""The API loads the dense model at startup, not on the first question.

Found in the live golden run of 2026-10-27: on a fresh process the first two
questions, arriving together, both built the model and one failed with a 503.
The startup now embeds once ("warm-up"); a failure there is logged and leaves
the lazy load of src.nlp.embedding.indexer to the first question.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app_state import app_state


def _start_and_stop_the_app(indexer_module: MagicMock) -> None:
    """Run the real lifespan with the indexer module and the database mocked."""
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": indexer_module, "src.db.engine": MagicMock()},
        ),
        patch.object(app_state, "indexer", None),
        patch.object(app_state, "qdrant_available", False),
    ):
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from src.api.main import app

        with TestClient(app, raise_server_exceptions=False):
            pass


def test_startup_embeds_once_to_load_the_model():
    indexer_module = MagicMock()
    _start_and_stop_the_app(indexer_module)
    indexer = indexer_module.HybridIndexer.return_value
    indexer.embed_query.assert_called_once_with("warm-up")


def test_a_failed_warm_up_does_not_stop_the_api():
    indexer_module = MagicMock()
    indexer_module.HybridIndexer.return_value.embed_query.side_effect = OSError("no model files")
    _start_and_stop_the_app(indexer_module)  # no exception: the first question retries


def test_no_warm_up_without_qdrant():
    indexer_module = MagicMock()
    indexer_module.HybridIndexer.return_value.setup_collection.side_effect = ConnectionError()
    _start_and_stop_the_app(indexer_module)
    indexer_module.HybridIndexer.return_value.embed_query.assert_not_called()
