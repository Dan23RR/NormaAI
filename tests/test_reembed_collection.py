"""scripts/reembed_collection.py: copy a collection with another dense model.

main() runs against qdrant-client's in-process ``:memory:`` mode (no server, no
container) with a fake ``fastembed`` module, so no model is downloaded. SOURCE is
built by the real HybridIndexer from chunks of the real chunker + seed
enrichment. TARGET must come out with the same ids, payloads and sparse vectors,
each dense vector embedded on the seed's passage text behind the e5
"passage: " prefix, and a corpus meta point for the new model; SOURCE must be
left untouched.
"""

import importlib.util
import math
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, SparseVectorParams, VectorParams

import src.pipeline as pipeline_mod
from src.nlp.chunking.contextual_chunker import ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker
from src.nlp.embedding.indexer import (
    CORPUS_META_ID,
    CORPUS_META_KIND,
    HybridIndexer,
    stored_passage_text,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reembed_collection.py"
INDEXER_CLIENT = "src.nlp.embedding.indexer.QdrantClient"
MPNET = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
E5 = "intfloat/multilingual-e5-large"
SOURCE, TARGET = "eu_regulations", "eu_regulations_e5"
SOURCE_DIM, TARGET_DIM = 4, 6

SEED_HTML = """<html><body>
<p>CHAPTER II</p><p>REPORTING OBLIGATIONS</p>
<p>Article 19a</p><p>Sustainability reporting</p>
<p>1. Large undertakings shall include in the management report information necessary
to understand the undertaking's impacts on sustainability matters.</p>
<p>Article 29a</p><p>Consolidated sustainability reporting</p>
<p>1. Parent undertakings of a large group shall include in the consolidated management
report information necessary to understand the group's impacts on sustainability matters.</p>
</body></html>"""


@pytest.fixture(scope="module")
def script():
    """The script module, loaded from its file (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("reembed_collection", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def qdrant():
    """One in-memory Qdrant shared by every HybridIndexer built during the test."""
    client = QdrantClient(":memory:")
    with patch(INDEXER_CLIENT, return_value=client):
        yield client


def fake_vector(text: str, dim: int) -> list[float]:
    """A direction that depends on the text, so a stored vector can be traced back to it."""
    digest = zlib.crc32(text.encode("utf-8"))
    return [1.0, (digest % 997) / 997, (digest % 991) / 991] + [0.0] * (dim - 3)


def unit(vector) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


class RecordingEmbedder:
    """Stand-in for fastembed.TextEmbedding: records every text, returns fake_vector."""

    def __init__(self, dim: int):
        self.dim = dim
        self.texts: list[str] = []

    def embed(self, texts):
        for text in texts:
            self.texts.append(text)
            yield fake_vector(text, self.dim)


def fake_fastembed(dims: dict[str, int], loaded: dict[str, RecordingEmbedder]):
    """A ``fastembed`` module whose models are RecordingEmbedders (kept in ``loaded``)."""

    class TextEmbedding:
        def __init__(self, model_name, cache_dir=None):
            self._embedder = loaded.setdefault(model_name, RecordingEmbedder(dims[model_name]))

        def embed(self, texts):
            return self._embedder.embed(texts)

        @staticmethod
        def list_supported_models():
            return [{"model": name, "dim": dim} for name, dim in dims.items()]

    return SimpleNamespace(TextEmbedding=TextEmbedding)


def build_source() -> RecordingEmbedder:
    """SOURCE as a seed + an upload build it; returns the embedder that saw its passages."""
    source = HybridIndexer(embedding_dim=SOURCE_DIM, collection_name=SOURCE)  # mpnet
    embedder = RecordingEmbedder(SOURCE_DIM)
    source._embedder = embedder
    source.setup_collection()
    chunks = EURLexHTMLChunker(celex="32013L0034", framework="CSRD", lang="EN").chunk_html(
        SEED_HTML
    )
    pipeline = pipeline_mod.IngestionPipeline.__new__(pipeline_mod.IngestionPipeline)
    pipeline.contextual_chunker = ContextualChunker()
    source.reindex_act("32013L0034", "EN", pipeline._enrich(chunks))
    plain = [
        SimpleNamespace(text="Uploaded memo without context", metadata={"celex": "DOC_1"}),
        SimpleNamespace(text="", metadata={"celex": "DOC_2"}),  # empty sparse vector
    ]
    source.index_chunks(plain, org_id="org-1")
    source.write_corpus_meta(
        acts=[{"celex": "32013L0034", "lang": "EN", "chunks": len(chunks)}],
        corpus_as_of="2026-10-24",
        extra={"languages": ["EN"], "data_source": "eurlex"},
    )
    assert len(embedder.texts) >= 4
    return embedder


def snapshot(client: QdrantClient, name: str) -> dict:
    records, _ = client.scroll(name, limit=1000, with_payload=True, with_vectors=True)
    return {str(r.id): (r.payload, r.vector) for r in records}


def args(*extra: str) -> list[str]:
    return ["--source", SOURCE, "--target", TARGET, "--model", E5, "--dim", str(TARGET_DIM)] + [
        *extra
    ]


def test_reembeds_every_point_with_the_new_model(script, qdrant):
    source_embedder = build_source()
    before = snapshot(qdrant, SOURCE)
    loaded: dict = {}
    with patch.dict("sys.modules", {"fastembed": fake_fastembed({E5: TARGET_DIM}, loaded)}):
        code = script.main(args("--batch-size", "2"))  # several scroll pages

    assert code == 0
    assert snapshot(qdrant, SOURCE) == before  # SOURCE untouched
    after = snapshot(qdrant, TARGET)
    assert set(after) == set(before)  # same ids, corpus meta point included

    # Exactly the passages the seed embedded, now behind the e5 passage prefix.
    assert sorted(loaded[E5].texts) == sorted("passage: " + t for t in source_embedder.texts)
    for point_id, (payload, vectors) in after.items():
        if point_id == CORPUS_META_ID:
            continue
        source_payload, source_vectors = before[point_id]
        assert payload == source_payload
        assert vectors["bm25"] == source_vectors["bm25"]
        expected = fake_vector("passage: " + stored_passage_text(payload), TARGET_DIM)
        assert unit(vectors["dense"]) == pytest.approx(unit(expected))

    meta, meta_vectors = after[CORPUS_META_ID]
    assert meta["kind"] == CORPUS_META_KIND
    assert meta["embedding_model"] == E5
    assert meta["corpus_as_of"] == "2026-10-24"
    assert meta["acts"] == before[CORPUS_META_ID][0]["acts"]
    assert (meta["languages"], meta["data_source"]) == (["EN"], "eurlex")
    assert meta["reembedded_from"]["collection"] == SOURCE
    assert meta["reembedded_from"]["embedding_model"] == MPNET
    assert len(meta_vectors["dense"]) == TARGET_DIM

    layout = script.collection_layout(qdrant, TARGET)
    assert layout["dense"] == {"dense": TARGET_DIM}
    assert layout["sparse"] == {"bm25": "idf"}


def test_dry_run_prints_the_plan_and_writes_nothing(script, qdrant, capsys):
    build_source()
    before = snapshot(qdrant, SOURCE)
    loaded: dict = {}
    with patch.dict("sys.modules", {"fastembed": fake_fastembed({E5: TARGET_DIM}, loaded)}):
        code = script.main(args("--dry-run"))

    assert code == 0
    assert not qdrant.collection_exists(TARGET)
    assert loaded == {}  # no model loaded
    assert snapshot(qdrant, SOURCE) == before
    out = capsys.readouterr().out
    assert "passage prefix 'passage: '" in out
    assert f"{len(before) - 1} passages re-embedded" in out
    assert "Dry run: nothing written." in out


def test_help_needs_no_qdrant(script, capsys):
    with patch(INDEXER_CLIENT) as client_cls, pytest.raises(SystemExit) as exit_info:
        script.main(["--help"])
    assert exit_info.value.code == 0
    assert "--dry-run" in capsys.readouterr().out
    client_cls.assert_not_called()


def test_source_is_never_the_target(script):
    with pytest.raises(SystemExit) as exit_info:
        script.main(["--source", SOURCE, "--target", SOURCE, "--model", E5, "--dim", "6"])
    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("dims", "reason"),
    [({E5: TARGET_DIM + 1}, "dimensions"), ({}, "not in FastEmbed")],
)
def test_refuses_a_model_of_another_size_or_unknown(script, qdrant, capsys, dims, reason):
    build_source()
    with patch.dict("sys.modules", {"fastembed": fake_fastembed(dims, {})}):
        code = script.main(args())
    assert code == 2
    assert reason in capsys.readouterr().err
    assert not qdrant.collection_exists(TARGET)


def test_refuses_a_source_without_the_idf_modifier(script, qdrant, capsys):
    qdrant.create_collection(
        SOURCE,
        vectors_config={"dense": VectorParams(size=SOURCE_DIM, distance=Distance.COSINE)},
        sparse_vectors_config={"bm25": SparseVectorParams()},
    )
    with patch.dict("sys.modules", {"fastembed": fake_fastembed({E5: TARGET_DIM}, {})}):
        code = script.main(args())
    assert code == 2
    assert "no IDF modifier" in capsys.readouterr().err
    assert not qdrant.collection_exists(TARGET)


def test_existing_target_of_another_size_needs_recreate(script, qdrant, capsys):
    build_source()
    stale = HybridIndexer(embedding_dim=3, collection_name=TARGET)
    stale.setup_collection()
    loaded: dict = {}
    with patch.dict("sys.modules", {"fastembed": fake_fastembed({E5: TARGET_DIM}, loaded)}):
        assert script.main(args()) == 2
        assert "--recreate-target" in capsys.readouterr().err
        assert script.main(args("--recreate-target")) == 0
    assert script.collection_layout(qdrant, TARGET)["dense"] == {"dense": TARGET_DIM}


def test_unreachable_qdrant_is_reported(script, capsys):
    client = MagicMock()
    client.collection_exists.side_effect = ConnectionError("refused")
    with patch(INDEXER_CLIENT, return_value=client):
        code = script.main(args("--dry-run"))
    assert code == 1
    assert "cannot read Qdrant" in capsys.readouterr().err


def test_resume_embeds_only_the_points_target_lacks(script, qdrant):
    build_source()
    loaded: dict = {}
    fake = fake_fastembed({E5: TARGET_DIM}, loaded)
    with patch.dict("sys.modules", {"fastembed": fake}):
        assert script.main(args("--batch-size", "2")) == 0
    complete = {k: v for k, v in snapshot(qdrant, TARGET).items() if k != CORPUS_META_ID}
    missing = sorted(complete)[:2]
    # An interrupted run: two chunks never reached TARGET.
    qdrant.delete(TARGET, points_selector=PointIdsList(points=missing))
    loaded.clear()
    with patch.dict("sys.modules", {"fastembed": fake}):
        assert script.main(args("--batch-size", "2", "--resume")) == 0

    assert len(loaded[E5].texts) == 2  # only the missing points were embedded
    resumed = {k: v for k, v in snapshot(qdrant, TARGET).items() if k != CORPUS_META_ID}
    assert resumed == complete


def test_resume_and_recreate_exclude_each_other(script):
    with pytest.raises(SystemExit):
        script.main(args("--resume", "--recreate-target"))
