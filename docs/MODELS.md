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
| Retrieval only: expected article in the top 15 | 80 / 90 | `python -m tests.validation.retrieval_eval --label <name>` |

84 / 101 and 0.83 are the run of 2026-10-24 scored with the article matching fixed in
commit `c71d5fb` ("Art. 19 bis" equals "Art. 19a"; spaces separate article parts). The
report the runner wrote before that fix shows 82 / 101 and recall 0.81 for the same answers.
The retrieval-only measure got the same fix in commit `49d669b`: 77 / 90 on 2026-10-24,
80 / 90 for the same collection read the new way (the difference is CSRD, Art. 19a and 29a).

The retrieval-only measure covers the 90 questions that expect an article (the others
test abstention) and makes no LLM call, so it is the first gate for any retrieval change:
dense model, sparse vectors, reranker. Measured since: multilingual-e5-large (§2.1) and a
cross-encoder reranker (§4.1).

## 2. Dense embedding

Set by `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION`. Vectors live in a model-specific
space: a new model needs a collection re-embedded with it (§6).

| Model | Status | Dims | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|---|
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | **in use** (default) | 768 | Apache-2.0 | [model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2), FastEmbed 0.4.2 | 2026-10-26 code, FastEmbed | baseline, §1 |
| `intfloat/multilingual-e5-large` | candidate, measured (§2.1) | 1024 | MIT | [model card](https://huggingface.co/intfloat/multilingual-e5-large), FastEmbed 0.4.2 | 2026-10-26 FastEmbed | 83 / 90 retrieval only; 86 / 90 with the reranker (§2.1) |
| `BAAI/bge-m3` | candidate | — | MIT | [model card](https://huggingface.co/BAAI/bge-m3); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `Qwen/Qwen3-Embedding-0.6B`, `Qwen/Qwen3-Embedding-4B` | candidate | — | Apache-2.0 | [0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), [4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `nvidia/NV-Embed-v2` | **excluded** (§7) | — | CC-BY-NC-4.0 | [model card](https://huggingface.co/nvidia/NV-Embed-v2) | 2026-10-26 notes | — |

- **Passage length** (measured 2026-10-27). The chunks are long for mpnet: median 323
  tokens, 90th percentile 439, and 83 % are longer than the 128 tokens mpnet is
  configured for (`max_seq_length` in its `sentence_bert_config.json`); FastEmbed lets it
  read up to 512. multilingual-e5-large reads 512 tokens, enough for 99 % of the
  chunks. With mpnet, the best AI Act Art. 50 chunk ranks between about 260th and 370th
  in the dense search for the four chatbot questions of `retrieval_eval`, so for the
  main chatbot question it is not even among the reranker's candidates.
- **multilingual-e5-large** is trained with `query: ` before queries and `passage: `
  before documents. The indexer adds them (`EMBEDDING_PREFIXES` in
  `src/nlp/embedding/indexer.py`), so the model needs only the settings and a
  re-embedded collection. Its ONNX weights are ~2.2 GB (~1.0 GB for mpnet).
- **bge-m3** and **Qwen3-Embedding** need a runtime other than FastEmbed 0.4.2, or a
  FastEmbed release that lists them. bge-m3 can also produce sparse lexical weights
  (§3). The Qwen3-Embedding model card recommends a task instruction before queries,
  which would need its own `EMBEDDING_PREFIXES` entry.

### 2.1 Measured: multilingual-e5-large, retrieval only, 2026-10-27

Collection `eu_regulations_e5`: the 5,851 passages of `eu_regulations` with the same ids,
payloads and BM25 vectors, dense vectors re-embedded with multilingual-e5-large
(`scripts/reembed_collection.py`). Same measure as §1 and §4.1: expected article among
the chunks the agents read, 90 golden v2 questions. The reranker is the int8 cross-encoder
of §4.1, over 30 candidates; the search depth is explained below.

| Dense model | Hybrid search, 15 results | Reranker, search depth 90 | Reranker, search depth 45 |
|---|---|---|---|
| mpnet (in use) | 80 / 90 | **88 / 90** | 83 / 90 |
| multilingual-e5-large | 83 / 90 | 87 / 90 | 86 / 90 |

AI Act Art. 50 among the chunks the agents read, for the four chatbot questions of
`retrieval_eval`; in brackets, its position for the first one ("Il chatbot sul sito della
nostra azienda deve dichiarare di essere un'intelligenza artificiale? Da quando?"):

| Dense model | Hybrid search, 15 results | Reranker, search depth 90 | Reranker, search depth 45 |
|---|---|---|---|
| mpnet (in use) | 0 of 4 | 1 of 4 (missing) | 1 of 4 (missing) |
| multilingual-e5-large | 3 of 4 (8th) | 2 of 4 (missing) | 3 of 4 (11th) |

- **e5 finds Art. 50 where mpnet cannot.** In the dense search alone the best Art. 50
  passage ranks 2nd, 7th, 2nd and 15th for the four questions, against about 260th to
  370th with mpnet (passage length, above). The BM25 search still ranks it between 9th
  and 186th.
- **Against the app today**, e5 alone gains six questions and loses three. Gained:
  aiact-113-002, aiact-113-005, gdpr-030-002, dora-005-003, tax-008-002 and csrd-003-001,
  the question naming "Article 3(4) of Directive 2013/34/EU" that the reranker misses
  with mpnet. Lost: csrd-19a-001, tax-008-001, cra-071-002.
- **Search depth.** With a reranker the hybrid search returns 30 candidates; the depth
  is how many dense and how many BM25 results it fuses into them. Without a reranker it
  is 45 (3 x 15 results); the first reranker code used 90 (3 x 30), and §4.1 was measured
  so. A deeper fusion favours passages both searches find, even far down, over a passage
  only one of them ranks high. With e5, the Art. 50 passage of the first chatbot question
  (2nd in the dense search, beyond the BM25 top 90) is 8th at depth 45 and 29th of the
  30 candidates at depth 90, where the reranker does not bring it back. mpnet needs the
  depth (88 at 90, 83 at 45); e5 hardly does (87 at 90, 86 at 45).
  `RERANKER_SEARCH_DEPTH` sets it, 90 by default.
- **Still missed** with e5 and the reranker at depth 45: aiact-113-003, csddd-037-001,
  csrd-19a-001, tax-008-001.
- **Cost**, on the development laptop (Intel i7-1195G7, 4 cores):
  - re-embedding the 5,851 passages: about 0.35 passages per second, about 4.5 hours of
    CPU (the seed of 2026-10-24 embedded about 1 passage per second with mpnet);
  - query embedding: median 126 ms (mpnet 29 ms);
  - memory of one API process after the 101 golden questions, private bytes: 2.8 GB with
    e5, 2.1 GB with mpnet, 0.6 GB more with the int8 reranker. The working set Windows
    reports is lower (e5 1.6 GB, mpnet 1.8 GB) while the laptop is short of memory: size
    a server by the private bytes. The e5 weights are 2.1 GB on disk (`model.onnx_data`).
- The fusion and the depth were chosen on the same 90 questions they are measured on:
  confirm them end to end (golden v2 with the LLM) before switching.

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
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | candidate, measured; code ready, off (§4.3); licence question open (§4.2) | Apache-2.0 on the model card; trained on a translation of MS MARCO (§4.2) | [model card](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1), ONNX exports (fp32, int8) in the same repository; not in FastEmbed 0.4.2 | 2026-10-27 model card | 88 / 90 retrieval only with mpnet, fused with the hybrid rank (§4.1); 86-87 / 90 with e5 (§2.1) |
| `BAAI/bge-reranker-v2-m3` | candidate; too slow to measure on the laptop CPU (§4.1) | Apache-2.0 | [model card](https://huggingface.co/BAAI/bge-reranker-v2-m3); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `Qwen/Qwen3-Reranker-0.6B` | candidate | Apache-2.0 | [model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B); not in FastEmbed 0.4.2 | 2026-10-26 notes | — |
| `jinaai/jina-reranker-v2-base-multilingual` | **excluded** (§7) | CC-BY-NC-4.0 | [model card](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual), FastEmbed 0.4.2 | 2026-10-26 notes, FastEmbed | — |

### 4.1 Measured: retrieval only, 2026-10-27

Collection `eu_regulations` (mpnet), the 90 golden v2 questions that expect an article,
expected article among the chunks the LLM receives (15; 20 with several frameworks).
The cross-encoder scores (question, passage) pairs, the passage being act title, article
and section title, then the chunk text, cut at 384 tokens.

| Configuration | Result | Against the app |
|---|---|---|
| App today: hybrid search, 15 results | 80 / 90 | — |
| Hybrid search, 30 candidates, first 15 | 82 / 90 | +5, −3 |
| 30 candidates in cross-encoder order | 85 / 90 | +8, −3 |
| 30 candidates, hybrid top 5 kept, then cross-encoder order | 85 / 90 | +7, −2 |
| **30 candidates, RRF of hybrid rank and cross-encoder rank (k=60)** | **88 / 90** | **+8, −0** |
| same, cross-encoder quantized to int8 (ONNX) | 88 / 90 | +8, −0 |

- **Fuse, do not replace.** The cross-encoder alone loses three date questions the
  hybrid search answers (AI Act Art. 113, CSDDD Art. 37 twice). Fusing the two ranks
  keeps them and still brings in what the cross-encoder ranks high among candidates
  16 to 30. Any k from 5 to 200 gives 88 / 90.
- **The candidates matter.** Same scores on the first N of the 30 candidates: 15 give
  82 / 90 (no change of membership), 20 give 83, 25 give 87, 30 give 88. The 30
  candidates come from a fusion of 90 dense and 90 BM25 results; from 45 and 45, as
  without a reranker, the same reranker scores 83 / 90 (§2.1, search depth).
- **Art. 50.** One of the four chatbot questions now gets AI Act Art. 50, at position 13
  of 15 (10 with int8); none did before.
- **Still missed**: aiact-113-003 (when the obligations for general-purpose AI models
  apply) and csrd-003-001, which names "Article 3(4) of Directive 2013/34/EU": an
  explicit article reference could be looked up instead of searched.
- **Time per question** on the development laptop (Intel i7-1195G7, 4 cores; 30 pairs):
  cross-encoder 4.2 s in PyTorch, 4.9 s in ONNX fp32, 2.7 s in ONNX int8; the hybrid
  search itself takes 0.12 s. The int8 model weighs 118 MB and runs on onnxruntime and
  tokenizers, which FastEmbed already installs: no PyTorch in the image. Its scores follow
  the fp32 ones (Spearman 0.97, median per question) and it scores the same once fused;
  alone it scores 83 / 90 instead of 85.
- **bge-reranker-v2-m3** (568M parameters) was too slow to measure on the same laptop:
  the 90-question run was estimated at about 750 CPU-minutes and stopped.
- The fusion was chosen on the same 90 questions it is measured on: confirm it end to
  end (golden v2 with the LLM) before switching it on.

The table was measured with scripts kept outside the repository. The same measure
now runs through the app's own code: `tests/validation/retrieval_eval.py` calls
`retrieve_node`, which reranks when the settings of §4.3 are set.

### 4.2 Licence question

The model card says Apache-2.0, and so does the card of mMARCO, the training data. mMARCO
is a machine translation of MS MARCO, whose terms say the MS MARCO datasets are "intended
for non-commercial research purposes only". Most open rerankers are trained on MS MARCO,
and whether those terms reach the users of a trained model is not settled. Check before
commercial use.

### 4.3 Switching it on

The code is in place and off by default: `src/nlp/embedding/reranker.py`, called by
`retrieve_node` in `src/agents/nodes.py`. CoVe's evidence search is not reranked.

1. **Files**: a directory with the ONNX export and `tokenizer.json`. The model
   repository ships `onnx/model_quint8_avx2.onnx` (int8, 119 MB, any AVX2 CPU) and
   `onnx/model.onnx` (fp32, 471 MB). The int8 model of §4.1 is an export of the same
   weights quantized with onnxruntime (`quantize_dynamic`, uint8 weights); measure the
   repository's own int8 file before using it.
2. **Settings**: `RERANKER_MODEL_DIR`, `RERANKER_ONNX_FILE` (path inside the directory),
   `RERANKER_CANDIDATES` (30) and `RERANKER_SEARCH_DEPTH` (90 with mpnet, 45 with
   multilingual-e5-large, §2.1). The API loads the model at startup and refuses to start
   if a file is missing; a reranking error at query time keeps the hybrid order.
3. **Docker image**: the runtime filesystem is read-only and offline
   (`HF_HUB_OFFLINE=1`), so bake the files into `/app/models` at build time, as for the
   dense model.
4. **Server**: about 0.6 GB more memory per API process (measured, §2.1; the int8 file
   itself is 118 MB) and 2-3 s of CPU per question on 4 cores. The app container is
   limited to 2 CPUs (`docker-compose.yml`), so expect about twice that; questions
   answered at the same time share the CPU.
5. **Measure**: `retrieval_eval` with these settings, then golden v2 end to end.

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
   (`indexer_kwargs_from_settings`); the background scheduler
   (`src/crawler/scheduler.py`) and the in-force refresh of `src/api/routers/data.py`
   take the API's indexer through `get_indexer()` in `src/api/app_state.py`.
2. **Vectors**: re-embed the corpus into a new collection, keeping ids, payloads and
   BM25 vectors, or reseed with `--recreate`. Try `--dry-run` first:

   ```bash
   python scripts/reembed_collection.py --source eu_regulations --target eu_regulations_e5 --model intfloat/multilingual-e5-large --dim 1024
   ```

   With e5 this takes hours of CPU (§2.1). Re-embed once and move the collection to the
   server as a Qdrant snapshot rather than re-embedding there; new acts later embed only
   their own passages.
3. **Prefixes**: a model trained with input prefixes needs an `EMBEDDING_PREFIXES` entry,
   otherwise it silently loses accuracy. e5 is listed.
4. **Docker image**: the Dockerfile bakes only mpnet into `/app/models` and the runtime
   filesystem is read-only. Bake the new model too, or the API cannot load it: e5 adds
   2.1 GB to the image.
5. **Memory**: each uvicorn worker loads its own copy of the models (the Dockerfile
   starts 2) and the app container is limited to 4 GB (`docker-compose.yml`). Measured
   per process (§2.1): 2.1 GB with mpnet, 2.8 GB with e5, 0.6 GB more with the reranker.
   With e5, run 1 worker or raise the limit (about 7 GB for 2 workers with the reranker).
6. **SNC**: `SNC_WEAK_EVIDENCE_DENSE_SCORE` (0.25) is a raw cosine threshold set on mpnet
   scores. e5 models give cosine scores in a narrow, high band (the best passage scored
   0.85 to 0.88 for the four chatbot questions), so with e5 the gate would never fire:
   recalibrate it before enabling SNC with another model. SNC is off by default.
7. **Measure**: retrieval only first, then golden v2 end to end; record both here.

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
| 2026-10-27 | Retrieval-only baseline read with the "bis" fix (80 / 90); multilingual MiniLM cross-encoder measured (§4.1), licence question (§4.2); multilingual-e5-large measured alone and with the reranker, search depth of the reranker's candidates (`RERANKER_SEARCH_DEPTH`), memory and re-embedding time (§2.1) |
