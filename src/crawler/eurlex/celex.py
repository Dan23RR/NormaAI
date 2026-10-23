"""CELEX / ELI helpers shared by the EUR-Lex client, the chunker and the indexer.

Pure functions - no network, no heavy imports - so the chunker can use them
without pulling in SPARQLWrapper/httpx.

A CELEX number encodes ``sector(1) year(4) type(1) number(4)``, e.g.
``32022L2464`` (sector 3 = legislation, L = directive). CELLAR publishes the
*consolidated* text of an act under sector ``0`` with the consolidation date
appended: ``02022L2464-20260318`` is Directive 2022/2464 as consolidated on
2026-03-18. Both forms are accepted everywhere below.
"""

from __future__ import annotations

import re
from datetime import date

CELEX_RE = re.compile(
    r"^(?P<sector>[0-9])(?P<year>\d{4})(?P<type>[A-Z])(?P<number>\d{4})(?:-(?P<date>\d{8}))?$"
)
CONSOLIDATED_CELEX_RE = re.compile(r"^0\d{4}[A-Z]\d{4}-\d{8}$")

# CELEX document-type letter -> ELI resource type (the ``/eli/<type>/`` segment).
# Delegated / implementing acts share the plain letter in CELEX, so a caller
# that knows better passes ``eli_type`` explicitly (the act registry does).
_ELI_TYPE_BY_LETTER = {"L": "dir", "R": "reg", "D": "dec"}
ELI_TYPES = frozenset(
    {"dir", "reg", "dec", "dir_del", "dir_impl", "reg_del", "reg_impl", "dec_del", "dec_impl"}
)

EURLEX_LEGAL_CONTENT = "https://eur-lex.europa.eu/legal-content"


def parse_celex(celex: str | None) -> dict | None:
    """Split a CELEX number into its parts, or None when it is not a CELEX.

    Returns ``{"sector", "year", "type", "number", "date"}`` where ``date`` is
    the consolidation date as ``YYYY-MM-DD`` (None for an original act).
    Non-CELEX identifiers (Normattiva URNs, ``DOC_...`` upload ids) yield None.
    """
    if not celex:
        return None
    m = CELEX_RE.match(celex.strip())
    if not m:
        return None
    raw_date = m.group("date")
    iso_date = None
    if raw_date:
        try:
            iso_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])).isoformat()
        except ValueError:
            return None
    return {
        "sector": m.group("sector"),
        "year": m.group("year"),
        "type": m.group("type"),
        "number": m.group("number"),
        "date": iso_date,
    }


def is_consolidated_celex(celex: str | None) -> bool:
    """True for CELLAR consolidated ids (``0YYYYLNNNN-YYYYMMDD``)."""
    return bool(celex) and bool(CONSOLIDATED_CELEX_RE.match(celex.strip()))


def base_celex(celex: str) -> str:
    """Map a consolidated id back to the original act's CELEX.

    ``02022L2464-20260318`` -> ``32022L2464``; anything else is returned
    unchanged (an original CELEX, a URN, an upload id).
    """
    parts = parse_celex(celex)
    if parts is None or parts["sector"] != "0":
        return celex
    return f"3{parts['year']}{parts['type']}{parts['number']}"


def consolidated_prefix(celex: str) -> str | None:
    """The CELLAR id prefix shared by every consolidated version of an act.

    ``32022L2464`` -> ``02022L2464-``. None when ``celex`` is not a CELEX.
    """
    parts = parse_celex(base_celex(celex))
    if parts is None:
        return None
    return f"0{parts['year']}{parts['type']}{parts['number']}-"


def consolidated_as_of(celex: str | None) -> str | None:
    """ISO date of a consolidated id (``2026-03-18``), None for an original act."""
    parts = parse_celex(celex)
    return parts["date"] if parts else None


def celex_to_eli(celex: str | None, eli_type: str | None = None) -> str | None:
    """Build the ELI URI for an act when it can be derived, else None.

    ``32022L2464`` -> ``http://data.europa.eu/eli/dir/2022/2464/oj``
    ``02022L2464-20260318`` -> ``http://data.europa.eu/eli/dir/2022/2464/2026-03-18``
    (ELI point-in-time form for consolidated texts).

    ``eli_type`` overrides the type inferred from the CELEX letter: a
    delegated regulation is ``R`` in CELEX but ``reg_del`` in ELI, which
    CELEX alone cannot tell.
    """
    parts = parse_celex(celex)
    if parts is None:
        return None
    resource_type = eli_type if eli_type in ELI_TYPES else _ELI_TYPE_BY_LETTER.get(parts["type"])
    if resource_type is None:
        return None
    number = str(int(parts["number"]))
    tail = parts["date"] or "oj"
    return f"http://data.europa.eu/eli/{resource_type}/{parts['year']}/{number}/{tail}"


def eurlex_txt_url(celex: str | None, lang: str = "EN") -> str | None:
    """EUR-Lex human-readable TXT page for an act in the given language.

    Accepts original and consolidated ids; None for a non-CELEX identifier.
    """
    if parse_celex(celex) is None:
        return None
    lang_code = re.sub(r"[^A-Za-z]", "", lang or "EN").upper()[:2] or "EN"
    return f"{EURLEX_LEGAL_CONTENT}/{lang_code}/TXT/?uri=CELEX:{celex.strip()}"


def normalize_lang(lang: str | None, default: str = "EN") -> str:
    """Two-letter upper-case language code (``it`` -> ``IT``), defaulting safely."""
    code = re.sub(r"[^A-Za-z]", "", lang or "").upper()[:2]
    return code or default
