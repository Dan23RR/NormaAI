# Golden set v2 — Q&A with EUR-Lex-verified citations

`tests/validation/test_cases/golden_v2.jsonl` holds **101 questions** on EU law whose
expected answers are anchored to the **official text**: for every answerable record the
act (CELEX), the article, the paragraph and a passage **copied verbatim from EUR-Lex**
(via the Publications Office CELLAR endpoint) are stored next to the question. The set is
built for NormaAI's Q&A agent: it rewards answers that cite the right provision and state
the right date / threshold / fact, and it checks that the system abstains on questions
outside its corpus and does not follow injected instructions.

Built and verified on **2026-10-23**. Verification status: **101 fetched, 0 unverified**.

---

## 1. Record format

One JSON object per line:

```json
{
  "id": "aiact-050-001",
  "lang": "it",
  "framework": "AI_ACT",
  "question": "Un'azienda offre un chatbot ... deve informare gli utenti ...?",
  "kind": "factual",
  "expected": {
    "celex": "32024R1689",
    "article": "50",
    "paragraph": "1",
    "quote": "1. I fornitori garantiscono che i sistemi di IA destinati a interagire ...",
    "answer_must_contain": ["50", "interag"],
    "answer_must_not_contain": ["articolo 52", "art. 52"],
    "abstain": false
  },
  "source_url": "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689",
  "verified_on": "2026-10-23",
  "verification": "fetched",
  "notes": "..."
}
```

| Field | Values / meaning |
|---|---|
| `lang` | `it` or `en`; the quote is always in the language of the question |
| `framework` | `AI_ACT`, `CSRD`, `CSDDD`, `DORA`, `NIS2`, `GDPR`, `TAXONOMY`, `CRA`, plus `NONE` for out-of-corpus abstain records |
| `kind` | `factual`, `applicability`, `date`, `threshold`, `refuse` (expected abstain), `injection` |
| `expected.celex` / `article` / `paragraph` | provision the answer must cite; `paragraph` is `"1"`, `"2(a)"`, `"3(c)"` or `null` |
| `expected.quote` | passage copied verbatim from the official text (whitespace collapsed); `""` on abstain records |
| `expected.answer_must_contain` | case-insensitive substrings that a correct answer contains (short stems such as `interag`, `vietat` tolerate inflection) |
| `expected.answer_must_not_contain` | strings that mark a wrong answer (stale article numbers, wrong deadlines, injected tokens, prompt fragments) |
| `expected.abstain` | `true` when the right behaviour is to decline (refuse records and one injection record) |
| `expected.quote_celex` / `quote_article` | *optional*: where the quote was copied from when it differs from the cited act — a consolidated text (`02013L0034-20260318`) or the amending act (`32026R1744`, Article 1) |
| `verification` | `fetched` (quote copied from the official text) or `unverified` (never used in this version) |

Two extensions to the brief's schema, both documented here and validated by the pydantic
model: the optional `quote_celex`/`quote_article` pair and the `NONE` framework.

## 2. How the set was built

1. **Questions** were written by hand per framework and article, mixing Italian (60 %) and
   English (40 %), with the typical pitfalls encoded in `answer_must_not_contain`
   (e.g. "Art. 52" for AI Act transparency, "48 hours" for NIS2 early warning,
   the never-applied 1 000 employees / EUR 450 M CSDDD thresholds).
2. **Official texts** were downloaded in both languages from the CELLAR endpoint
   `http://publications.europa.eu/resource/celex/<CELEX>` (`Accept: application/xhtml+xml`,
   `Accept-Language: ita|eng`). EUR-Lex's own HTML endpoint answered HTTP 202 with an empty
   body from this machine (asynchronous rendering), CELLAR served the same documents
   directly. Acts used:

   | CELEX | Act | Used for |
   |---|---|---|
   | `32024R1689` | AI Act | Arts 3, 5, 6, 26, 50, 113 |
   | `32026R1744` | Reg. (EU) 2026/1744, Digital Omnibus on AI (OJ L 24.7.2026) | amended Art. 113 dates, new Art. 111(4) |
   | `32016R0679` | GDPR | Arts 6, 13, 17, 30, 33, 35 |
   | `32022L2555` | NIS2 | Arts 3, 21, 23 |
   | `32022R2554` | DORA | Arts 5, 17, 18, 19, 28 |
   | `02013L0034-20260318` | Accounting Directive 2013/34/EU **consolidated** (CSRD + Omnibus I, 18.3.2026) | Arts 3, 19a, 29a |
   | `02022L2464-20260318` | CSRD Directive 2022/2464 consolidated (stop-the-clock + Omnibus I) | Art. 5 application dates |
   | `02024L1760-20260318` | CSDDD consolidated (Omnibus I) | Arts 2, 37 |
   | `32020R0852` | Taxonomy Regulation | Arts 3, 8 |
   | `32024R2847` | Cyber Resilience Act | Arts 14, 71 |

3. **Extraction.** Each article is cut out of the XHTML (`<div class="eli-subdivision"
   id="art_N">`) and reduced to text lines (paragraphs and points, point markers merged),
   handling both the OJ markup of base acts and the consolidated-text markup
   (`▼M`/`►M` amendment markers, footnote superscripts removed).
4. **Quotes** were never retyped: a locator (paragraph number, line prefix or substring,
   optional number of consecutive lines) selects the passage and the build script copies
   it into `expected.quote`. For the AI Act dates changed by Regulation (EU) 2026/1744, no
   consolidated AI Act exists yet, so the quote is the new wording as it appears in the
   amending act (`quote_celex: "32026R1744"`, `quote_article: "1"`) while the citation
   target remains AI Act Art. 113 / Art. 111; `notes` cites both acts.
5. **Verification.** `verify_golden_v2.py` re-downloads every cited act and checks that the
   quote is a substring of the extracted article after normalisation (NFKC, ASCII quotes
   and dashes, amendment markers dropped, whitespace collapsed — the official files mix
   `'`/`’` and `«»`/`“”`). Result on 2026-10-23: `90 fetched records checked, 0 failed,
   11 skipped` (the 11 skipped are the abstain records, which have nothing to quote).

Re-run the verification (network, ~20 MB of downloads, cached afterwards):

```bash
python -m tests.validation.verify_golden_v2 --verbose
python -m tests.validation.verify_golden_v2 --offline --cache-dir /path/to/cache
```

Offline schema checks (ids unique, CELEX pattern, quote present on fetched records,
abstain consistency, language mix, article coverage, bridge to the runner):

```bash
python -m pytest tests/validation/test_golden_v2_schema.py -q -p no:cacheprovider -o addopts=""
```

## 3. Counts

| Framework | Records | of which refuse / injection |
|---|---|---|
| AI_ACT | 26 | 1 / 2 |
| GDPR | 17 | 1 / 1 |
| NIS2 | 13 | 1 / 1 |
| DORA | 14 | 1 / 0 |
| CSRD | 7 | 0 / 1 |
| CSDDD | 5 | 0 / 0 |
| TAXONOMY | 5 | 0 / 0 |
| CRA | 7 | 0 / 0 |
| NONE (out of corpus) | 7 | 6 / 1 |
| **Total** | **101** | **10 / 6** |

| Kind | Records |
|---|---|
| factual | 41 |
| applicability | 14 |
| date | 14 |
| threshold | 16 |
| refuse | 10 |
| injection | 6 |

| Language | Records |
|---|---|
| it | 60 (59.4 %) |
| en | 41 (40.6 %) |

| Verification | Records |
|---|---|
| fetched | 101 |
| unverified | 0 |

Article coverage: AI Act 3, 5, 6, 26, 50, 111, 113 · GDPR 6, 13, 17, 30, 33, 35 ·
NIS2 3, 21, 23 · DORA 5, 17, 18, 19, 28 · Accounting Directive 3, 19a, 29a · CSRD
Directive 5 · CSDDD 2, 37 · Taxonomy 3, 8 · CRA 14, 71.

## 4. Unverified records

None. Every quoted passage was fetched from the official text; the post-Omnibus CSRD and
CSDDD thresholds and dates could be verified on the consolidated texts of 18 March 2026,
so no `threshold` record had to be left `unverified`.

## 5. How the runner consumes it

- `tests/validation/schemas.py`: `GoldenV2Record` / `GoldenV2Expected` (pydantic) and
  `GoldenV2Record.to_test_case()`, which bridges a record to the legacy `TestCase`
  (task `qa`, the expected finding is the citation `Art. 50(1)`, `expected_answer` carries
  the answer checks). `Framework` gained `TAXONOMY` and `CRA`; `ViolationType` gained
  `reference`.
- `tests/validation/golden_v2.py`: `load_golden_v2()`, `load_golden_v2_test_cases()` and
  `check_answer()` (must-contain / must-not-contain / abstain scoring).
- `tests/validation/runner.py`: `--suite golden_v2` loads the JSONL (any `*.jsonl` under
  `test_cases/` is also picked up by `--suite all`); the report prints the answer-check
  pass rate.
- `tests/validation/metrics.py`: a case that expects no finding (abstain records, the
  existing false-positive probes) now scores recall 1.0 and precision 1.0 when nothing is
  flagged; answer checks are stored in `TestResult.answer_checks`.

```bash
python -m tests.validation.runner --suite golden_v2 --demo          # smoke
python -m tests.validation.runner --suite golden_v2 --api --verbose # real run
```

Scoring semantics: a non-abstain record passes when every `answer_must_contain` string is
present, no `answer_must_not_contain` string is present and the answer is not an abstention
(abstention = a known abstention phrase or zero citations). An abstain record passes when
the system abstained and said nothing forbidden. Citation precision/recall are computed on
`Art. N(p)` references with the existing fuzzy parent/child matching.

## 6. What the official texts say that the repository does not (yet)

Found while verifying; worth a review of the product copy and prompts.

1. **AI Act high-risk timeline moved.** Regulation (EU) 2026/1744 (Digital Omnibus on AI,
   OJ L 24.7.2026, in force 27.7.2026) rewrote Art. 113, third paragraph: Chapter III
   Sections 1-3 apply from **2 December 2027** for Annex III systems and from
   **2 August 2028** for Annex I systems (previously 2 August 2026 / 2 August 2027);
   Articles 102-110 apply from 27 July 2026; the new Art. 5 prohibitions (points (ba)/(bb))
   from 2 December 2026. New Art. 111(4): providers of generative systems already on the
   market before 2 August 2026 must meet Art. 50(2) by **2 December 2026**. The general
   application date (2 August 2026) is unchanged. `frontend/src/lib/mock-data.ts:117` still
   states "requisiti per sistemi ad alto rischio dal agosto 2026".
2. **CSDDD thresholds.** `frontend/src/lib/mock-data.ts:606` says the CSDDD applies above
   1 000 employees and EUR 450 M; the consolidated Art. 2(1)(a) (Omnibus I) says
   **more than 5 000 employees and net worldwide turnover above EUR 1 500 000 000**
   (third-country companies: EUR 1 500 000 000 net turnover in the Union, Art. 2(2)(a)).
   The transposition / application dates in README and landing (26 July 2028 / 26 July
   2029) match the official Art. 37(1).
3. **CSRD waves after Omnibus I.** Directive 2022/2464 Art. 5(2) as amended: wave 1
   (large PIEs > 500 employees) now covers financial years starting between 1 January 2024
   and 31 December 2026; the > EUR 450 M / > 1 000 employees regime applies to financial
   years starting on or after **1 January 2027** (with a Member State option to exempt
   smaller undertakings for FY 2025-2026). Art. 19a(1)/29a(1) of the Accounting Directive
   carry the 450 M / 1 000 thresholds.
4. **"Omnibus I (December 2025)" in `prompts/qa_bot.txt`.** The Omnibus I directive is
   Directive (EU) 2026/470 of 24 February 2026 (OJ 26.2.2026, in force 18.3.2026);
   "December 2025" at most describes the political agreement.
5. **DORA 4-hour notification.** The mock Q&A answer in `frontend/src/lib/mock-data.ts`
   cites a 4-hour deadline; DORA Art. 19(4) only lists initial notification, intermediate
   and final report and defers the time limits to the Art. 20 technical standards.
6. **Typos in the official Italian texts, reproduced verbatim in the quotes:** AI Act
   Art. 5(1)(h)(i) "specifichevittime" and DORA Art. 19(1) "gli gravi incidenti TIC".

## 7. Maintenance

- Add records by writing the question and a locator for the passage, then rebuild and run
  `verify_golden_v2.py`; never paste a quote by hand.
- When an act is amended, re-run the verifier: a failing record means the quoted passage
  changed and the record (and probably the product copy) needs a review.
- Keep `unverified` records at or below 15 % of the set (enforced by the schema test).
