# Italian legislative URNs - Module Index

## Overview

This package holds `URNValidator`: validation, normalization, parsing and extraction of Italian and EU legislative URNs (`urn:nir:...`) from free text. The document check uses it (`src/document_check/extract.py`).

It used to hold an async client for the Normattiva Open Data API as well. Its endpoints (`www.normattiva.it/opendata/api/...`) answered HTTP 409 with a page of the Poligrafico's protection systems (2026-11-11), so the client fed no Italian text into the Q&A corpus and returned an error for every URN that CoVe asked it about; it was removed in November 2026 (git keeps it in history). The document check reads Italian law through the newer open data API in `src/document_check/normattiva.py`.

## Module Structure

```
src/crawler/normattiva/
├── __init__.py              # exports URNValidator, URNComponents
├── urn_validator.py         # URN handling & extraction
└── INDEX.md                 # This file
```

## URNValidator (urn_validator.py)

Static URN validation, parsing, and extraction utilities. Pure functions: no network.

**Main Methods:**
- `validate_format(urn: str) -> bool` - Check URN format
- `normalize(urn: str) -> str` - Normalize URN string
- `parse(urn: str) -> URNComponents` - Extract components
- `from_citation(text: str) -> list[str]` - Extract URNs from text
- `build_url(urn: str) -> str` - Build Normattiva web URL
- `get_citation_format(urn: str) -> str` - Generate readable citation
- `extract_and_validate(text: str) -> dict` - Extract & validate URNs

**URNComponents** - Parsed URN parts: autorita, tipo, data, numero, articolo.

## Supported Legislative Types

### Italian (autorita=stato)
- legge (law)
- decreto.legislativo (legislative decree)
- decreto.legge (decree-law)
- decreto.presidente.repubblica (presidential decree)
- decreto.presidente.consiglio.ministri (prime minister decree)
- regolamento (regulation)
- direttiva (directive)

### EU (autorita=unione.europea)
- regolamento.ue (EU regulation)
- direttiva.ue (EU directive)

## Citation Pattern Support

| Pattern | Example | Extracts |
|---------|---------|----------|
| Standard law | legge n. 123 del 2024 | urn:nir:stato:legge:2024;123 |
| Short law | l. 123/2024 | urn:nir:stato:legge:2024;123 |
| Decree | d.lgs. 138/2023 | urn:nir:stato:decreto.legislativo:2023;138 |
| Decree-law | D.L. 15 gennaio 2024, n. 3 | urn:nir:stato:decreto.legge:2024-01-15;3 |
| With article | art. 5, legge n. 123/2024 | urn:nir:stato:legge:2024;123 |
| EU regulation | Regolamento (UE) 2024/1689 | urn:nir:unione.europea:regolamento:2024;1689 |
| EU directive | Direttiva (UE) 2024/1689 | urn:nir:unione.europea:direttiva:2024;1689 |

## Testing

`tests/test_urn_validator.py`; `urn_validator.py` is also in the blocking mypy gate of CI.
