"""scripts/relabel_quoted_articles.py: relabel the chunks of amending acts in place.

The end-to-end test seeds an in-memory Qdrant (no server) twice with the same
two amending acts, through the real chunker, seed enrichment and HybridIndexer,
and a fake ``fastembed`` (no download): once with the labels the chunker gave
before the fix (``OLD_LABELS``), once with today's chunker. After --apply the
first collection must hold exactly the points of the second: same ids,
payloads, dense and BM25 vectors. relabel_act is also checked on its own: parts
of a long unit, a collection relabelled halfway, acts without quotations.
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from qdrant_client import QdrantClient

import src.pipeline as pipeline_mod
from src.config import get_settings
from src.nlp.chunking.contextual_chunker import ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker
from src.nlp.embedding.indexer import CORPUS_META_ID, HybridIndexer
from tests.test_chunking_amending_acts import AMENDING_AI, AMENDING_EN
from tests.test_reembed_collection import RecordingEmbedder, fake_fastembed

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "relabel_quoted_articles.py"
INDEXER_CLIENT = "src.nlp.embedding.indexer.QdrantClient"
MPNET = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
DIM = 4
QUOTED_CHAPTER = "‘CHAPTER 6c - DIGITAL SUPPORT MEASURES"

# What the chunker gave the article chunks of each act before the fix
# (hierarchy = article unless given).
OLD_LABELS = {
    "32026L0470": [
        {"article": "Art. 1", "title": "Amendments to Directive 2013/34/EU", "section_title": ""},
        {"article": "Art. ?", "title": "‘Article 29ca", "section_title": ""},
        {
            "article": "Art. 29e",
            "title": "Digital portal for sustainability reporting",
            "section_title": QUOTED_CHAPTER,
            "hierarchy": f"{QUOTED_CHAPTER} > Art. 29e",
        },
        {
            "article": "Art. 2",
            "title": "Transposition",
            "section_title": QUOTED_CHAPTER,
            "hierarchy": f"{QUOTED_CHAPTER} > Art. 2",
        },
    ],
    "32026R1744": [
        {
            "article": "Art. 1",
            "title": "Amendments to Regulation (EU) 2024/1689",
            "section_title": "",
        },
        {"article": "Art. ?", "title": "‘Article 75a", "section_title": ""},
        {
            "article": "Art. 75b",
            "title": "Supervision of testing in real world conditions",
            "section_title": "",
        },
        {"article": "Art. 75c", "title": "Guidance", "section_title": ""},
        {"article": "Art. 2", "title": "Entry into force", "section_title": ""},
    ],
}
ACTS = {"32026L0470": ("CSRD", AMENDING_EN), "32026R1744": ("AI_ACT", AMENDING_AI)}


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("relabel_quoted_articles", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def qdrant():
    client = QdrantClient(":memory:")
    with patch(INDEXER_CLIENT, return_value=client):
        yield client


def _chunks(celex: str, old: bool):
    framework, html = ACTS[celex]
    chunks = EURLexHTMLChunker(celex=celex, framework=framework, lang="EN").chunk_html(html)
    if old:
        for chunk, labels in zip(chunks, OLD_LABELS[celex], strict=True):
            labels = {"hierarchy": labels["article"], **labels}
            chunk.metadata.update(labels, article_number=labels["article"])
            chunk.metadata.update(quoted_article=None, amended_celex=None)
    return chunks


def _seed(collection: str, old: bool) -> None:
    """Seed both acts as the pipeline does, with the old or the current labels."""
    indexer = HybridIndexer(embedding_dim=DIM, collection_name=collection)
    indexer._embedder = RecordingEmbedder(DIM)
    indexer.setup_collection()
    pipeline = pipeline_mod.IngestionPipeline.__new__(pipeline_mod.IngestionPipeline)
    pipeline.contextual_chunker = ContextualChunker()
    for celex in ACTS:
        indexer.reindex_act(celex, "EN", pipeline._enrich(_chunks(celex, old)))
    indexer.write_corpus_meta(acts=[], corpus_as_of="2026-10-24", embedding_model=MPNET)


def _points(client: QdrantClient, collection: str) -> dict:
    records, _ = client.scroll(collection, limit=100, with_payload=True, with_vectors=True)
    out = {}
    for r in records:
        if str(r.id) == CORPUS_META_ID:
            continue
        payload = {k: v for k, v in (r.payload or {}).items() if k != "indexed_at"}
        out[str(r.id)] = (payload, r.vector)
    return out


def _settings(collection: str):
    return get_settings().model_copy(
        update={
            "qdrant_collection": collection,
            "embedding_model": MPNET,
            "embedding_dimension": DIM,
        }
    )


def test_apply_gives_the_points_a_fresh_seed_gives(script, qdrant, capsys):
    _seed("relabelled", old=True)
    _seed("fresh_seed", old=False)
    loaded: dict = {}
    with (
        patch.object(script, "get_settings", return_value=_settings("relabelled")),
        patch.dict("sys.modules", {"fastembed": fake_fastembed({MPNET: DIM}, loaded)}),
    ):
        assert script.main(["--apply"]) == 0
        out = capsys.readouterr().out
        assert script.main([]) == 0  # a second run finds nothing
        assert "relabelled: 0 chunks to relabel" in capsys.readouterr().out

    assert "relabelled: 6 chunks to relabel" in out
    assert "Art. ? -> Art. 1; quotes Art. 29ca of 32013L0034" in out
    assert f"Art. 2 -> Art. 2; section '{QUOTED_CHAPTER}' -> ''" in out
    assert "Art. 75b -> Art. 1; quotes Art. 75b of 32024R1689" in out
    relabelled, fresh = _points(qdrant, "relabelled"), _points(qdrant, "fresh_seed")
    assert set(relabelled) == set(fresh)  # new ids, old ones deleted
    for point_id, (payload, vectors) in fresh.items():
        assert relabelled[point_id][0] == payload
        assert relabelled[point_id][1]["bm25"] == vectors["bm25"]
        assert relabelled[point_id][1]["dense"] == pytest.approx(vectors["dense"])


def test_dry_run_writes_nothing(script, qdrant, capsys):
    _seed("relabelled", old=True)
    before = _points(qdrant, "relabelled")
    with patch.object(script, "get_settings", return_value=_settings("relabelled")):
        assert script.main([]) == 0
    assert _points(qdrant, "relabelled") == before
    assert "6 chunks to relabel" in capsys.readouterr().out


def test_apply_refuses_a_collection_of_another_model(script, qdrant, capsys):
    _seed("relabelled", old=True)
    other = _settings("relabelled").model_copy(update={"embedding_model": "intfloat/e5-x"})
    with patch.object(script, "get_settings", return_value=other):
        assert script.main(["--apply"]) == 2
    assert "refused" in capsys.readouterr().out


# ─── relabel_act ──────────────────────────────────────────────────


def _payload(article, part=None, text="x", section="", title="T", **extra):
    return {
        "chunk_type": "article",
        "article": article,
        "article_number": article,
        "title": title,
        "section_title": section,
        "hierarchy": f"{section} > {article}" if section else article,
        "part": part,
        "text": text,
        **extra,
    }


def test_every_part_of_a_quoted_unit_follows_its_first_part(script):
    payloads = [
        _payload("Art. 25", title="Amendments to Regulation (EU) 2019/2088", section="CHAPTER III"),
        _payload("Art. ?", part="1", text="«Article 2a\nPrinciple", section="CHAPTER III"),
        _payload("Art. ?", part="2", text="«Article 2a\n3. Power", section="CHAPTER III"),
        _payload("Art. 26", section="CHAPTER III"),
    ]
    new = script.relabel_act(payloads)
    assert new[0] is None and new[3] is None
    for labels in new[1:3]:
        assert labels == {
            "article": "Art. 25",
            "article_number": "Art. 25",
            "title": "Amendments to Regulation (EU) 2019/2088",
            "section_title": "CHAPTER III",
            "hierarchy": "CHAPTER III > Art. 25",
            "quoted_article": "Art. 2a",
            "amended_celex": "32019R2088",
        }


def test_a_collection_relabelled_halfway_is_finished(script):
    # A first run (before the rule for headings after a quoted article) fixed the
    # "Art. ?" unit but not the unquoted "Article 75b" that follows it.
    amending = "Amendments to Regulation (EU) 2024/1689"
    payloads = [
        _payload("Art. 1", title=amending),
        _payload(
            "Art. 1",
            title=amending,
            text="‘Article 75a\nMutual assistance",
            quoted_article="Art. 75a",
            amended_celex="32024R1689",
        ),
        _payload("Art. 75b", title="Supervision of testing", text="Article 75b\nSupervision"),
        _payload("Art. 2", title="Entry into force"),
    ]
    new = script.relabel_act(payloads)
    assert new[0] is None and new[1] is None and new[3] is None
    assert new[2]["article"] == "Art. 1"
    assert new[2]["title"] == amending
    assert (new[2]["quoted_article"], new[2]["amended_celex"]) == ("Art. 75b", "32024R1689")


def test_acts_without_quotations_and_other_chunks_are_left_alone(script):
    payloads = [
        {"chunk_type": "recital", "article": "Recital 1", "text": "(1) x"},
        _payload("Art. 1", section="CHAPTER I"),
        _payload("Art. 2", part="1", section="CHAPTER I"),
        _payload("Art. 2", part="2", section="CHAPTER I"),
        _payload("Art. 4a", section="CHAPTER II"),  # consolidated text: suffixes are fine
        {"chunk_type": "annex", "article": "Annex I", "section_title": "‘Part A’", "text": "y"},
    ]
    assert script.relabel_act(payloads) == [None] * len(payloads)
