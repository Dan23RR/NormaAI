# Document check (prototype)

> Checks the legal references in a document a consultant already has (privacy notice, AI
> policy, contract clause, an assistant's answer) against the EU texts in force, and
> records the provisions it cites so a later run says which ones changed. Prototype of
> "controlla un documento", started on 2026-10-28.

## What it does

For every reference it finds ("art. 13 del GDPR", "Article 6(1)(f) GDPR", "art. 50, par. 5,
AI Act", "artt. 15-17", "considerando 47", "Allegato III", "paragrafo 9 dell'articolo 50"):

1. **Act.** The act written next to the reference, a name the document defines
   ("(di seguito «Regolamento»)"), or the act named earlier on the same line. Italian law
   (d.lgs., legge, Codice privacy) is listed with a Normattiva link but not checked: the
   corpus has no Italian texts yet.
2. **Provision.** The article, recital or annex must exist in the latest CELLAR consolidated
   text, and so must each cited paragraph. A provision missing today but present in an
   earlier version is reported as repealed or renumbered.
3. **Quotes.** Each quote («...», “...”, "...") goes through the production verifier
   (`src/agents/citation_verifier.py`, same normalisation and thresholds): in the cited
   provision, then elsewhere in the act, then in the earlier versions. A quote found only in
   an earlier version is **outdated**, and the report shows the provision then and now.
4. **Document date** (`--data`). The provision in force on that date is compared with
   today's. When paragraphs are cited, only those paragraphs count.

Every provision found in force goes into a lock file (`*.norma-lock.json`): CELEX, version,
article, text, SHA-256 of the normalised text. `--ricontrolla` compares a lock file with the
versions in force and reports what changed: "which documents to redo".

## Use

```bash
python scripts/check_document.py informativa.docx
python scripts/check_document.py policy_ia.pdf --data 2026-03-15
python scripts/check_document.py --ricontrolla informativa.norma-lock.json
```

Formats: `.docx` (tables included), `.pdf` (text layer only, no OCR), `.html`, `.txt`, `.md`.
The report (`*.controllo.html`) is in Italian. Texts are cached in `~/.cache/normaai/cellar`
(`--cache` to change it); the list of versions is asked again after a day.

## Design

| Module | Role |
|---|---|
| `src/document_check/extract.py` | Acts, provisions, quotes in the document text (no network) |
| `src/document_check/official.py` | Versions and articles from CELLAR: `EurLexClient.list_consolidated_celex`, `download_full_text_html`, the corpus chunker; on-disk cache |
| `src/document_check/check.py` | Statuses, lock file, re-check |
| `src/document_check/report.py` | HTML report, terminal summary |
| `scripts/check_document.py` | Command line |
| `tests/test_document_check.py` | Offline tests with a fake source |

## Known limits

- EUR-Lex consolidated texts are documentation; only the Official Journal is authentic.
- Unusual ways of citing can be missed; an article without an act ("si veda l'art. 22") is
  reported, not guessed, when the document names more than one EU act.
- Some consolidated versions have no XHTML in CELLAR (the AI Act of 2024-07-12 in Italian):
  the check falls back to the version before, down to the act as adopted.
- No Italian law, no case law, no authority guidance yet.
- Scanned PDFs (no text layer) give no text.

Measured on 2026-10-28 on a sample AI policy (12 provisions cited, 3 planted errors: an
outdated quote of AI Act art. 4, a paragraph that does not exist, an invented quote): all
three found, 7 provisions confirmed, 2 Italian references listed; 21 s on the first run,
7 s with the cache.
