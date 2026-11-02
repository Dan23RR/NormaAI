"""hybrid_search through qdrant-client's in-process Qdrant (``:memory:``).

The unit tests in tests/test_indexer.py mock _query_points. These send the real
requests: the collection setup_collection creates (named dense vector, BM25
sparse vector with IDF), points written by index_chunks, and query_points with
``using=`` on each vector, the only search path since qdrant-client 1.19
removed .search() and NamedVector. No server and no model download: the
embedder counts topic words.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from qdrant_client import QdrantClient

from src.nlp.embedding.indexer import HybridIndexer

INDEXER_CLIENT = "src.nlp.embedding.indexer.QdrantClient"
TOPICS = ("sustainability", "bank", "chatbot")


class TopicEmbedder:
    """Stand-in for fastembed: one dimension per topic word, plus a constant."""

    def embed(self, texts):
        for text in texts:
            words = text.lower().split()
            yield [float(words.count(topic)) for topic in TOPICS] + [0.1]


def chunk(text: str, celex: str, framework: str) -> SimpleNamespace:
    return SimpleNamespace(text=text, metadata={"celex": celex, "framework": framework})


@pytest.fixture
def indexer():
    client = QdrantClient(":memory:")
    with patch(INDEXER_CLIENT, return_value=client):
        idx = HybridIndexer(embedding_dim=len(TOPICS) + 1, collection_name="eu_regulations_test")
        idx._embedder = TopicEmbedder()
        idx.setup_collection()
        idx.index_chunks(
            [
                chunk("sustainability reporting by large undertakings", "32022L2464", "CSRD"),
                chunk("bank operational resilience and ICT risk", "32022R2554", "DORA"),
                chunk("a chatbot tells people they talk to a machine", "32024R1689", "AI_ACT"),
            ]
        )
        yield idx
    client.close()


def test_both_vectors_are_searched_and_fused(indexer):
    results = indexer.hybrid_search("sustainability reporting", limit=3)

    assert results[0]["celex"] == "32022L2464"
    # The top chunk came back from the dense search and from the BM25 one.
    assert results[0]["dense_score"] is not None
    assert results[0]["sparse_score"] is not None


def test_the_filter_reaches_both_searches(indexer):
    results = indexer.hybrid_search("sustainability reporting", limit=3, framework_filter="DORA")

    assert [r["celex"] for r in results] == ["32022R2554"]
