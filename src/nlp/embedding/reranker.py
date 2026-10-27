"""
Cross-encoder reranking of the hybrid search candidates (optional, off by default).

The hybrid search returns more candidates than the agents read; a cross-encoder
scores each (question, passage) pair, and its ranking is fused with the hybrid
ranking by Reciprocal Rank Fusion. Candidates the hybrid search ranks first keep
their place unless the cross-encoder ranks them low too, and the cross-encoder's
picks from further down move in. Replacing the hybrid order outright lost date
questions the hybrid search answers (docs/MODELS.md, section 4).

The model is an ONNX export of a cross-encoder (one logit per pair) read from a
local directory holding the .onnx file and its ``tokenizer.json``. It runs on
onnxruntime and tokenizers, which FastEmbed already installs: no PyTorch.
"""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Same constant as the hybrid search's own fusion (HybridIndexer.hybrid_search).
RERANK_RRF_K = 60
# Tokens per (question, passage) pair, as measured on golden v2 (docs/MODELS.md).
RERANK_MAX_LENGTH = 384


class PairScorer(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Scores (query, passage) pairs with an ONNX cross-encoder on the CPU."""

    def __init__(
        self,
        model_dir: str | Path,
        onnx_file: str = "model.onnx",
        max_length: int = RERANK_MAX_LENGTH,
        batch_size: int = 16,
    ) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = Path(model_dir)
        model_path, tokenizer_path = model_dir / onnx_file, model_dir / "tokenizer.json"
        missing = [str(p) for p in (model_path, tokenizer_path) if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"reranker files missing: {', '.join(missing)}")

        self.model_path = model_path
        self.batch_size = batch_size
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_length=max_length, strategy="longest_first")
        # XLM-R models pad with "<pad>", BERT models with "[PAD]". The value only
        # fills masked positions, so a tokenizer with neither pads with id 0.
        pad_token = next(
            (t for t in ("<pad>", "[PAD]") if self.tokenizer.token_to_id(t) is not None), None
        )
        pad_id = self.tokenizer.token_to_id(pad_token) if pad_token else 0
        self.tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token or "[PAD]")

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """One relevance logit per passage, higher is more relevant."""
        import numpy as np

        scores: list[float] = []
        for start in range(0, len(passages), self.batch_size):
            batch = passages[start : start + self.batch_size]
            encodings = self.tokenizer.encode_batch([(query, p) for p in batch])
            feeds = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            }
            if "token_type_ids" in self._input_names:  # BERT-style pair segments
                feeds["token_type_ids"] = np.array([e.type_ids for e in encodings], dtype=np.int64)
            logits = self.session.run(None, feeds)[0]
            scores.extend(float(x) for x in np.asarray(logits).reshape(len(batch), -1)[:, 0])
        return scores


def reranker_from_settings(settings: Any) -> CrossEncoderReranker | None:
    """The configured reranker, or None when RERANKER_MODEL_DIR is empty (off)."""
    if not settings.reranker_model_dir:
        return None
    return CrossEncoderReranker(settings.reranker_model_dir, onnx_file=settings.reranker_onnx_file)


def rerank_text(chunk: dict[str, Any]) -> str:
    """What the cross-encoder reads: act title, article and section title, then the text."""
    header = " | ".join(
        str(x)
        for x in (
            chunk.get("act_title") or chunk.get("title"),
            chunk.get("article"),
            chunk.get("section_title"),
        )
        if x
    )
    text = chunk.get("text") or ""
    return f"{header}\n{text}" if header else text


def fused_order(scores: Sequence[float], k: int = RERANK_RRF_K) -> list[int]:
    """Candidate positions, best first, by RRF of the hybrid rank and the score rank.

    ``scores`` follow the hybrid order (position 0 is the hybrid search's best).
    Ties keep the hybrid order.
    """
    by_score = sorted(range(len(scores)), key=lambda i: -scores[i])
    score_rank = {i: rank for rank, i in enumerate(by_score)}
    return sorted(
        range(len(scores)),
        key=lambda i: -(1.0 / (k + i + 1) + 1.0 / (k + score_rank[i] + 1)),
    )


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    scorer: PairScorer,
    keep: int,
    k: int = RERANK_RRF_K,
) -> list[dict[str, Any]]:
    """The ``keep`` best candidates by fused rank, each with its ``rerank_score``."""
    if not candidates:
        return []
    scores = scorer.score(query, [rerank_text(c) for c in candidates])
    return [{**candidates[i], "rerank_score": scores[i]} for i in fused_order(scores, k)[:keep]]
