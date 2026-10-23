"""Tests for the pure CELEX / ELI helpers (src/crawler/eurlex/celex.py).

No network: these functions only parse identifiers and build URIs.
"""

import pytest

from src.crawler.eurlex import celex as cx


class TestParseCelex:
    def test_original_act(self):
        parts = cx.parse_celex("32022L2464")
        assert parts == {
            "sector": "3",
            "year": "2022",
            "type": "L",
            "number": "2464",
            "date": None,
        }

    def test_consolidated_id_carries_date(self):
        parts = cx.parse_celex("02022L2464-20260318")
        assert parts["sector"] == "0"
        assert parts["date"] == "2026-03-18"

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            None,
            "urn:nir:stato:decreto.legislativo:2003-06-30;196",
            "DOC_1A2B3C4D",
            "3202",
            "02022L2464-20261345",
        ],
    )
    def test_non_celex_returns_none(self, bad):
        assert cx.parse_celex(bad) is None

    def test_surrounding_whitespace_tolerated(self):
        assert cx.parse_celex(" 32024R1689 ")["number"] == "1689"


class TestBaseAndConsolidated:
    def test_base_celex_of_consolidated(self):
        assert cx.base_celex("02022L2464-20260318") == "32022L2464"

    def test_base_celex_of_original_unchanged(self):
        assert cx.base_celex("32022L2464") == "32022L2464"

    def test_base_celex_passthrough_for_non_celex(self):
        assert cx.base_celex("DOC_ABCD1234") == "DOC_ABCD1234"

    def test_is_consolidated(self):
        assert cx.is_consolidated_celex("02022L2464-20260318")
        assert not cx.is_consolidated_celex("32022L2464")
        assert not cx.is_consolidated_celex(None)

    def test_consolidated_prefix(self):
        assert cx.consolidated_prefix("32022L2464") == "02022L2464-"
        # Also derivable from a consolidated id (same base).
        assert cx.consolidated_prefix("02022L2464-20250417") == "02022L2464-"
        assert cx.consolidated_prefix("not-a-celex") is None

    def test_consolidated_as_of(self):
        assert cx.consolidated_as_of("02022L2464-20260318") == "2026-03-18"
        assert cx.consolidated_as_of("32022L2464") is None
        assert cx.consolidated_as_of("urn:x") is None


class TestEli:
    def test_directive(self):
        assert cx.celex_to_eli("32022L2464") == "http://data.europa.eu/eli/dir/2022/2464/oj"

    def test_regulation_strips_leading_zeros(self):
        assert cx.celex_to_eli("32020R0852") == "http://data.europa.eu/eli/reg/2020/852/oj"

    def test_decision(self):
        assert cx.celex_to_eli("32021D0914") == "http://data.europa.eu/eli/dec/2021/914/oj"

    def test_explicit_eli_type_for_delegated_regulation(self):
        assert (
            cx.celex_to_eli("32023R2772", eli_type="reg_del")
            == "http://data.europa.eu/eli/reg_del/2023/2772/oj"
        )

    def test_unknown_eli_type_falls_back_to_letter(self):
        assert cx.celex_to_eli("32023R2772", eli_type="bogus").startswith(
            "http://data.europa.eu/eli/reg/2023/2772/"
        )

    def test_consolidated_point_in_time(self):
        assert (
            cx.celex_to_eli("02022L2464-20260318")
            == "http://data.europa.eu/eli/dir/2022/2464/2026-03-18"
        )

    def test_non_celex_is_none(self):
        assert cx.celex_to_eli("DOC_ABCD1234") is None
        assert cx.celex_to_eli(None) is None

    def test_unknown_type_letter_is_none(self):
        assert cx.celex_to_eli("32020X0001") is None


class TestUrlAndLang:
    def test_txt_url_default_language(self):
        assert (
            cx.eurlex_txt_url("32022L2464")
            == "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464"
        )

    def test_txt_url_italian_consolidated(self):
        url = cx.eurlex_txt_url("02022L2464-20260318", lang="it")
        assert url == (
            "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02022L2464-20260318"
        )

    def test_txt_url_none_for_non_celex(self):
        assert cx.eurlex_txt_url("urn:nir:stato:legge:2020;1") is None

    @pytest.mark.parametrize(
        "raw, expected",
        [("it", "IT"), ("EN", "EN"), ("ita", "IT"), ("", "EN"), (None, "EN"), ("e-n", "EN")],
    )
    def test_normalize_lang(self, raw, expected):
        assert cx.normalize_lang(raw) == expected

    def test_normalize_lang_custom_default(self):
        assert cx.normalize_lang("", default="IT") == "IT"
