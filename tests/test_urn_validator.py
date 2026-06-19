"""Unit tests for URNValidator - Italian legislative URN validation/extraction.

Citations are the core of NormaAI's "verified sources" promise, so this pins the
validator's format rules, round-trip parsing, normalization and (Italian)
citation extraction. TIER 1 (pure functions; no DB/network).

NOTE: ``from_citation``/``extract_and_validate`` are utility helpers, not yet
wired into the production CoVe path. A known limitation is documented in
``test_from_citation_eu_regulation_not_yet_extracted`` (EU citation patterns do
not capture an act ``tipo``, so EU references are currently not extracted).
"""

from __future__ import annotations

import pytest

from src.crawler.normattiva.urn_validator import URNComponents, URNValidator

VALID_URNS = [
    "urn:nir:stato:legge:2024;123",
    "urn:nir:stato:legge:2024-01-15;3",
    "urn:nir:unione.europea:regolamento:2024;1689",
    "urn:nir:stato:decreto.legislativo:2023;138",
    "urn:nir:stato:legge:2024;123,5",  # with trailing article reference
]

INVALID_URNS = [
    "",
    "not-a-urn",
    "legge 123/2024",  # plain citation, not a URN
    "urn:nir:stato:legge:2024",  # missing ;numero
    "urn:nir:regione:legge:2024;1",  # authority not stato/unione.europea
    "urn:nir:stato:legge:24;123",  # year is not 4 digits
]


@pytest.mark.parametrize("urn", VALID_URNS)
def test_validate_format_accepts_valid(urn):
    assert URNValidator.validate_format(urn) is True


@pytest.mark.parametrize("urn", INVALID_URNS)
def test_validate_format_rejects_invalid(urn):
    assert URNValidator.validate_format(urn) is False


def test_validate_format_tolerates_surrounding_whitespace():
    assert URNValidator.validate_format("  urn:nir:stato:legge:2024;123  ") is True


def test_parse_round_trips_components():
    comp = URNValidator.parse("urn:nir:stato:legge:2024-01-15;3")
    assert isinstance(comp, URNComponents)
    assert comp.autorita == "stato"
    assert comp.tipo == "legge"
    assert comp.data == "2024-01-15"
    assert comp.numero == "3"


def test_parse_extracts_article_when_present():
    comp = URNValidator.parse("urn:nir:stato:legge:2024;123,5")
    assert comp is not None
    assert comp.articolo == "5"


def test_parse_returns_none_for_invalid():
    assert URNValidator.parse("garbage") is None


def test_normalize_lowercases_and_expands_abbreviations():
    out = URNValidator.normalize("  D.Lgs. 138 ")
    assert out == out.lower()
    assert "decreto.legislativo:" in out  # "d.lgs." expanded


def test_from_citation_extracts_italian_law_del_form():
    urns = URNValidator.from_citation("ai sensi della legge n. 123 del 2024")
    assert urns == ["urn:nir:stato:legge:2024;123"]


def test_from_citation_extracts_italian_law_slash_form():
    urns = URNValidator.from_citation("legge n. 123/2024")
    assert urns == ["urn:nir:stato:legge:2024;123"]


def test_from_citation_empty_on_plain_text():
    assert URNValidator.from_citation("questo testo non contiene citazioni") == []


def test_from_citation_eu_regulation_not_yet_extracted():
    # KNOWN LIMITATION: the EU citation regexes capture anno/numero but no `tipo`,
    # so _build_urn_from_match (which requires tipo) drops them. Pinned so the day
    # someone fixes EU extraction this test flips and is updated deliberately.
    assert URNValidator.from_citation("come da Regolamento (UE) 2024/1689") == []


def test_extract_and_validate_separates_valid_and_invalid():
    result = URNValidator.extract_and_validate("legge n. 123 del 2024")
    assert set(result.keys()) == {"valid", "invalid"}
    assert "urn:nir:stato:legge:2024;123" in result["valid"]
    assert result["invalid"] == []


def test_build_url_for_valid_urn():
    url = URNValidator.build_url("urn:nir:stato:legge:2024;123")
    assert url == "https://www.normattiva.it/atto/stato/legge/2024/123"


def test_build_url_strips_full_date_to_year():
    url = URNValidator.build_url("urn:nir:stato:legge:2024-01-15;3")
    assert url == "https://www.normattiva.it/atto/stato/legge/2024/3"


def test_build_url_empty_for_invalid():
    assert URNValidator.build_url("garbage") == ""


def test_get_citation_format_human_readable():
    assert URNValidator.get_citation_format("urn:nir:stato:legge:2024;123") == (
        "Legge n. 123 del 2024"
    )


def test_get_citation_format_none_for_invalid():
    assert URNValidator.get_citation_format("garbage") is None
