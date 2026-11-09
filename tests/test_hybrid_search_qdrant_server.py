"""hybrid_search against a Qdrant server: the one at QDRANT_HOST:QDRANT_PORT.

tests/test_hybrid_search_local_qdrant.py sends the same calls to qdrant-client's
in-process Qdrant, a Python re-implementation of the engine. Here they reach a
server, the qdrant/qdrant image of the CI service and the compose files: the
collection setup_collection creates (named dense vector, BM25 sparse vector
with the IDF modifier, keyword payload indexes), the points index_chunks writes,
and query_points with ``using=`` on each vector, under the filters
hybrid_search builds, also around the lookup of an article the query names.
The embedder counts topic words, so no model is downloaded. Each run writes to
a collection of its own and deletes it at the end. With no server ready
(locally, Docker off) the tests skip.
"""

import os
import uuid
from types import SimpleNamespace

import httpx
import pytest
from qdrant_client.models import Distance, Modifier, PayloadSchemaType

from src.nlp.embedding.indexer import (
    CORPUS_META_ID,
    DENSE_VECTOR,
    PAYLOAD_INDEX_FIELDS,
    SPARSE_VECTOR,
    HybridIndexer,
)

# 127.0.0.1, not localhost, when unset: the compose files publish Qdrant on
# 127.0.0.1 only, and on Windows localhost tries ::1 first (about 2 s a request).
QDRANT_HOST = os.environ.get("QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))

TOPICS = ("sustainability", "bank", "chatbot", "diligence")
ORG_A = "org-a"
ORG_B = "org-b"


class TopicEmbedder:
    """Stand-in for fastembed: one dimension per topic word, plus a constant."""

    def embed(self, texts):
        for text in texts:
            words = text.lower().split()
            yield [float(words.count(topic)) for topic in TOPICS] + [0.1]


def chunk(title: str, text: str, celex: str, framework: str, **metadata) -> SimpleNamespace:
    # The title names the chunk in the assertions.
    return SimpleNamespace(
        text=text,
        metadata={"title": title, "celex": celex, "framework": framework, **metadata},
    )


SHARED_CHUNKS = [
    chunk(
        "CSRD",
        "large undertakings shall publish sustainability reporting",
        "32022L2464",
        "CSRD",
        chunk_type="article",
    ),
    chunk(
        "DORA",
        "a bank shall manage ICT risk",
        "32022R2554",
        "DORA",
        article="Art. 6",
        chunk_type="article",
    ),
    chunk(
        "DORA recital",
        "whereas a bank shall notify major incidents",
        "32022R2554",
        "DORA",
        chunk_type="recital",
    ),
    chunk(
        "AI Act EN",
        "a chatbot shall tell people they talk to a machine",
        "32024R1689",
        "AI_ACT",
        lang="EN",
        chunk_type="article",
    ),
    chunk(
        "AI Act IT",
        "un chatbot deve dire alle persone che parlano con una macchina",
        "32024R1689",
        "AI_ACT",
        lang="IT",
        chunk_type="article",
    ),
    # Listed under two frameworks: CSRD is the primary one.
    chunk(
        "Omnibus I",
        "the omnibus postpones diligence and reporting dates",
        "32025L0794",
        "CSRD",
        frameworks=["CSRD", "CSDDD"],
        chunk_type="article",
    ),
    chunk(
        "NFRD",
        "large undertakings shall publish a non financial statement",
        "32014L0095",
        "CSRD",
        superseded_by="32022L2464",
        chunk_type="article",
    ),
]
# A document uploaded by ORG_A.
TENANT_CHUNKS = [
    chunk(
        "Acme policy",
        "acme shall tell clients when a chatbot answers",
        "acme-policy",
        "AI_ACT",
        article="Art. 3",
    )
]
# What a search finds with no filter of its own: the shared chunks in force.
IN_FORCE = {"CSRD", "DORA", "DORA recital", "AI Act EN", "AI Act IT", "Omnibus I"}


def found(results: list[dict]) -> list[str]:
    return sorted(r["title"] for r in results)


def server_ready() -> bool:
    try:
        return httpx.get(f"http://{QDRANT_HOST}:{QDRANT_PORT}/readyz", timeout=2).is_success
    except httpx.HTTPError:
        return False


def server_indexer(collection_name: str) -> HybridIndexer:
    idx = HybridIndexer(
        qdrant_host=QDRANT_HOST,
        qdrant_port=QDRANT_PORT,
        embedding_dim=len(TOPICS) + 1,
        collection_name=collection_name,
    )
    idx._embedder = TopicEmbedder()
    return idx


@pytest.fixture(scope="module")
def indexer():
    if not server_ready():
        pytest.skip(f"no Qdrant server ready at {QDRANT_HOST}:{QDRANT_PORT}")
    idx = server_indexer(f"pytest_hybrid_{uuid.uuid4().hex}")
    try:
        idx.setup_collection()
        idx.index_chunks(SHARED_CHUNKS)
        idx.index_chunks(TENANT_CHUNKS, org_id=ORG_A)
        idx.write_corpus_meta(acts=[])
        yield idx
    finally:
        if idx.client.collection_exists(idx.COLLECTION_NAME):
            idx.client.delete_collection(idx.COLLECTION_NAME)
        idx.client.close()


def test_setup_collection_creates_the_hybrid_schema(indexer):
    info = indexer.client.get_collection(indexer.COLLECTION_NAME)

    dense = info.config.params.vectors[DENSE_VECTOR]
    assert (dense.size, dense.distance) == (len(TOPICS) + 1, Distance.COSINE)
    assert info.config.params.sparse_vectors[SPARSE_VECTOR].modifier == Modifier.IDF
    assert set(info.payload_schema) == set(PAYLOAD_INDEX_FIELDS)
    assert {i.data_type for i in info.payload_schema.values()} == {PayloadSchemaType.KEYWORD}

    # A second indexer finds the collection and reads the IDF modifier back.
    again = server_indexer(indexer.COLLECTION_NAME)
    try:
        again.setup_collection()
        assert again.sparse_idf_enabled is True
    finally:
        again.client.close()


def test_the_two_rankings_are_fused(indexer):
    results = indexer.hybrid_search("sustainability reporting", limit=10, rrf_k=60)

    # First in both rankings: 1 / (60 + 1) from each.
    assert results[0]["title"] == "CSRD"
    assert results[0]["score"] == pytest.approx(2 / 61)
    # The only other chunk BM25 finds ("reporting") comes next, above the chunks
    # that only the dense search returns.
    assert results[1]["title"] == "Omnibus I"
    assert results[1]["sparse_score"] is not None
    assert [r["sparse_score"] for r in results[2:]] == [None] * 4
    # The dense search returns every chunk in force.
    assert all(r["dense_score"] is not None for r in results)
    assert found(results) == sorted(IN_FORCE)


def test_bm25_weighs_each_word_by_its_idf(indexer):
    results = indexer.hybrid_search("shall omnibus", limit=10)

    # Each chunk BM25 finds holds one of the two words, once: without IDF all
    # their scores would be equal. "shall" is in most chunks, "omnibus" in one.
    sparse = {r["title"]: r["sparse_score"] for r in results if r["sparse_score"] is not None}
    assert sorted(sparse) == ["AI Act EN", "CSRD", "DORA", "DORA recital", "Omnibus I"]
    assert sparse["Omnibus I"] > max(s for title, s in sparse.items() if title != "Omnibus I")


# Every chunk shares a word with this query and the dense search returns every
# chunk it may, so only the filter, applied to both searches, decides the results.
FILTER_QUERY = "shall chatbot reporting"


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        pytest.param({}, IN_FORCE, id="default"),
        pytest.param({"framework_filter": "CSRD"}, {"CSRD", "Omnibus I"}, id="framework"),
        pytest.param({"framework_filter": "CSDDD"}, {"Omnibus I"}, id="framework-in-list"),
        pytest.param(
            {"framework_filter": ["DORA", "AI_ACT"]},
            {"DORA", "DORA recital", "AI Act EN", "AI Act IT"},
            id="any-framework",
        ),
        pytest.param({"lang_filter": "IT"}, {"AI Act IT"}, id="lang"),
        pytest.param({"chunk_type_filter": "recital"}, {"DORA recital"}, id="chunk-type"),
        pytest.param({"include_superseded": True}, IN_FORCE | {"NFRD"}, id="superseded"),
        pytest.param({"org_id": ORG_A}, IN_FORCE | {"Acme policy"}, id="own-org"),
        pytest.param({"org_id": ORG_B}, IN_FORCE, id="other-org"),
        pytest.param({"allow_all_orgs": True}, IN_FORCE | {"Acme policy"}, id="all-orgs"),
    ],
)
def test_the_filters_reach_both_searches(indexer, filters, expected):
    results = indexer.hybrid_search(FILTER_QUERY, limit=10, **filters)

    assert found(results) == sorted(expected)


def test_a_named_article_joins_the_ranking(indexer):
    # "chatbot" points both searches at the AI Act chunks; the article the
    # question names (by its act's number) brings the DORA chunk first.
    named = indexer.hybrid_search(
        "Does Article 6 of Regulation (EU) 2022/2554 cover a chatbot", limit=10
    )
    unnamed = indexer.hybrid_search("Does Regulation (EU) 2022/2554 cover a chatbot", limit=10)

    assert named[0]["title"] == "DORA"
    assert named[0]["score"] > 2 / 61  # the lookup's share, plus the two searches'
    assert {r["title"] for r in unnamed[:2]} == {"AI Act EN", "AI Act IT"}


@pytest.mark.parametrize(("org_id", "acme_named"), [(ORG_A, True), (ORG_B, False)])
def test_the_lookup_keeps_the_tenant_filter(indexer, org_id, acme_named):
    # The tenant document is labelled "Art. 3" too: another organisation never gets it.
    results = indexer.hybrid_search(
        "What does art. 3 say about a chatbot", limit=10, framework_filter="AI_ACT", org_id=org_id
    )

    acme = [r for r in results if r["title"] == "Acme policy"]
    assert bool(acme) is acme_named
    if acme_named:
        assert acme[0]["score"] > 2 / 61


def test_the_corpus_meta_point_is_never_a_hit(indexer):
    assert indexer.get_corpus_info() is not None
    # Its placeholder vector points along "sustainability", and allow_all_orgs
    # drops the tenant filter its sentinel org_id fails: only its kind keeps it out.
    results = indexer.hybrid_search(
        "sustainability", limit=10, allow_all_orgs=True, include_superseded=True
    )

    assert CORPUS_META_ID not in {r["id"] for r in results}
    assert found(results) == sorted(IN_FORCE | {"NFRD", "Acme policy"})
