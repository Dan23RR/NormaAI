# Normattiva Open Data Crawler - Module Index

## Overview

This package provides a production-grade async Python client for the Italian Normattiva Open Data API, with comprehensive URN validation, citation extraction, and data parsing capabilities.

## Module Structure

```
src/crawler/normattiva/
├── __init__.py              # Package exports (clean public API)
├── client.py                # Main API client (599 lines)
├── urn_validator.py         # URN handling & extraction (397 lines)
└── INDEX.md                 # This file
```

## Core Classes

### NormattivaOpenDataClient (client.py)

Async HTTP client for the Normattiva Open Data API.

**Main Methods:**
- `async search(query, tipo_atto, anno, page, limit)` - Search acts
- `async get_atto(tipo, anno, numero, articolo)` - Get full text
- `async get_multivigenza(urn, data_vigenza)` - Version history
- `async download_bulk_xml(tipo_atto, anno_from, anno_to)` - Bulk downloads
- `async validate_urn(urn)` - Validate URN existence
- `async close()` - Close connection

**Configuration:**
```python
client = NormattivaOpenDataClient(
    base_url="https://www.normattiva.it/opendata",
    rate_limit_delay=1.0,    # 1 second between requests
    timeout=30.0,             # 30 second timeout
    max_retries=3             # 3 retry attempts
)
```

### URNValidator (urn_validator.py)

Static URN validation, parsing, and extraction utilities.

**Main Methods:**
- `validate_format(urn: str) -> bool` - Check URN format
- `normalize(urn: str) -> str` - Normalize URN string
- `parse(urn: str) -> URNComponents` - Extract components
- `from_citation(text: str) -> list[str]` - Extract URNs from text
- `build_url(urn: str) -> str` - Build Normattiva web URL
- `get_citation_format(urn: str) -> str` - Generate readable citation
- `extract_and_validate(text: str) -> dict` - Extract & validate URNs
- `async verify_remote(urn, client)` - Verify against API

## Data Models

### From client.py

1. **Articolo** - Single article in legislative text
   - numero, rubrica, testo, commi

2. **NormativeActSummary** - Search result summary
   - urn, tipo, anno, numero, titolo, data_pubblicazione, in_vigore

3. **SearchResult** - Paginated search response
   - total, page, results

4. **NormativeText** - Full legislative text
   - urn, tipo, anno, numero, titolo, testo_html, testo_plain, articoli, data_vigenza, url

5. **Versione** - Single version in history
   - data_inizio, data_fine, testo, modifiche

6. **MultivigenzaResult** - Version history wrapper
   - urn, versioni

7. **NormativeActXML** - Parsed XML document
   - urn, xml_content, parsed_articles

8. **URNValidationResult** - Validation response
   - urn, exists, is_in_force, tipo, anno, numero, titolo, url

### From urn_validator.py

1. **URNComponents** - Parsed URN parts
   - autorita, tipo, data, numero, articolo

## Usage Patterns

### Pattern 1: Search and Retrieve

```python
async with NormattivaOpenDataClient() as client:
    # Search
    results = await client.search(query="energy", anno=2024)
    
    # Get first result's full text
    if results.results:
        act = results.results[0]
        text = await client.get_atto(
            tipo=act.tipo,
            anno=act.anno,
            numero=act.numero
        )
```

### Pattern 2: URN Extraction and Validation

```python
# Extract URNs from text
text = "Law n. 123 del 2024 modifies decree 138/2023"
urns = URNValidator.from_citation(text)

# Build URLs
for urn in urns:
    url = URNValidator.build_url(urn)
    print(f"Read: {url}")

# Validate with API
valid = await URNValidator.verify_remote(urn, client)
```

### Pattern 3: Concurrent Operations

```python
async with NormattivaOpenDataClient() as client:
    tasks = [
        client.search(query=q)
        for q in ["tax", "health", "environment"]
    ]
    results = await asyncio.gather(*tasks)
```

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

## Error Handling

All methods implement comprehensive error handling:

- HTTP errors are caught and logged
- Returns empty/None results on failure
- Never throws exceptions to caller
- All errors logged via Python logging module

Enable logging:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Performance Characteristics

- **Rate limiting:** 1 second default between requests
- **Retry logic:** 3 attempts with exponential backoff (1s, 2s, 4s)
- **Timeout:** 30 seconds default per request
- **Async:** Supports concurrent operations via asyncio.gather()
- **Memory:** Efficient XML parsing with streaming

## Dependencies

- Python >= 3.10
- pydantic >= 2.0
- httpx >= 0.25.0
- lxml (for XML parsing)

## API Endpoints

All requests go to: https://www.normattiva.it/opendata/

Implemented endpoints:
- GET /api/ricerca - Search
- GET /api/atto/{tipo}/{anno}/{numero} - Full text
- GET /api/multivigenza/{urn} - Version history
- GET /api/bulk - Bulk XML download
- GET /api/validate - URN validation

## Testing

Manual validation checks:
```bash
python3 -m py_compile client.py urn_validator.py __init__.py
```

See IMPLEMENTATION_SUMMARY.txt for test recommendations.

## Documentation

- NORMATTIVA_README.md - Complete usage guide
- DELIVERY_SUMMARY.txt - Implementation overview
- IMPLEMENTATION_SUMMARY.txt - Technical details

## License

Part of NormaAI - Italian/EU Regulatory Intelligence Platform
