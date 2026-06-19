"""
Additional unit tests for the EUR-Lex SPARQL + CELLAR HTTP client.

The pre-existing tests/test_eurlex_client.py covers the static helpers
(_celex_to_doc_type, CORE_FRAMEWORKS, dataclass defaults, constructor) but
skips every network path. This file complements it by exercising the
HTTP/SPARQL behaviour with the transport layer fully mocked - no real
network, no real LLM, no DB. It asserts the documented CELLAR fix:
download_full_text_html must hit publications.europa.eu with
`Accept: application/xhtml+xml` and an ISO 639-3 Accept-Language.

A non-colliding filename (..._more.py) is used because
tests/test_eurlex_client.py already exists.

Run:
    pytest tests/test_eurlex_client_more.py -q
"""

from unittest.mock import MagicMock, patch

import pytest

from src.crawler.eurlex import client as eurlex_module
from src.crawler.eurlex.client import (
    CELLAR_CELEX_BASE,
    CORE_FRAMEWORKS,
    LANG_ISO639_3,
    RESOURCE_TYPES,
    SPARQL_PREFIXES,
    AmendmentInfo,
    EurLexClient,
    RegulationMetadata,
)

# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client():
    """An EurLexClient whose HTTP client and rate-limiter are neutralised.

    - _http is replaced with a MagicMock so no socket is ever opened.
    - _rate_limit is patched to a no-op so tests never sleep on the clock.
    - _sparql is replaced with a MagicMock so SPARQLWrapper never talks out.
    """
    c = EurLexClient(request_delay=0.0, max_retries=3)
    c._http = MagicMock()
    c._sparql = MagicMock()
    c._rate_limit = MagicMock()
    yield c
    # close() just closes the (already-mocked) http client; safe to call.
    c.close()


def _sparql_bindings(rows):
    """Wrap a list of binding dicts in the SPARQL JSON envelope."""
    return {"results": {"bindings": rows}}


# --------------------------------------------------------------------------- #
#  Module-level constants / structure                                         #
# --------------------------------------------------------------------------- #


class TestModuleConstants:
    def test_resource_types_are_authority_uris(self):
        # Every tracked resource type must be a Publications Office authority URI.
        assert set(RESOURCE_TYPES) == {
            "directive",
            "regulation",
            "delegated_dir",
            "delegated_reg",
            "implementing_dir",
            "implementing_reg",
        }
        for uri in RESOURCE_TYPES.values():
            assert uri.startswith("http://publications.europa.eu/resource/authority/resource-type/")

    def test_cellar_base_is_publications_office(self):
        # The known fix: full text comes from CELLAR, not the legal-content frontend.
        assert CELLAR_CELEX_BASE == "http://publications.europa.eu/resource/celex"
        assert "eur-lex.europa.eu" not in CELLAR_CELEX_BASE

    def test_lang_map_uses_iso639_3_codes(self):
        # Content negotiation uses 3-letter ISO 639-3 codes, not the 2-letter form.
        assert LANG_ISO639_3["EN"] == "eng"
        assert LANG_ISO639_3["IT"] == "ita"
        for code in LANG_ISO639_3.values():
            assert len(code) == 3

    def test_sparql_prefixes_declare_cdm(self):
        assert "cdm:" in SPARQL_PREFIXES
        assert "publications.europa.eu/ontology/cdm#" in SPARQL_PREFIXES

    def test_core_frameworks_value_shape(self):
        # Each framework maps CELEX -> human-readable description (both strings).
        for celex_map in CORE_FRAMEWORKS.values():
            assert isinstance(celex_map, dict)
            for celex, desc in celex_map.items():
                assert isinstance(celex, str)
                assert isinstance(desc, str) and desc


# --------------------------------------------------------------------------- #
#  _sanitize_celex                                                             #
# --------------------------------------------------------------------------- #


class TestSanitizeCelex:
    def test_passthrough_valid(self):
        assert EurLexClient._sanitize_celex("32022L2464") == "32022L2464"

    def test_strips_injection_characters(self):
        # SPARQL-injection attempt: only alphanumerics survive.
        out = EurLexClient._sanitize_celex('32022L2464" } INJECT {')
        assert out == "32022L2464INJECT"
        assert '"' not in out and "{" not in out and " " not in out

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="Invalid CELEX"):
            EurLexClient._sanitize_celex("3202")  # 4 chars after sanitize

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="Invalid CELEX"):
            EurLexClient._sanitize_celex("3" * 21)

    def test_boundary_lengths_ok(self):
        # 5 and 20 are the inclusive bounds.
        assert EurLexClient._sanitize_celex("32022") == "32022"
        assert EurLexClient._sanitize_celex("3" * 20) == "3" * 20


# --------------------------------------------------------------------------- #
#  _celex_to_doc_type (edge cases not in the existing test file)              #
# --------------------------------------------------------------------------- #


class TestCelexDocTypeEdges:
    def test_other_type_char(self):
        assert EurLexClient._celex_to_doc_type("32020O0001") == "other"

    def test_unknown_type_char(self):
        # 'X' at index 5 is not in the mapping table.
        assert EurLexClient._celex_to_doc_type("32020X0001") == "unknown"

    def test_len_six_is_unknown(self):
        # Guard is `len < 7`, so a 6-char CELEX is rejected before indexing.
        assert EurLexClient._celex_to_doc_type("32020L") == "unknown"

    def test_len_seven_reads_index_five(self):
        assert EurLexClient._celex_to_doc_type("32020L1") == "directive"


# --------------------------------------------------------------------------- #
#  _build_sparql_query                                                         #
# --------------------------------------------------------------------------- #


class TestBuildSparqlQuery:
    def test_substitutes_double_brace_placeholder(self):
        out = EurLexClient._build_sparql_query("celex={{celex}}", {"celex": "32022L2464"})
        assert out == "celex=32022L2464"

    def test_strips_special_chars_from_value(self):
        # Quotes, braces, backslashes and newlines are stripped from the value.
        out = EurLexClient._build_sparql_query("v={{x}}", {"x": 'a"b\\c\n{d}e'})
        assert out == "v=abcde"

    def test_unreferenced_placeholder_left_intact(self):
        # Only placeholders present in params are replaced.
        out = EurLexClient._build_sparql_query("a={{a}} b={{b}}", {"a": "1"})
        assert out == "a=1 b={{b}}"


# --------------------------------------------------------------------------- #
#  _execute_sparql (retry / backoff)                                          #
# --------------------------------------------------------------------------- #


class TestExecuteSparql:
    def test_prepends_prefixes_and_returns_results(self, client):
        envelope = _sparql_bindings([{"title": {"value": "X"}}])
        query_obj = MagicMock()
        query_obj.convert.return_value = envelope
        client._sparql.query.return_value = query_obj

        out = client._execute_sparql("SELECT * WHERE {}")

        assert out is envelope
        sent = client._sparql.setQuery.call_args[0][0]
        assert sent.startswith(SPARQL_PREFIXES)
        assert "SELECT * WHERE {}" in sent

    def test_retries_then_succeeds(self, client):
        good = MagicMock()
        good.convert.return_value = _sparql_bindings([])
        # First call raises, second returns a usable object.
        client._sparql.query.side_effect = [RuntimeError("boom"), good]

        with patch.object(eurlex_module.time, "sleep") as mock_sleep:
            out = client._execute_sparql("SELECT * WHERE {}")

        assert out == _sparql_bindings([])
        assert client._sparql.query.call_count == 2
        mock_sleep.assert_called_once()  # one backoff between the two attempts

    def test_raises_after_max_retries(self, client):
        client._sparql.query.side_effect = RuntimeError("permanent")

        with (
            patch.object(eurlex_module.time, "sleep"),
            pytest.raises(RuntimeError, match="permanent"),
        ):
            client._execute_sparql("SELECT * WHERE {}")

        assert client._sparql.query.call_count == client.max_retries


# --------------------------------------------------------------------------- #
#  fetch_regulation_metadata                                                   #
# --------------------------------------------------------------------------- #


class TestFetchRegulationMetadata:
    def test_parses_bindings_and_detects_framework(self, client):
        rows = [
            {
                "title": {"value": "Corporate Sustainability Reporting Directive"},
                "date": {"value": "2022-12-14"},
                "inForce": {"value": "true"},
            }
        ]
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings(rows)) as ex:
            meta = client.fetch_regulation_metadata("32022L2464")

        assert isinstance(meta, RegulationMetadata)
        assert meta.celex == "32022L2464"
        assert meta.title == "Corporate Sustainability Reporting Directive"
        assert meta.date_document == "2022-12-14"
        assert meta.is_in_force is True
        assert meta.framework == "CSRD"  # from CORE_FRAMEWORKS map
        assert meta.doc_type == "directive"
        # The CELEX literal is embedded in the executed query.
        assert "32022L2464" in ex.call_args[0][0]

    def test_title_falls_back_to_known_description(self, client):
        # Empty SPARQL title -> falls back to CORE_FRAMEWORKS description.
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings([])):
            meta = client.fetch_regulation_metadata("32024R1689")  # AI Act
        assert meta.framework == "AI_ACT"
        assert meta.title == "Artificial Intelligence Act"
        assert meta.doc_type == "regulation"
        assert meta.is_in_force is None  # no bindings -> stays None

    def test_unknown_celex_has_empty_framework(self, client):
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings([])):
            meta = client.fetch_regulation_metadata("31999L9999")
        assert meta.framework == ""
        assert meta.title == ""

    def test_in_force_false_parsed(self, client):
        rows = [{"inForce": {"value": "FALSE"}}]
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings(rows)):
            meta = client.fetch_regulation_metadata("32022L2464")
        assert meta.is_in_force is False

    def test_sanitizes_celex_before_query(self, client):
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings([])):
            meta = client.fetch_regulation_metadata('32022L2464"INJECT')
        # The dirty input is sanitized to alphanumerics.
        assert meta.celex == "32022L2464INJECT"


# --------------------------------------------------------------------------- #
#  fetch_amendments                                                            #
# --------------------------------------------------------------------------- #


class TestFetchAmendments:
    def test_empty_results(self, client):
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings([])):
            out = client.fetch_amendments("32022L2464")
        assert out == []

    def test_parses_amendments(self, client):
        rows = [
            {
                "amendingCelex": {"value": "32025L0794"},
                "amendingTitle": {"value": "Stop-the-Clock Directive"},
                "amendDate": {"value": "2025-04-01"},
            },
            {
                "amendingCelex": {"value": "32026L0470"},
                "amendingTitle": {"value": "Omnibus I Directive"},
                "amendDate": {"value": "2026-01-15"},
            },
        ]
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings(rows)):
            out = client.fetch_amendments("32022L2464")

        assert len(out) == 2
        assert all(isinstance(a, AmendmentInfo) for a in out)
        assert out[0].original_celex == "32022L2464"
        assert out[0].amending_celex == "32025L0794"
        assert out[0].amending_title == "Stop-the-Clock Directive"
        assert out[1].amending_celex == "32026L0470"

    def test_skips_rows_without_amending_celex(self, client):
        # Rows whose amendingCelex binding is absent/empty are dropped.
        rows = [
            {"amendingTitle": {"value": "no celex here"}},
            {"amendingCelex": {"value": ""}},
            {"amendingCelex": {"value": "32026L0470"}},
        ]
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings(rows)):
            out = client.fetch_amendments("32022L2464")
        assert len(out) == 1
        assert out[0].amending_celex == "32026L0470"


# --------------------------------------------------------------------------- #
#  fetch_recent_legislation                                                    #
# --------------------------------------------------------------------------- #


class TestFetchRecentLegislation:
    def test_empty(self, client):
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings([])):
            out = client.fetch_recent_legislation(days_back=7)
        assert out == []

    def test_non_empty_parsing(self, client):
        rows = [
            {
                "celex": {"value": "32026L0470"},
                "title": {"value": "Omnibus I Directive"},
                "date": {"value": "2026-06-15"},
            }
        ]
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings(rows)):
            out = client.fetch_recent_legislation(days_back=30)

        assert len(out) == 1
        reg = out[0]
        assert reg.celex == "32026L0470"
        assert reg.title == "Omnibus I Directive"
        assert reg.date_document == "2026-06-15"
        assert reg.doc_type == "directive"

    def test_query_embeds_resource_types_and_date(self, client):
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings([])) as ex:
            client.fetch_recent_legislation(days_back=7)

        query = ex.call_args[0][0]
        # All six resource-type URIs are inlined into the FILTER(?type IN (...)).
        for uri in RESOURCE_TYPES.values():
            assert uri in query
        # A strictly-formatted ISO date literal is present.
        assert "xsd:date" in query

    def test_skips_rows_without_celex(self, client):
        rows = [
            {"title": {"value": "no celex"}},
            {"celex": {"value": "32026L0470"}, "title": {"value": "ok"}},
        ]
        with patch.object(client, "_execute_sparql", return_value=_sparql_bindings(rows)):
            out = client.fetch_recent_legislation()
        assert len(out) == 1
        assert out[0].celex == "32026L0470"


# --------------------------------------------------------------------------- #
#  download_full_text_html  (CELLAR HTTP)                                      #
# --------------------------------------------------------------------------- #


def _http_response(status_code, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    return resp


class TestDownloadFullTextHtml:
    def test_happy_path_returns_xhtml(self, client):
        body = "<html><body>sustainability reporting</body></html>"
        client._http.get.return_value = _http_response(200, body)

        out = client.download_full_text_html("32022L2464", lang="EN")

        assert out == body
        # Exactly one GET, no retries on success.
        assert client._http.get.call_count == 1

    def test_hits_cellar_with_xhtml_accept_and_iso639_3_lang(self, client):
        # This is the documented production fix - assert it precisely.
        client._http.get.return_value = _http_response(200, "<html/>")

        client.download_full_text_html("32022L2464", lang="IT")

        args, kwargs = client._http.get.call_args
        url = args[0] if args else kwargs.get("url")
        headers = kwargs["headers"]
        assert url == f"{CELLAR_CELEX_BASE}/32022L2464"
        assert "publications.europa.eu" in url
        assert "eur-lex.europa.eu/legal-content" not in url
        assert headers["Accept"] == "application/xhtml+xml"
        # IT -> ISO 639-3 'ita', not the 2-letter form.
        assert headers["Accept-Language"] == "ita"

    def test_unknown_language_defaults_to_eng(self, client):
        client._http.get.return_value = _http_response(200, "<html/>")
        client.download_full_text_html("32022L2464", lang="ZZ")
        headers = client._http.get.call_args[1]["headers"]
        assert headers["Accept-Language"] == "eng"

    def test_404_returns_none_without_retry(self, client):
        client._http.get.return_value = _http_response(404)
        with patch.object(eurlex_module.time, "sleep") as mock_sleep:
            out = client.download_full_text_html("32022L2464")
        assert out is None
        # 404 is deterministic: no retry, no sleep.
        assert client._http.get.call_count == 1
        mock_sleep.assert_not_called()

    def test_406_returns_none_without_retry(self, client):
        client._http.get.return_value = _http_response(406)
        with patch.object(eurlex_module.time, "sleep"):
            out = client.download_full_text_html("32022L2464")
        assert out is None
        assert client._http.get.call_count == 1

    def test_202_is_transient_and_exhausts_retries(self, client):
        # 202 (still rendering) is transient: retried max_retries times, then None.
        client._http.get.return_value = _http_response(202, "")
        with patch.object(eurlex_module.time, "sleep") as mock_sleep:
            out = client.download_full_text_html("32022L2464")
        assert out is None
        assert client._http.get.call_count == client.max_retries
        # Sleeps between attempts only (max_retries - 1 times).
        assert mock_sleep.call_count == client.max_retries - 1

    def test_empty_200_is_treated_as_transient(self, client):
        # 200 with empty body does NOT count as success.
        client._http.get.return_value = _http_response(200, "")
        with patch.object(eurlex_module.time, "sleep"):
            out = client.download_full_text_html("32022L2464")
        assert out is None
        assert client._http.get.call_count == client.max_retries

    def test_retry_after_header_honored(self, client):
        # A numeric Retry-After overrides the exponential backoff value.
        client._http.get.return_value = _http_response(503, "", headers={"Retry-After": "7"})
        with patch.object(eurlex_module.time, "sleep") as mock_sleep:
            client.download_full_text_html("32022L2464")
        # Every backoff sleep should use the Retry-After value (7s).
        assert mock_sleep.call_count == client.max_retries - 1
        for call in mock_sleep.call_args_list:
            assert call.args[0] == 7.0

    def test_transient_then_success(self, client):
        # First attempt transient (202), second attempt 200 with body.
        client._http.get.side_effect = [
            _http_response(202, ""),
            _http_response(200, "<html>ok</html>"),
        ]
        with patch.object(eurlex_module.time, "sleep") as mock_sleep:
            out = client.download_full_text_html("32022L2464")
        assert out == "<html>ok</html>"
        assert client._http.get.call_count == 2
        mock_sleep.assert_called_once()

    def test_exception_is_caught_and_retried(self, client):
        # A raised transport error is caught; retries proceed; eventually None.
        client._http.get.side_effect = RuntimeError("connection reset")
        with patch.object(eurlex_module.time, "sleep"):
            out = client.download_full_text_html("32022L2464")
        assert out is None
        assert client._http.get.call_count == client.max_retries

    def test_invalid_celex_raises_before_http(self, client):
        with pytest.raises(ValueError, match="Invalid CELEX"):
            client.download_full_text_html("xx")
        client._http.get.assert_not_called()


# --------------------------------------------------------------------------- #
#  check_for_new_amendments / crawl_all_core_frameworks                        #
# --------------------------------------------------------------------------- #


class TestCheckForNewAmendments:
    def test_empty_when_no_amendments(self, client):
        with patch.object(client, "fetch_amendments", return_value=[]):
            out = client.check_for_new_amendments(["32022L2464", "32024L1760"])
        assert out == []

    def test_aggregates_across_tracked_celex(self, client):
        def fake(celex):
            if celex == "32022L2464":
                return [AmendmentInfo(original_celex=celex, amending_celex="32025L0794")]
            return []

        with patch.object(client, "fetch_amendments", side_effect=fake):
            out = client.check_for_new_amendments(["32022L2464", "32024R1689"])

        assert len(out) == 1
        assert out[0].amending_celex == "32025L0794"

    def test_empty_input_list(self, client):
        with patch.object(client, "fetch_amendments") as fa:
            out = client.check_for_new_amendments([])
        assert out == []
        fa.assert_not_called()


class TestCrawlAllCoreFrameworks:
    def test_crawls_every_celex_and_builds_url(self, client):
        meta_calls = []

        def fake_meta(celex):
            meta_calls.append(celex)
            return RegulationMetadata(celex=celex)

        total_celex = sum(len(m) for m in CORE_FRAMEWORKS.values())

        with (
            patch.object(client, "fetch_regulation_metadata", side_effect=fake_meta),
            patch.object(client, "fetch_amendments", return_value=[]),
        ):
            out = client.crawl_all_core_frameworks()

        assert len(out) == total_celex
        assert len(meta_calls) == total_celex
        # Framework is stamped on every result and the legal-content URL is built.
        for meta in out:
            assert meta.framework in CORE_FRAMEWORKS
            assert meta.full_text_url == (
                "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/" f"?uri=CELEX:{meta.celex}"
            )

    def test_amendments_attached_to_metadata(self, client):
        amend = AmendmentInfo(original_celex="x", amending_celex="32026L0470")
        with (
            patch.object(
                client,
                "fetch_regulation_metadata",
                side_effect=lambda c: RegulationMetadata(celex=c),
            ),
            patch.object(client, "fetch_amendments", return_value=[amend]),
        ):
            out = client.crawl_all_core_frameworks()
        # Every regulation gets the amending CELEX list copied in.
        assert all(meta.amendments == ["32026L0470"] for meta in out)


# --------------------------------------------------------------------------- #
#  Context manager / lifecycle                                                #
# --------------------------------------------------------------------------- #


class TestLifecycle:
    def test_context_manager_closes_http(self):
        with EurLexClient() as c:
            c._http = MagicMock()
            http = c._http
        http.close.assert_called_once()

    def test_close_is_idempotent_via_mock(self, client):
        client.close()
        client._http.close.assert_called()
