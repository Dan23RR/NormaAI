# Model registry

> Every model NormaAI uses or is evaluating, by role: licence, source, when it was
> checked and what it scored on our golden set. Update it whenever a default changes,
> a candidate is measured or a licence is re-checked.

**Licences are to re-check on the model card before use.** They are recorded as noted
on the date in the *Checked* column, and a licence can change between versions of the
same model.

*Checked* says where a row comes from: **code** = read from `src/` on that date;
**FastEmbed** = from the model list of the installed FastEmbed 0.4.2 (name, size,
licence); **notes** = from the evaluation notes, model card not re-read yet.
*Measured* lists results on golden v2 recorded in this file; "—" means none.

---

## 1. Measured baseline (2026-10-24)

Configuration measured on golden v2 (101 questions, see
[tests/validation/GOLDEN_V2.md](../tests/validation/GOLDEN_V2.md)):

| Role | Model |
|---|---|
| Dense embedding | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768 dims) |
| Sparse vectors | hashed term frequencies + Qdrant IDF modifier (no model) |
| Fusion / reranking | Reciprocal Rank Fusion (k=60), no reranker |
| LLM | Claude Haiku 5.5 (`LLM_PROVIDER=anthropic`, `ANTHROPIC_MODEL=claude-haiku-5-5`) |

| Measure | Result | Command |
|---|---|---|
| Golden v2 end to end: questions passed | 84 / 101 | `python -m tests.validation.runner --suite golden_v2 --api` |
| Recall of the expected citation | 0.83 | same run |
| Citations verified word for word | 99.6 % | same run |
| Retrieval only: expected article in the top 15 | 77 / 90 | `python -m tests.validation.retrieval_eval --label <name>` |

84 / 101 and 0.83 are the run of 2026-10-24 scored with the article matching fixed in
commit `c71d5fb` ("Art. 19 bis" equals "Art. 19a"; spaces separate article parts). The
report the runner wrote before that fix shows 82 / 101 and recall 0.81 for the same answers.

The retrieval-only measure covers the 90 questions that expect an article (the others
test abstention) and makes no LLM call, so it is the first gate for any retrieval change:
dense model, sparse vectors, reranker.

## 2. Dense embedding

Set by `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION`. Vectors live in a model-specific
space: a new model needs a collection re-embedded with it (§6).

| Model | Status | Dims | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|---|
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | **in use** (default) | 768 | Apache-2.0 | [model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2), FastEmbed 0.4.2 | 2026-10-26 code, FastEmbed | baseline, §1 |
| `intfloat/multilingual-e5-large` | candidate, next A/B | 1024 | MIT | [model card](https://huggingface.co/intfloat/multilingual-e5-large), FastEmbed 0.4.2 | 2026-10-26 FastEmbed | — |
| `BAAI/bge-m3` | candidate | — | MIT | [model card](https://huggingface.co/BAAI/bge-m3); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `Qwen/Qwen3-Embedding-0.6B`, `Qwen/Qwen3-Embedding-4B` | candidate | — | Apache-2.0 | [0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), [4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `nvidia/NV-Embed-v2` | **excluded** (§7) | — | CC-BY-NC-4.0 | [model card](https://huggingface.co/nvidia/NV-Embed-v2) | 2026-10-26 notes | — |

- **multilingual-e5-large** is trained with `query: ` before queries and `passage: `
  before documents. The indexer adds them (`EMBEDDING_PREFIXES` in
  `src/nlp/embedding/indexer.py`), so the model needs only the settings and a
  re-embedded collection. Its ONNX weights are ~2.2 GB (~1.0 GB for mpnet).
- **bge-m3** and **Qwen3-Embedding** need a runtime other than FastEmbed 0.4.2, or a
  FastEmbed release that lists them. bge-m3 can also produce sparse lexical weights
  (§3). The Qwen3-Embedding model card recommends a task instruction before queries,
  which would need its own `EMBEDDING_PREFIXES` entry.

## 3. Sparse vectors

| Model | Status | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|
| Hashed term frequencies (MD5 into 30,000 buckets, `log(1 + tf)`) with Qdrant `Modifier.IDF`, BM25-style | **in use** | own code | `_text_to_sparse_vector` in `src/nlp/embedding/indexer.py` | 2026-10-26 code | baseline, §1 |

No learned sparse model is in use or lined up; bge-m3 (§2) is the obvious one to try.
The re-embed script copies the sparse vectors unchanged, so changing them needs a
reseed (`python -m src.pipeline --action seed --recreate`).

## 4. Reranker

| Model | Status | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|
| none: the fused hybrid results go to the LLM as they are | **in use** | — | `hybrid_search` in `src/nlp/embedding/indexer.py` | 2026-10-26 code | baseline, §1 |
| `BAAI/bge-reranker-v2-m3` | candidate | Apache-2.0 | [model card](https://huggingface.co/BAAI/bge-reranker-v2-m3); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `Qwen/Qwen3-Reranker-0.6B` | candidate | Apache-2.0 | [model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `jinaai/jina-reranker-v2-base-multilingual` | **excluded** (§7) | CC-BY-NC-4.0 | [model card](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual), FastEmbed 0.4.2 | 2026-10-26 notes, FastEmbed | — |

## 5. LLM

`LLM_PROVIDER` (default `gemini`) picks the provider; each provider has one analysis
model, set by the variable in brackets.

| Model | Status | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|
| `gemini-3.6-flash` | **default** (`LLM_PROVIDER=gemini`, `GEMINI_MODEL`) | provider terms | Google Gemini API | 2026-10-26 code | — |
| `claude-sonnet-5-5` | default for `LLM_PROVIDER=anthropic` (`ANTHROPIC_MODEL`) | provider terms | Anthropic API | 2026-10-26 code | — |
| `claude-haiku-5-5` | measured (`ANTHROPIC_MODEL=claude-haiku-5-5`) | provider terms | Anthropic API | 2026-10-24 | 84 / 101, recall 0.83, 99.6 % verified (§1) |
| `nvidia/nemotron-3-super-120b-a12b:free` | default for `LLM_PROVIDER=openrouter` (`OPENROUTER_MODEL_ANALYSIS`) | provider terms | OpenRouter | 2026-10-26 code | — |
| `qwen3.5:4b` | local router, off by default (`LOCAL_LLM_ENABLED`, `LOCAL_LLM_MODEL`) | to check | Ollama | 2026-10-26 code | — |
| Mistral Small 4 | candidate: sovereign LLM (EU provider, open weights) | Apache-2.0 | Mistral AI | 2026-10-26 notes | — |
| Llama 4 | **excluded** (§7) | Llama 4 Community License + Acceptable Use Policy | Meta | 2026-10-26 notes | — |

## 6. Changing the dense model

1. **Settings**: `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` and `QDRANT_COLLECTION`. The
   API, the agents' retrieval and the seed pipeline build their indexer from these
   (`indexer_kwargs_from_settings`). The background scheduler
   (`src/crawler/scheduler.py`) and the in-force refresh of `src/api/routers/data.py`
   still use the indexer defaults.
2. **Vectors**: re-embed the corpus into a new collection, keeping ids, payloads and
   BM25 vectors, or reseed with `--recreate`. Try `--dry-run` first:

   ```bash
   python scripts/reembed_collection.py --source eu_regulations --target eu_regulations_e5 --model intfloat/multilingual-e5-large --dim 1024
   ```
3. **Prefixes**: a model trained with input prefixes needs an `EMBEDDING_PREFIXES` entry,
   otherwise it silently loses accuracy. e5 is listed.
4. **Docker image**: the Dockerfile bakes only mpnet into `/app/models` and the runtime
   filesystem is read-only. Bake the new model too, or the API cannot load it.
5. **SNC**: `SNC_WEAK_EVIDENCE_DENSE_SCORE` (0.25) is a raw cosine threshold set on mpnet
   scores. e5 models give cosine scores in a narrow, high band, so recalibrate it before
   enabling SNC with another model.
6. **Measure**: retrieval only first, then golden v2 end to end; record both here.

## 7. Excluded models

- `nvidia/NV-Embed-v2` and `jinaai/jina-reranker-v2-base-multilingual`: CC-BY-NC-4.0,
  non-commercial use only.
- Llama 4: its Acceptable Use Policy does not grant the multimodal Llama 4 models to
  companies based in the EU.

## History

| Date | Change |
|---|---|
| 2026-10-24 | Baseline measured (§1) |
| 2026-10-26 | Registry created; the indexer adds the e5 prefixes; re-embed script and retrieval-only evaluation in the repository |
