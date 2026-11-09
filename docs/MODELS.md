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
dense model, sparse vectors, reranker. Measured since: multilingual-e5-large, retrieval
only (§2.1) and end to end (§2.2), and a cross-encoder reranker (§4.1). The matching of
parent articles was made strict on 2026-10-27 (§2.2); 84 / 101 does not change. On
2026-11-03: the terms of the sparse vectors and the lookup of the articles a question
names, retrieval only (§3.1, §3.2) and end to end (§2.3); the retrieval-only measure also
counts the expected paragraph since then.

## 2. Dense embedding

Set by `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION`. Vectors live in a model-specific
space: a new model needs a collection re-embedded with it (§6).

| Model | Status | Dims | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|---|
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | **in use** (default) | 768 | Apache-2.0 | [model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2), FastEmbed 0.4.2 | 2026-10-26 code, FastEmbed | baseline, §1 |
| `intfloat/multilingual-e5-large` | candidate, measured (§2.1) | 1024 | MIT; fine-tuning data include MS MARCO (§4.2) | [model card](https://huggingface.co/intfloat/multilingual-e5-large), FastEmbed 0.4.2 | 2026-11-03 model card | 83 / 90 retrieval only; 86 / 90 with the reranker (§2.1); 89 / 90 with the sparse terms and named articles of 2026-11-03, no reranker (§3.1) |
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

### 2.2 Measured: golden v2 end to end, 2026-10-27

Golden v2 through the API with Claude Haiku 5.5, as in §1, on the local corpus of
2026-10-27: labels of the articles quoted by amending acts fixed, inserted articles cited
as in `src/agents/quoted_articles.py`, no reranker. Each run used a new organisation and an
emptied Redis, so no answer came from the cache. All rows are scored with the article
matching fixed on this date (below).

| Run | Questions passed | Recall | Answer checks | Verified citations | Mean time |
|---|---|---|---|---|---|
| mpnet, 2026-10-24 (§1) | 84 / 101 | 0.83 | 78.2 % | 99.6 % | 18.1 s |
| mpnet | 81 / 101 | 0.80 | 75.2 % | 99.2 % | 15.4 s |
| multilingual-e5-large | 85 / 101 | 0.84 | 78.2 % | 100 % | 16.1 s |
| multilingual-e5-large, response parser fixed (`d2562d0`) | **89 / 101** | 0.88 | 80.2 % | 99.4 % | 14.8 s |

- **Cost**: $0.25 to $0.27 per run of 101 questions.
- **Run-to-run variation.** The LLM does not answer twice the same way. Against
  2026-10-24, mpnet gained 1 question and lost 4 whose article it retrieves
  (aiact-026-003, csrd-19a-001, dora-005-002, inj-005); the corpus labels changed in
  between too. Read a difference of a few questions with care.
- **e5 against mpnet**, same corpus and day: +9 -5. The gains the retrieval-only measure
  predicts (§2.1) are there: csrd-003-001, dora-005-003, gdpr-030-002, tax-008-002 and
  inj-003, the chatbot question without an article number (Art. 50). Lost: cra-071-002 and
  tax-008-001 (retrieval, as in §2.1) and three answers lost by the response parser.
- **Response parser.** In the first e5 run 4 answers out of 101 were not JSON: three in
  prose, one JSON with the quotes of the quoted law left unescaped. `parse_json_response`
  returned them with no citations (one shown as raw JSON), so they failed although right:
  aiact-113-002, csrd-005-001, gdpr-030-001, nis2-023-004. Since `d2562d0` such JSON is
  repaired, and an answer in prose keeps the citations written in its text, checked by the
  verifier like the others. The rerun passed all four; one answer came in prose
  (tax-008-002) and kept 5 citations, 4 verified word for word. The mpnet runs had none.
- **Article matching.** Until this date the metric took any prefix for a parent article:
  "Art. 1" (the article of Regulation 2026/1744 that amends the AI Act, cited for questions
  on Art. 113) passed aiact-113-003 and aiact-113-005, and "Art. 19 bis(10)" passed
  csrd-19a-001. Two false passes in the mpnet run and two in the first e5 run, none on
  2026-10-24 and none in the rerun; the reports the runner wrote that day show 83 and 87.
- **Still failing** in the rerun (12). Retrieval, the expected article is not among the
  chunks the agents read: aiact-113-003, cra-071-002, csrd-19a-001, dora-028-001,
  nis2-021-003, tax-003-002, tax-008-001 (three of them abstain). The answer cites another
  article, another paragraph or the recitals: csddd-037-001, csrd-19a-002, csrd-29a-001,
  inj-005.
  gdpr-035-003 abstains rightly: paragraph 7 of Art. 35 is not retrieved.
- The gate of month 1 asks for at least 90 / 101: e5 with the fixed parser is one
  question short.

### 2.3 Measured: golden v2 end to end, 2026-11-03

Golden v2 through the API with Claude Haiku 5.5, as in §2.2, with `eu_regulations_e5` as
indexed on 2026-10-27 and the retrieval of §3.1 and §3.2 (sparse terms, named articles),
no reranker. Each run used a new organisation and an emptied Redis, on containers of its
own (Postgres, Redis, a copy of the local Qdrant volume).

| Run | Questions passed | Recall | Answer checks | Verified citations | Mean time |
|---|---|---|---|---|---|
| e5, 2026-10-27 (§2.2) | 89 / 101 | 0.88 | 80.2 % | 99.4 % | 14.8 s |
| e5, named articles without the opening rule (§3.2) | 95 / 101 | 0.94 | 83.2 % | 98.6 % | 19.5 s |
| same code, second run | 96 / 101 | 0.95 | 83.2 % | 99.48 % | 18.9 s |

- **Cost**: $0.27 per run.
- **Stable gains.** Both runs gain the same eight questions against 2026-10-27, the ones
  the retrieval-only measure predicts (§3.1): aiact-113-003, gdpr-035-003, nis2-021-003,
  csrd-19a-002, csddd-037-001, tax-003-002, tax-008-001, cra-071-002. The losses change
  from run to run: aiact-003-004 and csddd-037-002 in the first (both passed in the
  second), aiact-113-005 in the second.
- **Verified citations** are the mean, over the 96 answers with citations, of the share
  verified word for word, so one answer weighs a point. In the first run one answer came
  in prose and its citations, written as "[GDPR, Art. 30(1)]" without the quoted text,
  could not be verified (gdpr-030-001, 0 of 5; the answer passed): without it the run
  scores 99.65 %. The second run had no answer in prose; two quotes were cut or joined
  (nis2-003-001, csddd-037-001).
- **Still failing in both**: dora-028-001 (retrieval, §3.1); csrd-19a-001, csrd-29a-001
  and inj-005, which cite the recitals of Directive 2026/470 instead of Art. 19a(1) or
  29a(1). These two runs predate the opening rule of §3.2, which brings paragraph 1 of
  both articles to the agents.
- **Mean time** is not comparable with §2.2: the laptop ran the test suite during the
  first run, and the second ran on the API process of the first.

## 3. Sparse vectors

| Model | Status | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|
| Hashed term frequencies (MD5 into 30,000 buckets, `log(1 + tf)`) of the words of the text, runs of letters and digits since 2026-11-03, with Qdrant `Modifier.IDF`, BM25-style | **in use** | own code | `_text_to_sparse_vector` in `src/nlp/embedding/indexer.py` | 2026-11-03 code | §1, §3.1 |

No learned sparse model is in use or lined up; bge-m3 (§2) is the obvious one to try.
The re-embed script copies the sparse vectors unchanged, so changing them needs a
reseed (`python -m src.pipeline --action seed --recreate`). The terms of 2026-11-03 do
not need one: the questions get them at once, and passages indexed with the old split
are found as well (§3.1). A reseed or a re-index makes the passages consistent.

### 3.1 Measured: sparse terms and named articles, retrieval only, 2026-11-03

Until 2026-11-03 the sparse vectors split the text on spaces only, so punctuation stayed
on the words: a question's "artificiale?", "dell'autenticazione", "«garanzie" or
"(capo" matched no passage. Now the terms are runs of letters and digits
(`sparse_terms`). The second change looks up the articles a question names (§3.2).

Same measure as §1 and §2.1: the 90 golden v2 questions that expect an article, expected
article among the chunks the agents read, no reranker; since 2026-11-03 `retrieval_eval`
also counts the expected paragraph ("Art. 29a(1)" needs a chunk holding paragraph 1).
Collections `eu_regulations_e5` and `eu_regulations` of 2026-10-27, with their sparse
vectors as indexed (split on spaces) unless a row says otherwise.

| Configuration | e5: articles | e5: paragraphs | Art. 50, chatbot question | mpnet: articles |
|---|---|---|---|---|
| Before (split on spaces) | 83 / 90 | 80 / 90 | 8th | 80 / 90 |
| New terms | 87 / 90 | 84 / 90 | 9th | 84 / 90 |
| New terms, passages re-indexed with them | 87 / 90 | — | 8th | — |
| **New terms and named articles (the code since 2026-11-03)** | **89 / 90** | **87 / 90** | **9th** | 85 / 90 |
| same, passages re-indexed | 89 / 90 | 87 / 90 | 8th | — |

"Art. 50, chatbot question" is the position of AI Act Art. 50 for the first chatbot
question of `retrieval_eval` ("Il chatbot sul sito della nostra azienda deve dichiarare
di essere un'intelligenza artificiale? Da quando?"); mpnet does not retrieve it in any row.

- **The gain comes from the questions.** With the passages as indexed, the new terms give
  the same 87 as with re-indexed passages: no reseed is needed to deploy them.
- **e5's dense search alone scores 86 / 90** (Art. 50 2nd): the old BM25, whose question
  terms rarely matched, pulled the hybrid search down to 83.
- **Gained** with e5, against before: aiact-113-003, nis2-021-003, tax-003-002 and
  cra-071-002 (new terms); csrd-19a-001 and tax-008-001 (named articles, both name the
  act's number). At paragraph level also gdpr-035-003 (Art. 35(7), new terms) and
  csrd-29a-001 (the article's opening, §3.2); csrd-19a-002 lost its paragraph with the
  new terms (Art. 19a still comes, with later paragraphs). **Still missed**:
  dora-028-001, the article (its best chunk is 7th in the dense search and 65th in
  BM25); csrd-19a-002 and inj-005, the paragraph.
- **Variants tried and not kept**, all with re-indexed passages, e5, articles and Art. 50
  position: accents removed 87 (8th); Snowball stems (the passage's language for the
  passages, Italian and English for the question) 86 (3rd); stopwords removed 86 (5th);
  BM25 length normalisation (k1 1.2, b 0.75) 85 (9th); stems and normalisation 86 (11th);
  stopwords, stems and normalisation, close to Qdrant's own BM25, 85 (2nd).
- **Fusion, tried and not changed** (new terms, re-indexed passages, no named articles
  unless said): search depth 2, 3, 4 and 6 times the results 86, 87, 87, 88, with Art. 50
  5th, 8th, 15th and missing; RRF constant 20 and 100 both 87; dense weight 1.25 to 2
  gives 88, sparse weight 1.5 gives 87 with Art. 50 missing. With the named articles a
  dense weight of 1.5 gives e5 90 / 90 but drops mpnet from 85 to 70. The search keeps
  k = 60, depth 3 times the results and equal weights, as before: no parameter was chosen
  on these 90 questions.

### 3.2 Named articles

52 of the 101 golden v2 questions name an article ("ai sensi dell'art. 8 del
regolamento (UE) 2020/852", "Article 3(4) of Directive 2013/34/EU", "art. 35, paragrafo
7, del GDPR"). `src/nlp/embedding/article_refs.py` reads the references (number, Latin
suffix or letter, paragraph, act number turned into a CELEX); `hybrid_search` looks each
one up within the search filter (framework, tenant, superseded chunks) and fuses its
chunks as a third ranking, weighted as much as the two searches together.

- **Which references**: one that gives its act's number, or any when the search is
  restricted to frameworks (the agents pass the framework the question names: "art. 35
  del GDPR"). A bare "art. 5" in a search over every act is not looked up, nor is an act
  named only by its common name ("the Accounting Directive" in csrd-19a-002, a question
  whose words detect no framework).
- **Which chunks**: two per reference, ranked by the dense search within the article.
  The chunks holding a named paragraph come first; without a paragraph the article's
  opening (paragraph 1, else its first part), which states the article's rule, then the
  best other chunk. With the two best by score instead, e5 scores 85 / 90 at paragraph
  level (csrd-19a-001 and csrd-29a-001 get later paragraphs of the article).
- **Unknown articles** (the refusal questions on "art. 999 del GDPR", "Article 150 of the
  NIS2 Directive") find nothing and change nothing.
- **Cost**: one more filtered dense query to Qdrant per named article (at most three per
  question); the question is embedded once. On the development laptop the hybrid search
  of the 48 golden questions that name an article (and expect one) takes a median of 66 ms
  instead of 41 ms, besides the 126 ms of the e5 embedding (§2.1).

## 4. Reranker

| Model | Status | Licence (to re-check) | Source | Checked | Measured |
|---|---|---|---|---|---|
| none: the fused hybrid results go to the LLM as they are | **in use** | — | `hybrid_search` in `src/nlp/embedding/indexer.py` | 2026-10-26 code | baseline, §1 |
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | candidate, measured; code ready, off (§4.3); licence question open (§4.2) | Apache-2.0 on the model card; trained on a translation of MS MARCO (§4.2) | [model card](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1), ONNX exports (fp32, int8) in the same repository; not in FastEmbed 0.4.2 | 2026-10-27 model card | 88 / 90 retrieval only with mpnet, fused with the hybrid rank (§4.1); 86-87 / 90 with e5 (§2.1) |
| `BAAI/bge-reranker-v2-m3` | candidate; too slow to measure on the laptop CPU (§4.1); not needed for the gate of month 1 (§3.1) | Apache-2.0 on the model card; built on bge-m3, whose fine-tuning data include MS MARCO and mMARCO-ZH (§4.2) | [model card](https://huggingface.co/BAAI/bge-reranker-v2-m3), 568M parameters, [M3-Embedding paper](https://arxiv.org/abs/2402.03216) §3.1; not in FastEmbed 0.4.2 | 2026-11-03 model card, paper | — |
| `Alibaba-NLP/gte-multilingual-reranker-base` | candidate, not measured; not needed for the gate of month 1 (§3.1) | Apache-2.0 on the model card; fine-tuning data include MS MARCO (§4.2) | [model card](https://huggingface.co/Alibaba-NLP/gte-multilingual-reranker-base), 306M parameters, 612 MB of weights, custom architecture (`trust_remote_code`), no ONNX export in the repository, [mGTE paper](https://arxiv.org/abs/2407.19669) appendix B.2; not in FastEmbed 0.4.2 | 2026-11-03 model card, paper | — |
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

Checked on 2026-11-03: the question is not specific to this reranker. The two permissive
candidates of §4 were fine-tuned on MS MARCO too (bge-reranker-v2-m3 through bge-m3, with
mMARCO-ZH; gte-multilingual-reranker-base in the mGTE fine-tuning data), and so was the
dense model: the model card of multilingual-e5-large lists MS MARCO, 500k pairs, among its
fine-tuning data. A rule that excludes models trained on MS MARCO excludes e5 as well.
Since 2026-11-03 the retrieval passes the retrieval gate of month 1 without any reranker
(§3.1).

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
4. **Docker image**: the runtime filesystem is read-only, so the Dockerfile bakes the
   dense model into `/app/models` at build time: the one its build argument
   `EMBEDDING_MODEL` names, which `docker-compose.yml` takes from the same
   `EMBEDDING_MODEL` the API reads (mpnet by default). e5 adds 2.1 GB to the image.
5. **Memory**: each uvicorn worker loads its own copy of the models. Measured per process
   (§2.1): 2.1 GB with mpnet, 2.8 GB with e5, 0.6 GB more with the reranker.
   `WEB_CONCURRENCY` sets the workers (2 in the Dockerfile) and `APP_MEMORY_LIMIT` the
   app container's limit (4G by default, `docker-compose.yml`): with e5 set
   `WEB_CONCURRENCY=1`, or `APP_MEMORY_LIMIT=7G` for 2 workers with the reranker.
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
| 2026-10-27 | Retrieval-only baseline read with the "bis" fix (80 / 90); multilingual MiniLM cross-encoder measured (§4.1), licence question (§4.2); multilingual-e5-large measured alone and with the reranker, search depth of the reranker's candidates (`RERANKER_SEARCH_DEPTH`), memory and re-embedding time (§2.1); the Docker image bakes the configured dense model, workers and container memory are settings (§6) |
| 2026-10-27 | Golden v2 end to end: mpnet 81, e5 85, e5 with the response parser fixed 89 (§2.2); parent articles match only at a separator |
| 2026-11-03 | Sparse terms split on punctuation and lookup of the articles a question names, retrieval only: e5 83 → 89 / 90, mpnet 80 → 85 (§3.1, §3.2); the retrieval-only measure counts the expected paragraph; golden v2 end to end 95 and 96 / 101 with e5 (§2.3); licences and training data of two permissive rerankers, MS MARCO in e5's fine-tuning data too (§4, §4.2) |
