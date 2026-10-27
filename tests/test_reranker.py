"""Cross-encoder reranking (src/nlp/embedding/reranker.py).

The fusion is the measured configuration of docs/MODELS.md, section 4: RRF of
the hybrid rank and the cross-encoder rank, so a candidate the hybrid search
ranks first survives a low cross-encoder score (the date questions the
cross-encoder alone lost) while a strong cross-encoder pick from further down
moves in. CrossEncoderReranker runs on a toy ONNX model and a toy tokenizer
built here: no download, no PyTorch.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from onnx import TensorProto, helper
from tokenizers import Tokenizer, models, pre_tokenizers, processors

from src.nlp.embedding.reranker import (
    CrossEncoderReranker,
    fused_order,
    rerank,
    rerank_text,
    reranker_from_settings,
)

# ─── fused_order ──────────────────────────────────────────────────


def test_agreeing_orders_are_kept():
    assert fused_order([5.0, 4.0, 3.0, 2.0]) == [0, 1, 2, 3]


def test_a_strong_pick_from_far_down_moves_into_the_top_15():
    scores = [-float(i) for i in range(30)]
    scores[25] = 100.0
    order = fused_order(scores)
    assert order[0] == 0
    assert order.index(25) < 15


def test_the_hybrid_best_survives_the_lowest_score():
    scores = [-float(i) for i in range(30)]
    scores[0] = -1000.0
    assert 0 in fused_order(scores)[:15]


def test_ties_keep_the_hybrid_order():
    assert fused_order([1.0] * 6) == list(range(6))
    assert fused_order([]) == []


# ─── rerank_text / rerank ─────────────────────────────────────────


def test_rerank_text_puts_the_labels_before_the_text():
    chunk = {
        "act_title": "AI Act",
        "article": "Art. 50",
        "section_title": "Transparency",
        "text": "Providers shall ensure...",
    }
    assert rerank_text(chunk) == "AI Act | Art. 50 | Transparency\nProviders shall ensure..."
    assert rerank_text({"title": "GDPR", "text": "x"}) == "GDPR\nx"
    assert rerank_text({"text": "only text"}) == "only text"


def test_rerank_keeps_the_fused_best_with_their_scores():
    candidates = [{"id": i, "text": f"t{i}"} for i in range(30)]
    scores = [-float(i) for i in range(30)]
    scores[25] = 100.0
    scorer = MagicMock()
    scorer.score.return_value = scores

    out = rerank("q", candidates, scorer, keep=15)

    scorer.score.assert_called_once_with("q", [f"t{i}" for i in range(30)])
    assert len(out) == 15
    assert out[0]["id"] == 0
    assert 25 in [c["id"] for c in out]
    assert out[0]["rerank_score"] == 0.0
    assert "rerank_score" not in candidates[0]  # the hybrid results are not mutated


def test_rerank_without_candidates_scores_nothing():
    scorer = MagicMock()
    assert rerank("q", [], scorer, keep=15) == []
    scorer.score.assert_not_called()


# ─── CrossEncoderReranker on a toy model ──────────────────────────

VOCAB = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, "q": 4, "a": 5, "b": 6, "c": 7, "d": 8}


def _toy_model_dir(tmp_path, with_token_types=True):
    """tokenizer.json + model.onnx whose logit counts the passage tokens.

    With token types the logit is the number of non-padding tokens of the second
    segment (the passage and its closing [SEP]); without, of the whole pair.
    """
    tokenizer = Tokenizer(models.WordLevel(VOCAB, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]",
        pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", 2), ("[SEP]", 3)],
    )
    tokenizer.save(str(tmp_path / "tokenizer.json"))

    names = ["input_ids", "attention_mask"] + (["token_type_ids"] if with_token_types else [])
    inputs = [helper.make_tensor_value_info(n, TensorProto.INT64, ["N", "S"]) for n in names]
    counted = "token_type_ids" if with_token_types else "attention_mask"
    nodes = [
        helper.make_node("Greater", ["input_ids", "minus_one"], ["is_token"]),  # uses input_ids
        helper.make_node("Cast", ["is_token"], ["ones"], to=TensorProto.INT64),
        helper.make_node("Mul", ["attention_mask", counted], ["kept"]),
        helper.make_node("Mul", ["kept", "ones"], ["counted"]),
        helper.make_node("Cast", ["counted"], ["counted_f"], to=TensorProto.FLOAT),
        helper.make_node("ReduceSum", ["counted_f", "axes"], ["logits"], keepdims=1),
    ]
    initializers = [
        helper.make_tensor("minus_one", TensorProto.INT64, [], [-1]),
        helper.make_tensor("axes", TensorProto.INT64, [1], [1]),
    ]
    output = helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", 1])
    graph = helper.make_graph(nodes, "toy_cross_encoder", inputs, [output], initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8  # readable by every onnxruntime FastEmbed 0.4.2 allows
    (tmp_path / "model.onnx").write_bytes(model.SerializeToString())
    return tmp_path


def test_scores_pairs_in_batches_with_padding(tmp_path):
    reranker = CrossEncoderReranker(_toy_model_dir(tmp_path), batch_size=2)
    # passage tokens + the closing [SEP]; lengths differ, so batches are padded
    assert reranker.score("q", ["a", "a b c", "a b"]) == [2.0, 4.0, 3.0]


def test_long_pairs_are_truncated_from_the_longer_side(tmp_path):
    reranker = CrossEncoderReranker(_toy_model_dir(tmp_path), max_length=6)
    # [CLS] q [SEP] + at most 2 passage tokens + [SEP] = 6
    assert reranker.score("q", ["a b c d", "a"]) == [3.0, 2.0]


def test_models_without_token_type_ids_get_none(tmp_path):
    reranker = CrossEncoderReranker(_toy_model_dir(tmp_path, with_token_types=False))
    assert reranker.score("q", ["a b"]) == [6.0]  # [CLS] q [SEP] a b [SEP]


def test_missing_files_are_named(tmp_path):
    with pytest.raises(FileNotFoundError, match="tokenizer.json"):
        CrossEncoderReranker(tmp_path)


def test_settings_switch_it_on_and_off(tmp_path):
    off = SimpleNamespace(reranker_model_dir="", reranker_onnx_file="model.onnx")
    assert reranker_from_settings(off) is None
    on = SimpleNamespace(
        reranker_model_dir=str(_toy_model_dir(tmp_path)), reranker_onnx_file="model.onnx"
    )
    reranker = reranker_from_settings(on)
    assert reranker is not None
    assert reranker.model_path == tmp_path / "model.onnx"
