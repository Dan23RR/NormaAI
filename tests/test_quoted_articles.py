"""Citing the articles that amending acts quote (src/agents/quoted_articles.py).

C: the consolidated text when it has the same wording; B: otherwise the
amended act's article as the amending act quotes it (first part of a quoted
unit only, cut where the quotation ends); A: anything else stays as retrieved.
The unit tests use plain dict chunks; the integration test chunks an amending
act and a consolidated act with the real chunker, indexes them in an
in-memory Qdrant and reads them back through HybridIndexer.article_chunks.
"""

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient

import src.pipeline as pipeline_mod
from src.agents.citation_verifier import verify_citations
from src.agents.nodes import retrieve_node
from src.agents.quoted_articles import quoted_span, resolve_quoted_articles
from src.nlp.chunking.contextual_chunker import ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker
from src.nlp.embedding.indexer import HybridIndexer
from tests.test_chunking_amending_acts import AMENDING_AI, AMENDING_EN
from tests.test_reembed_collection import RecordingEmbedder

PARAGRAPH = "1. Market surveillance authorities shall cooperate with each other on testing."


def _amending(text, part=None, quoted="Art. 75a", amended="32024R1689", **extra):
    return {
        "id": extra.pop("id", "amending-1"),
        "celex": "32026R1744",
        "article": "Art. 1",
        "framework": "AI_ACT",
        "lang": "EN",
        "part": part,
        "score": 0.5,
        "quoted_article": quoted,
        "amended_celex": amended,
        "text": text,
        **extra,
    }


def _consolidated(text, article="Art. 75a", id_="consolidated-75a"):
    return {
        "id": id_,
        "celex": "32024R1689",
        "article": article,
        "framework": "AI_ACT",
        "lang": "EN",
        "text": text,
    }


QUOTED_75A = (
    f"‘Article 75a\nMutual assistance\n{PARAGRAPH}’;\n(26) Article 77 is amended as follows:"
)
CONSOLIDATED_75A = f"Article 75a\nMutual assistance\n{PARAGRAPH}\n2. Other text."


# ─── quoted_span ──────────────────────────────────────────────────


def test_the_span_ends_where_the_quotation_closes():
    assert quoted_span({"text": QUOTED_75A}) == ["Mutual assistance", f"{PARAGRAPH}’;"]


def test_the_span_stops_before_an_amending_instruction():
    text = f"‘Article 75a\n{PARAGRAPH}\n(26) Article 77 is amended as follows:\n(a) x"
    assert quoted_span({"text": text}) == [PARAGRAPH]


@pytest.mark.parametrize(
    "first_line",
    [
        "(4) Article 11 is amended as follows:",
        "(a) paragraph 1 is replaced by the following:",
        "1) è inserito l’articolo seguente:",
        "«1. I sistemi di IA ad alto rischio sono progettati",  # another quotation
    ],
)
def test_no_span_when_the_body_starts_with_another_amendment(first_line):
    assert quoted_span({"text": f"«Article 2a\n{first_line}\nmore"}) == []


# ─── resolve_quoted_articles ──────────────────────────────────────


def test_c_the_consolidated_chunk_replaces_the_passage():
    lookup = MagicMock(return_value=[_consolidated(CONSOLIDATED_75A)])
    other = {"id": "gdpr-5", "celex": "32016R0679", "article": "Art. 5", "text": "x"}
    out = resolve_quoted_articles([other, _amending(QUOTED_75A)], lookup)

    lookup.assert_called_once_with("32024R1689", "Art. 75a", "EN")
    assert out[0] is other
    assert out[1]["id"] == "consolidated-75a"
    assert out[1]["text"] == CONSOLIDATED_75A
    assert out[1]["score"] == 0.5  # the rank the passage earned
    assert (out[1]["amended_by_celex"], out[1]["amended_by_article"]) == ("32026R1744", "Art. 1")


def test_c_a_consolidated_chunk_already_retrieved_is_not_added_twice():
    consolidated = _consolidated(CONSOLIDATED_75A)
    lookup = MagicMock(return_value=[consolidated])
    out = resolve_quoted_articles([_amending(QUOTED_75A), {**consolidated, "score": 0.1}], lookup)
    assert [c["id"] for c in out] == ["consolidated-75a"]
    assert out[0]["score"] == 0.1 and out[0]["amended_by_celex"] == "32026R1744"


def test_b_without_the_consolidated_article_the_quoted_text_is_cited_as_the_amended_one():
    out = resolve_quoted_articles([_amending(QUOTED_75A)], MagicMock(return_value=[]))
    assert out[0]["id"] == "amending-1"
    assert (
        out[0]["text"] == f"‘Article 75a\nMutual assistance\n{PARAGRAPH}’;"
    )  # cut at the quote end
    assert (out[0]["citation_celex"], out[0]["citation_article"]) == ("32024R1689", "Art. 75a")


def test_b_when_the_consolidated_text_has_another_wording():
    older = _consolidated(
        "Article 75a\nMutual assistance\n1. An older wording of the same article, longer."
    )
    out = resolve_quoted_articles([_amending(QUOTED_75A)], MagicMock(return_value=[older]))
    assert out[0]["id"] == "amending-1" and out[0]["citation_article"] == "Art. 75a"


def test_a_later_parts_without_the_consolidated_wording_stay_as_they_are():
    later = _amending(
        f"‘Article 75a\n(b) by 1 June 2022 for the objectives of points (c) to (f) of Article 9, {PARAGRAPH}",
        part="6",
    )
    out = resolve_quoted_articles([later], MagicMock(return_value=[]))
    assert out == [later]


def test_c_also_for_later_parts_with_the_consolidated_wording():
    later = _amending(f"‘Article 75a\n{PARAGRAPH}", part="2")
    out = resolve_quoted_articles(
        [later], MagicMock(return_value=[_consolidated(CONSOLIDATED_75A)])
    )
    assert out[0]["id"] == "consolidated-75a"


def test_a_passages_that_are_not_quoted_text_stay_as_they_are():
    instruction = _amending("‘Article 75a\n(26) Article 77 is amended as follows:")
    no_act = _amending(QUOTED_75A, amended=None)
    lookup = MagicMock(return_value=[])
    assert resolve_quoted_articles([instruction, no_act], lookup) == [instruction, no_act]
    lookup.assert_not_called()


def test_one_lookup_per_article_and_language():
    lookup = MagicMock(return_value=[])
    resolve_quoted_articles(
        [
            _amending(QUOTED_75A, id="a"),
            _amending(QUOTED_75A, id="b"),
            _amending(QUOTED_75A, id="c", lang="IT"),
        ],
        lookup,
    )
    assert lookup.call_count == 2


# ─── Verification of a B passage ──────────────────────────────────


def test_a_b_passage_is_verified_as_the_amended_article_found_in_the_amending_act():
    passage = resolve_quoted_articles([_amending(QUOTED_75A)], MagicMock(return_value=[]))[0]
    citation = {"framework": "32024R1689", "reference": "Art. 75a", "quote_snippet": PARAGRAPH}
    result = verify_citations([citation], [passage])[0]
    assert result.verified and result.level == "article"
    assert (result.celex, result.article) == ("32024R1689", "Art. 75a")
    assert (result.amending_celex, result.amending_article) == ("32026R1744", "Art. 1")
    assert result.url == "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1744"


def test_text_after_the_quotation_is_never_verified_as_the_quoted_article():
    passage = resolve_quoted_articles([_amending(QUOTED_75A)], MagicMock(return_value=[]))[0]
    citation = {
        "framework": "32024R1689",
        "reference": "Art. 75a",
        "quote_snippet": "Article 77 is amended as follows",
    }
    assert not verify_citations([citation], [passage])[0].verified


# ─── Integration: real chunks in Qdrant, through retrieve_node ────

CONSOLIDATED_AI = """<html><body>
<p class="oj-normal">HAVE ADOPTED THIS REGULATION:</p>
<p class="oj-ti-art">Article 75a</p>
<p class="oj-sti-art">Mutual assistance for market surveillance</p>
<p class="oj-normal">1. Market surveillance authorities shall cooperate with each other.</p>
<p class="oj-ti-art">Article 75b</p>
<p class="oj-sti-art">Supervision of testing in real world conditions</p>
<p class="oj-normal">1. Market surveillance authorities shall supervise the testing.</p>
<p class="oj-ti-art">Article 75c</p>
<p class="oj-sti-art">Guidance</p>
<p class="oj-normal">The Commission shall issue guidance on the application of this Section.</p>
</body></html>"""


@pytest.fixture
def indexer():
    client = QdrantClient(":memory:")
    with patch("src.nlp.embedding.indexer.QdrantClient", return_value=client):
        idx = HybridIndexer(embedding_dim=4, collection_name="eu_regulations")
        idx._embedder = RecordingEmbedder(4)
        idx.setup_collection()
        pipeline = pipeline_mod.IngestionPipeline.__new__(pipeline_mod.IngestionPipeline)
        pipeline.contextual_chunker = ContextualChunker()
        for celex, html in (
            ("32026R1744", AMENDING_AI),  # quotes Articles 75a-75c of the AI Act
            ("32024R1689", CONSOLIDATED_AI),  # the AI Act with them
            ("32026L0470", AMENDING_EN),  # quotes Article 29ca of Directive 2013/34/EU
        ):
            chunks = EURLexHTMLChunker(celex=celex, framework="AI_ACT", lang="EN").chunk_html(html)
            idx.reindex_act(celex, "EN", pipeline._enrich(chunks))
        yield idx


def test_article_chunks_reads_one_article_of_one_act(indexer):
    chunks = indexer.article_chunks("32024R1689", "Art. 75b", "EN")
    assert [(c["celex"], c["article"]) for c in chunks] == [("32024R1689", "Art. 75b")]
    assert chunks[0]["text"].startswith("Article 75b\nSupervision of testing")
    assert indexer.article_chunks("32024R1689", "Art. 75b", "IT") == []
    assert indexer.article_chunks("", "Art. 75b") == []


def test_retrieve_node_cites_the_consolidated_text_or_the_quoted_article(indexer):
    retrieved = indexer.article_chunks("32026R1744", "Art. 1", "EN") + indexer.article_chunks(
        "32026L0470", "Art. 1", "EN"
    )
    with (
        patch.object(indexer, "hybrid_search", return_value=retrieved),
        patch("src.api.app_state.app_state.indexer", indexer),
    ):
        out = retrieve_node({"query": "AI Act market surveillance"})["retrieved_chunks"]

    labels = [(c["celex"], c["article"], c.get("citation_article")) for c in out]
    assert labels == [
        ("32026R1744", "Art. 1", None),  # the amending article's own text (A)
        ("32024R1689", "Art. 75a", None),  # C: the consolidated articles
        ("32024R1689", "Art. 75b", None),
        ("32024R1689", "Art. 75c", None),
        ("32026L0470", "Art. 1", None),
        ("32026L0470", "Art. 1", "Art. 29ca"),  # B: Directive 2013/34/EU is not in the corpus
        ("32026L0470", "Art. 1", "Art. 29e"),  # B: the unquoted heading of the quoted chapter
    ]
    assert {c.get("amended_by_celex") for c in out[1:4]} == {"32026R1744"}
    b = out[5]
    assert b["citation_celex"] == "32013L0034"
    assert b["text"].endswith("the Commission shall adopt delegated acts.’;")


def test_retrieve_node_keeps_the_passages_when_the_lookup_fails():
    amending = _amending(QUOTED_75A)
    idx = MagicMock()
    idx.hybrid_search.return_value = [amending]
    idx.article_chunks.side_effect = RuntimeError("qdrant down")
    with patch("src.api.app_state.app_state.indexer", idx):
        out = retrieve_node({"query": "What does the AI Act require?"})
    assert out["retrieved_chunks"] == [amending]
