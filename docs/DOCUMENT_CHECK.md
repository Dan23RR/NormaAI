# Document check (prototype)

> Checks the legal references in a document a consultant already has (privacy notice, AI
> policy, contract clause, an assistant's answer) against the texts in force, EU law on
> CELLAR and Italian law on Normattiva, and records the provisions it cites so a later run
> says which ones changed. Prototype of "controlla un documento", started on 2026-10-28;
> Italian law since 2026-11-11.

## What it does

For every reference it finds ("art. 13 del GDPR", "Article 6(1)(f) GDPR", "art. 50, par. 5,
AI Act", "artt. 15-17", "considerando 47", "Allegato III", "paragrafo 9 dell'articolo 50"):

1. **Act.** The act written next to the reference, a name the document defines
   ("(di seguito «Regolamento»)"), or the act named earlier on the same line. Italian acts
   are resolved to their URN:NIR (see "Italian law" below); an act that cannot be resolved
   without guessing is reported, not checked.
2. **Provision.** The article, recital or annex must exist in the latest CELLAR consolidated
   text (for Italian law: the article in force today on Normattiva), and so must each cited
   paragraph or comma. A provision missing today but present in an earlier version is
   reported as repealed or renumbered.
3. **Quotes.** Each quote («...», “...”, "...") goes through the production verifier
   (`src/agents/citation_verifier.py`, same normalisation and thresholds): in the cited
   provision, then elsewhere in the act, then in the earlier versions. A quote found only in
   an earlier version is **outdated**, and the report shows the provision then and now.
4. **Document date** (`--data`). The provision in force on that date is compared with
   today's. When paragraphs are cited, only those paragraphs count.

Every provision found in force goes into a lock file (`*.norma-lock.json`): source
(`fonte`: `eurlex` or `normattiva`), act (CELEX or URN:NIR), version, article, text, SHA-256
of the normalised text. For an Italian article `versione` and `consolidato_al` are the day
the text in force was read. `--ricontrolla` compares a lock file with the texts in force and
reports what changed: "which documents to redo". A lock file written before Italian law was
read has no `fonte`: its entries are EU provisions.

## Outcomes

| Outcome (report label) | Group | Meaning |
|---|---|---|
| Citazione superata | da correggere | The quote matches only an earlier wording; the card shows before and after |
| Cambiato dopo la data del documento | da correggere | The provision in force on `--data` differs from today's (in the cited paragraphs or commi, when cited) |
| Non esiste nel testo vigente | da correggere | Article, paragraph or comma not in the text in force: never existed, repealed (the card shows the last wording), or not yet in force |
| Citazione diversa dal testo ufficiale | da correggere | The quote almost matches but words differ (a number, a negation, a short word); the card lists the differing words |
| Citazione non trovata | da correggere | The quote is in no wording of the cited provision |
| Citazione in un altro articolo | da controllare | EU law: the quote is in another article of the act |
| Testo ufficiale non raggiungibile | da controllare | CELLAR or Normattiva did not answer and nothing is cached |
| Versione più recente non leggibile | da controllare | EU law: a later consolidated text exists but could not be read; the check used an older one |
| Estremi dell'atto da controllare | da controllare | Italian law: Normattiva has no act with this type, year and number, or its date differs from the document's |
| Articolo letto solo in parte | da controllare | Italian law: the API gives only the first 100 commi of a very long article |
| Modifica pubblicata, non ancora in vigore | da controllare | Italian law: the wording in force already has its last day set (a repeal or an amendment published) |
| Sentenza della Corte costituzionale in nota | da controllare | Italian law: Normattiva reports a ruling of unconstitutionality under the article; the text is unchanged |
| Atto non indicato | da controllare | A reference whose act cannot be told |
| Riferimento valido, Citazione verificata | a posto | The provision exists; the quote is in the text in force, word for word |
| Atto che il controllo non legge | fuori copertura | Regional laws, ministerial decrees, d.P.C.M., circulars, annexes of Italian acts |

## Italian law (Normattiva)

Italian acts are read on the Normattiva open data API
(`https://api.normattiva.it/t/normattiva.api`, specification
`https://dati.normattiva.it/assets/come_fare_per/API_Normattiva_OpenData.pdf`), one article
per request, as in force on a day (`POST .../atto/dettaglio-atto-urn` with
`urn:nir:...~art2ter!vig=YYYY-MM-DD`, or `@originale` for the text as first published). No key
is needed; the data are licensed CC BY 4.0. The whole act is never downloaded.

- **Citation forms.** "d.lgs. 196/2003", "D.Lgs. n. 196 del 2003", "decreto legislativo
  30 giugno 2003, n. 196", "legge 241/90", "l. 300/1970", "decreto-legge", "D.L.", "D.P.R.",
  "r.d.", "legge costituzionale", "Cost."; the codes and common names: Codice civile (c.c.,
  cod. civ.), Codice penale (c.p.), c.p.c., c.p.p., Codice privacy, Statuto dei lavoratori,
  Codice del consumo, CAD, TUIR, legge fallimentare, and acts cited by number (d.lgs.
  231/2001, d.lgs. 81/2008, l. 241/1990). Commi: "comma 1-bis", "secondo comma", "commi primo
  e secondo". A bare "decreto 81/2008", or an article that could belong to two acts, is not
  guessed.
- **Checks.** The article and each cited comma must be in the text in force today. A quote
  is verified word for word with the production verifier on the article in force; failing
  that, on the wording in force on the document's date, the earlier wordings (up to five)
  and the original text: found there, it is "Citazione superata". With `--data`, a wording
  that started after that date is compared with the one in force then.
- **Cache.** One JSON file per article under `<cache>/normattiva`. A wording still in force
  is asked again after a day, a wording that has ended after a month, a missing article or
  act after a day. When the API does not answer, the last answer is used and the report
  says from which day it is.
- **Client.** One request at a time, 0.4 s between requests, 20 s timeout, two retries on a
  network error, HTTP 429 or 5xx. Only the API's own answers for a missing act (HTTP 400
  code 1003, 404 "atto non trovato") or article (404) mean "does not exist"; any other error
  is "Testo ufficiale non raggiungibile".
- **Not official.** Normattiva's texts are not official: the Gazzetta Ufficiale prevails in
  case of discrepancy. The report says so and credits Normattiva (CC BY 4.0). Editorial marks
  and update notes are removed from the text; rulings of the Constitutional Court that sit
  only in the notes are flagged.

## Use

```bash
python scripts/check_document.py informativa.docx
python scripts/check_document.py policy_ia.pdf --data 2026-03-15
python scripts/check_document.py --ricontrolla informativa.norma-lock.json
```

Formats: `.docx` (tables included), `.pdf` (text layer only, no OCR), `.html`, `.txt`, `.md`.
The report (`*.controllo.html`) is in Italian. Texts are cached in `$NORMAAI_TEXT_CACHE`
when set, otherwise in `~/.cache/normaai/cellar`, or under the system temporary folder when the
home cache cannot be created (`--cache` to change it); Italian articles go in its `normattiva`
folder. The list of EU versions is asked again after a day.

From Python (the API and the scheduled re-check use the same objects):

```python
from src.document_check.sources import default_source   # EU (CELLAR) + Italian (Normattiva)
from src.document_check.check import check_text, build_lock, recheck
check = check_text(text, default_source(), document="nota.docx", document_date="2026-03-15")
changes = recheck(build_lock(check), default_source())
```

## Design

| Module | Role |
|---|---|
| `src/document_check/extract.py` | Acts, provisions, quotes in the document text (no network) |
| `src/document_check/official.py` | Versions and articles from CELLAR: `EurLexClient.list_consolidated_celex`, `download_full_text_html`, the corpus chunker; on-disk cache |
| `src/document_check/normattiva.py` | Italian articles from the Normattiva open data API: client, HTML parsing, on-disk cache |
| `src/document_check/sources.py` | `default_source()`: EU and Italian law behind one object; `default_cache_dir()` |
| `src/document_check/check.py` | Statuses, lock file, re-check |
| `src/document_check/report.py` | HTML report, terminal summary |
| `scripts/check_document.py` | Command line |
| `tests/test_document_check.py` | Offline tests with a fake source |
| `tests/test_document_check_normattiva.py` | Offline tests on Normattiva answers recorded on 2026-11-11 (`tests/fixtures/normattiva/`) |

## Known limits

- EUR-Lex consolidated texts are documentation; only the Official Journal is authentic.
- Unusual ways of citing can be missed; an article without an act ("si veda l'art. 22") is
  reported, not guessed, when the document names more than one EU act.
- Some consolidated versions have no XHTML in CELLAR (the AI Act of 2024-07-12 in Italian):
  the check falls back to the version before, down to the act as adopted.
- Italian law: only the cited articles of state acts on Normattiva are read; regional
  laws, ministerial decrees, circulars and annexes are listed, not checked. A quote of an
  Italian act is looked for in the cited article only. Of a very long article (art. 1 of a
  budget law) the API gives the first 100 commi. Normattiva does not apply rulings of the
  Constitutional Court to the text.
- No case law, no authority guidance yet.
- Scanned PDFs (no text layer) give no text.

Measured on 2026-10-28 on a sample AI policy (12 provisions cited, 3 planted errors: an
outdated quote of AI Act art. 4, a paragraph that does not exist, an invented quote): all
three found, 7 provisions confirmed, 2 Italian references listed; 21 s on the first run,
7 s with the cache.

Measured on 2026-11-11 (live, empty cache): the sample note of 2026-03-15 with seven EU
provisions and two Italian ones (art. 24 d.lgs. 138/2024, art. 13 l. 132/2025, both found in
force) took 79 s, 64 s with the cache (almost all of it reading the EU texts); a note of six
Italian references with four planted errors (a number changed in a quote, an article that does
not exist, a repealed article, a quote of a wording replaced after the note's date) and a
provision amended after that date: all found, 13 s on the first run, 4 s with the cache.
