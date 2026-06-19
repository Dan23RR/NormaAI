"""Additional unit tests for the Normattiva Open Data API client.

NOTE ON FILE NAME: a test file named ``tests/test_normattiva_client.py`` already
exists and covers the Pydantic models, the URN validator and the client
constructor. To avoid clobbering it, this complementary suite lives in
``tests/test_normattiva_client_more.py`` and focuses on the *async* surface that
the original file does not exercise:

- ``validate_urn`` wiring (happy path, not-found -> 404, generic error)
- ``search`` parsing + graceful degradation to an empty ``SearchResult``
- ``get_atto`` full-text fetch (happy path, 404 -> ``None``, 409 handled)
- ``get_multivigenza`` version parsing and not-found handling
- ``download_bulk_xml`` XML:NIR parsing across a year range
- rate-limit delay logic (``_apply_rate_limit``)
- retry / exponential-backoff behaviour (``_request_with_retry``)
- model parsing helpers (``_parse_articles``, ``_parse_xml_articles``)

All HTTP traffic is mocked; nothing here touches the network, an LLM, a DB or a
real model download.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.crawler.normattiva.client import (
    Articolo,
    NormativeText,
    NormattivaOpenDataClient,
    SearchResult,
    URNValidationResult,
)

# --------------------------------------------------------------------------- #
#  Test helpers                                                                #
# --------------------------------------------------------------------------- #


def make_response(
    status_code: int = 200,
    json_data: dict | None = None,
    content: bytes | None = None,
):
    """Build a fake ``httpx.Response``-like object.

    ``raise_for_status`` mirrors httpx: it raises ``HTTPStatusError`` for >= 400
    and is a no-op otherwise. ``json()`` returns the supplied dict; ``content``
    returns the supplied bytes (used by the XML bulk path).
    """
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.content = content if content is not None else b""

    request = httpx.Request("GET", "https://www.normattiva.it/opendata/x")
    resp.request = request

    def _raise_for_status():
        if status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=resp)

    resp.raise_for_status.side_effect = _raise_for_status
    return resp


def client_with_mock_request(responses):
    """Return a client whose ``_request_with_retry`` yields ``responses``.

    ``responses`` may be a single object/exception or a list consumed in order.
    Exceptions in the list are raised; everything else is returned. Rate limiting
    is neutralised so tests don't sleep.
    """
    client = NormattivaOpenDataClient(rate_limit_delay=0)

    if not isinstance(responses, list):
        responses = [responses]
    queue = list(responses)

    async def fake_request(method, path, **kwargs):
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    client._request_with_retry = AsyncMock(side_effect=fake_request)
    return client


# --------------------------------------------------------------------------- #
#  validate_urn                                                                #
# --------------------------------------------------------------------------- #


class TestValidateUrn:
    async def test_validate_urn_happy_path(self):
        urn = "urn:nir:stato:decreto.legislativo:2024;138"
        resp = make_response(
            json_data={
                "exists": True,
                "is_in_force": True,
                "tipo": "decreto.legislativo",
                "anno": 2024,
                "numero": 138,
                "titolo": "NIS2 implementation",
                "url": "https://www.normattiva.it/uri-res/N2Ls?" + urn,
            }
        )
        client = client_with_mock_request(resp)

        result = await client.validate_urn(urn)

        assert isinstance(result, URNValidationResult)
        assert result.urn == urn
        assert result.exists is True
        assert result.is_in_force is True
        assert result.tipo == "decreto.legislativo"
        assert result.numero == 138
        # The request is wired to the /api/validate endpoint with the urn param.
        client._request_with_retry.assert_awaited_once()
        args, kwargs = client._request_with_retry.await_args
        assert args[0] == "GET"
        assert args[1] == "/api/validate"
        assert kwargs["params"] == {"urn": urn}

    async def test_validate_urn_defaults_when_fields_missing(self):
        """Absent ``exists``/``is_in_force`` default to False."""
        resp = make_response(json_data={})
        client = client_with_mock_request(resp)

        result = await client.validate_urn("urn:nir:stato:legge:2024;1")

        assert result.exists is False
        assert result.is_in_force is False
        assert result.tipo is None
        assert result.anno is None

    async def test_validate_urn_404_returns_negative_result(self):
        resp404 = make_response(status_code=404)
        err = httpx.HTTPStatusError("404", request=resp404.request, response=resp404)
        client = client_with_mock_request(err)

        result = await client.validate_urn("urn:nir:stato:legge:9999;0")

        assert result.exists is False
        assert result.is_in_force is False
        # On 404 the urn is still echoed back.
        assert result.urn == "urn:nir:stato:legge:9999;0"

    async def test_validate_urn_500_returns_negative_result(self):
        resp500 = make_response(status_code=500)
        err = httpx.HTTPStatusError("500", request=resp500.request, response=resp500)
        client = client_with_mock_request(err)

        result = await client.validate_urn("urn:nir:stato:legge:2024;1")

        assert result.exists is False
        assert result.is_in_force is False

    async def test_validate_urn_generic_exception_swallowed(self):
        client = client_with_mock_request(RuntimeError("boom"))

        result = await client.validate_urn("urn:nir:stato:legge:2024;1")

        assert result.exists is False
        assert result.is_in_force is False


# --------------------------------------------------------------------------- #
#  search                                                                      #
# --------------------------------------------------------------------------- #


class TestSearch:
    async def test_search_parses_results_and_pagination(self):
        resp = make_response(
            json_data={
                "total": 2,
                "results": [
                    {
                        "urn": "urn:nir:stato:legge:2024;1",
                        "tipo": "legge",
                        "anno": 2024,
                        "numero": 1,
                        "titolo": "Prima legge",
                        "data_pubblicazione": "2024-01-15T00:00:00Z",
                        "in_vigore": True,
                    },
                    {
                        "urn": "urn:nir:stato:legge:2024;2",
                        "tipo": "legge",
                        "anno": 2024,
                        "numero": 2,
                        # in_vigore omitted -> defaults True
                        "titolo": "Seconda legge",
                        "data_pubblicazione": "2024-02-20T00:00:00Z",
                    },
                ],
            }
        )
        client = client_with_mock_request(resp)

        result = await client.search("sicurezza", tipo_atto="legge", anno=2024, page=1)

        assert isinstance(result, SearchResult)
        assert result.total == 2
        assert result.page == 1
        assert len(result.results) == 2
        assert result.results[0].numero == 1
        # "Z" suffix in the date is normalised and parsed.
        assert result.results[0].data_pubblicazione.year == 2024
        # Missing in_vigore defaults to True per the source code.
        assert result.results[1].in_vigore is True

        # Optional filters are forwarded as query params.
        _, kwargs = client._request_with_retry.await_args
        assert kwargs["params"]["q"] == "sicurezza"
        assert kwargs["params"]["tipo_atto"] == "legge"
        assert kwargs["params"]["anno"] == 2024

    async def test_search_without_optional_filters_omits_params(self):
        resp = make_response(json_data={"total": 0, "results": []})
        client = client_with_mock_request(resp)

        result = await client.search("qualcosa")

        assert result.total == 0
        _, kwargs = client._request_with_retry.await_args
        params = kwargs["params"]
        assert "tipo_atto" not in params
        assert "anno" not in params
        assert params["limit"] == 20

    async def test_search_returns_empty_on_error(self):
        """Any exception during search degrades to an empty SearchResult."""
        client = client_with_mock_request(RuntimeError("network down"))

        result = await client.search("x", page=3)

        assert result.total == 0
        assert result.results == []
        # The requested page is preserved even on the error path.
        assert result.page == 3

    async def test_search_malformed_item_yields_empty(self):
        """A result row missing a required key triggers the except branch and
        the whole call degrades to empty (the comprehension raises KeyError)."""
        resp = make_response(
            json_data={
                "total": 1,
                "results": [{"urn": "urn:nir:stato:legge:2024;1"}],  # missing tipo etc.
            }
        )
        client = client_with_mock_request(resp)

        result = await client.search("x")

        assert result.total == 0
        assert result.results == []


# --------------------------------------------------------------------------- #
#  get_atto (full-text download)                                              #
# --------------------------------------------------------------------------- #


class TestGetAtto:
    async def test_get_atto_happy_path(self):
        resp = make_response(
            json_data={
                "urn": "urn:nir:stato:legge:2024;123",
                "tipo": "legge",
                "anno": 2024,
                "numero": 123,
                "titolo": "Legge di test",
                "testo_html": "<p>Testo</p>",
                "testo_plain": "Testo",
                "data_vigenza": "2024-03-01T00:00:00Z",
                "url": "https://www.normattiva.it/uri-res/...",
                "articoli": [
                    {
                        "numero": "1",
                        "rubrica": "Disposizioni generali",
                        "testo": "Testo art 1",
                        "commi": ["c1", "c2"],
                    }
                ],
            }
        )
        client = client_with_mock_request(resp)

        result = await client.get_atto("legge", 2024, 123)

        assert isinstance(result, NormativeText)
        assert result.numero == 123
        assert result.titolo == "Legge di test"
        assert len(result.articoli) == 1
        assert result.articoli[0].rubrica == "Disposizioni generali"
        assert result.articoli[0].commi == ["c1", "c2"]
        assert result.data_vigenza.year == 2024

        # Path is built from tipo/anno/numero; no article param -> params is None.
        args, kwargs = client._request_with_retry.await_args
        assert args[1] == "/api/atto/legge/2024/123"
        assert kwargs["params"] is None

    async def test_get_atto_with_articolo_param(self):
        resp = make_response(
            json_data={
                "urn": "urn:nir:stato:legge:2024;123",
                "tipo": "legge",
                "anno": 2024,
                "numero": 123,
                "titolo": "Legge di test",
                "data_vigenza": "2024-03-01T00:00:00Z",
                "articoli": [],
            }
        )
        client = client_with_mock_request(resp)

        await client.get_atto("legge", 2024, 123, articolo=5)

        _, kwargs = client._request_with_retry.await_args
        assert kwargs["params"] == {"articolo": 5}

    async def test_get_atto_404_returns_none(self):
        resp404 = make_response(status_code=404)
        err = httpx.HTTPStatusError("404", request=resp404.request, response=resp404)
        client = client_with_mock_request(err)

        result = await client.get_atto("legge", 9999, 0)

        assert result is None

    async def test_get_atto_409_is_handled_and_returns_none(self):
        """A 409 Conflict is a non-404 HTTPStatusError: get_atto logs it and
        returns None rather than propagating the exception."""
        resp409 = make_response(status_code=409)
        err = httpx.HTTPStatusError("409", request=resp409.request, response=resp409)
        client = client_with_mock_request(err)

        result = await client.get_atto("legge", 2024, 123)

        assert result is None

    async def test_get_atto_generic_error_returns_none(self):
        client = client_with_mock_request(ValueError("bad json"))

        result = await client.get_atto("legge", 2024, 123)

        assert result is None


# --------------------------------------------------------------------------- #
#  get_multivigenza                                                            #
# --------------------------------------------------------------------------- #


class TestGetMultivigenza:
    async def test_multivigenza_parses_versions(self):
        urn = "urn:nir:stato:legge:2024;123"
        resp = make_response(
            json_data={
                "versioni": [
                    {
                        "data_inizio": "2024-01-01T00:00:00Z",
                        "data_fine": "2024-06-30T00:00:00Z",
                        "testo": "Versione 1",
                        "modifiche": ["mod A"],
                    },
                    {
                        "data_inizio": "2024-07-01T00:00:00Z",
                        # data_fine omitted -> None (still in force)
                        "testo": "Versione 2",
                    },
                ]
            }
        )
        client = client_with_mock_request(resp)

        result = await client.get_multivigenza(urn, data_vigenza="2024-08-01")

        assert result is not None
        assert result.urn == urn
        assert len(result.versioni) == 2
        assert result.versioni[0].data_fine is not None
        assert result.versioni[1].data_fine is None
        assert result.versioni[0].modifiche == ["mod A"]
        assert result.versioni[1].modifiche == []

        # data_vigenza becomes the "data" query param.
        args, kwargs = client._request_with_retry.await_args
        assert args[1] == f"/api/multivigenza/{urn}"
        assert kwargs["params"] == {"data": "2024-08-01"}

    async def test_multivigenza_no_param_when_no_date(self):
        resp = make_response(json_data={"versioni": []})
        client = client_with_mock_request(resp)

        result = await client.get_multivigenza("urn:nir:stato:legge:2024;1")

        assert result is not None
        assert result.versioni == []
        _, kwargs = client._request_with_retry.await_args
        assert kwargs["params"] is None

    async def test_multivigenza_404_returns_none(self):
        resp404 = make_response(status_code=404)
        err = httpx.HTTPStatusError("404", request=resp404.request, response=resp404)
        client = client_with_mock_request(err)

        result = await client.get_multivigenza("urn:nir:stato:legge:9999;0")

        assert result is None

    async def test_multivigenza_generic_error_returns_none(self):
        client = client_with_mock_request(RuntimeError("boom"))

        result = await client.get_multivigenza("urn:nir:stato:legge:2024;1")

        assert result is None


# --------------------------------------------------------------------------- #
#  download_bulk_xml                                                           #
# --------------------------------------------------------------------------- #


class TestDownloadBulkXml:
    async def test_bulk_xml_parses_acts_across_years(self):
        xml = (
            b"<root><atto urn='urn:nir:stato:legge:2024;1'>"
            b"<articolo numero='1'>"
            b"<rubrica>Titolo</rubrica>"
            b"<comma>Comma uno</comma>"
            b"</articolo>"
            b"</atto></root>"
        )
        # Two-year range -> two requests; provide a response for each.
        client = client_with_mock_request([make_response(content=xml), make_response(content=xml)])

        results = await client.download_bulk_xml(tipo_atto="legge", anno_from=2024, anno_to=2025)

        # One <atto> per year -> two acts total.
        assert len(results) == 2
        assert results[0].urn == "urn:nir:stato:legge:2024;1"
        assert len(results[0].parsed_articles) == 1
        assert results[0].parsed_articles[0].numero == "1"
        assert results[0].parsed_articles[0].rubrica == "Titolo"
        assert "Comma uno" in results[0].parsed_articles[0].commi

    async def test_bulk_xml_skips_year_on_parse_error(self):
        """A malformed XML payload for one year is logged and skipped; the next
        year still contributes results (per-year try/except)."""
        good_xml = b"<root><atto urn='u2'><articolo numero='1'/></atto></root>"
        client = client_with_mock_request(
            [make_response(content=b"<<<not-xml"), make_response(content=good_xml)]
        )

        results = await client.download_bulk_xml(anno_from=2024, anno_to=2025)

        assert len(results) == 1
        assert results[0].urn == "u2"

    async def test_bulk_xml_request_error_per_year_is_skipped(self):
        client = client_with_mock_request(
            [httpx.ConnectError("down"), make_response(content=b"<root></root>")]
        )

        results = await client.download_bulk_xml(anno_from=2024, anno_to=2025)

        # First year errored (skipped), second year had no <atto> -> empty list.
        assert results == []


# --------------------------------------------------------------------------- #
#  _apply_rate_limit                                                          #
# --------------------------------------------------------------------------- #


class TestRateLimit:
    async def test_rate_limit_sleeps_when_called_too_soon(self):
        client = NormattivaOpenDataClient(rate_limit_delay=1.0)

        # Freeze the event-loop clock so elapsed time is 0 -> must sleep the
        # full delay.
        fake_loop = MagicMock()
        fake_loop.time.return_value = 100.0
        client._last_request_time = 100.0  # "just made a request"

        with (
            patch("asyncio.get_event_loop", return_value=fake_loop),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await client._apply_rate_limit()

        mock_sleep.assert_awaited_once()
        # Slept the full configured delay (1.0 - 0 elapsed).
        assert mock_sleep.await_args.args[0] == pytest.approx(1.0)

    async def test_rate_limit_no_sleep_when_enough_time_passed(self):
        client = NormattivaOpenDataClient(rate_limit_delay=1.0)

        fake_loop = MagicMock()
        fake_loop.time.return_value = 100.0
        client._last_request_time = 50.0  # 50s ago, far beyond the 1s delay

        with (
            patch("asyncio.get_event_loop", return_value=fake_loop),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await client._apply_rate_limit()

        mock_sleep.assert_not_awaited()
        # Last request time is updated to "now".
        assert client._last_request_time == 100.0


# --------------------------------------------------------------------------- #
#  _request_with_retry                                                         #
# --------------------------------------------------------------------------- #


class TestRequestWithRetry:
    async def test_returns_response_on_success(self):
        client = NormattivaOpenDataClient(rate_limit_delay=0, max_retries=3)
        ok = make_response(status_code=200, json_data={"ok": True})

        mock_http = MagicMock()
        mock_http.request = AsyncMock(return_value=ok)
        client._client = mock_http

        with patch.object(client, "_apply_rate_limit", new_callable=AsyncMock):
            result = await client._request_with_retry("GET", "/x")

        assert result is ok
        assert mock_http.request.await_count == 1

    async def test_client_error_not_retried(self):
        """A 4xx error is raised immediately without retrying."""
        client = NormattivaOpenDataClient(rate_limit_delay=0, max_retries=3)
        resp = make_response(status_code=404)

        mock_http = MagicMock()
        mock_http.request = AsyncMock(return_value=resp)
        client._client = mock_http

        with (
            patch.object(client, "_apply_rate_limit", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(httpx.HTTPStatusError),
        ):
            await client._request_with_retry("GET", "/x")

        # No retry, no backoff sleep for a client error.
        assert mock_http.request.await_count == 1
        mock_sleep.assert_not_awaited()

    async def test_server_error_retries_then_raises(self):
        """5xx errors are retried up to max_retries, then the last exception
        is re-raised."""
        client = NormattivaOpenDataClient(rate_limit_delay=0, max_retries=3)
        resp = make_response(status_code=503)

        mock_http = MagicMock()
        mock_http.request = AsyncMock(return_value=resp)
        client._client = mock_http

        with (
            patch.object(client, "_apply_rate_limit", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(httpx.HTTPStatusError),
        ):
            await client._request_with_retry("GET", "/x")

        # All attempts consumed.
        assert mock_http.request.await_count == 3
        # Backoff sleeps happen on the first (max_retries - 1) attempts.
        assert mock_sleep.await_count == 2

    async def test_server_error_then_success(self):
        """Recovers if a later attempt succeeds."""
        client = NormattivaOpenDataClient(rate_limit_delay=0, max_retries=3)
        bad = make_response(status_code=500)
        good = make_response(status_code=200, json_data={"ok": True})

        mock_http = MagicMock()
        mock_http.request = AsyncMock(side_effect=[bad, good])
        client._client = mock_http

        with (
            patch.object(client, "_apply_rate_limit", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client._request_with_retry("GET", "/x")

        assert result is good
        assert mock_http.request.await_count == 2

    async def test_request_error_retries_then_raises(self):
        """Transport-level RequestError is retried then re-raised."""
        client = NormattivaOpenDataClient(rate_limit_delay=0, max_retries=2)

        mock_http = MagicMock()
        mock_http.request = AsyncMock(side_effect=httpx.ConnectError("down"))
        client._client = mock_http

        with (
            patch.object(client, "_apply_rate_limit", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(httpx.ConnectError),
        ):
            await client._request_with_retry("GET", "/x")

        assert mock_http.request.await_count == 2
        # One backoff sleep between the two attempts.
        assert mock_sleep.await_count == 1


# --------------------------------------------------------------------------- #
#  client lifecycle helpers                                                    #
# --------------------------------------------------------------------------- #


class TestClientLifecycle:
    async def test_ensure_client_creates_and_reuses(self):
        client = NormattivaOpenDataClient()
        assert client._client is None

        with patch("httpx.AsyncClient") as mock_async_client:
            instance = MagicMock()
            mock_async_client.return_value = instance

            first = await client._ensure_client()
            second = await client._ensure_client()

        assert first is instance
        # The same instance is reused; AsyncClient constructed exactly once.
        assert second is instance
        mock_async_client.assert_called_once()

    async def test_async_context_manager_opens_and_closes(self):
        with patch("httpx.AsyncClient") as mock_async_client:
            instance = MagicMock()
            instance.aclose = AsyncMock()
            mock_async_client.return_value = instance

            async with NormattivaOpenDataClient() as client:
                assert client._client is instance

            instance.aclose.assert_awaited_once()

    async def test_close_is_safe_when_no_client(self):
        client = NormattivaOpenDataClient()
        # Should not raise even though no client was ever created.
        await client.close()

    async def test_close_closes_existing_client(self):
        client = NormattivaOpenDataClient()
        instance = MagicMock()
        instance.aclose = AsyncMock()
        client._client = instance

        await client.close()

        instance.aclose.assert_awaited_once()


# --------------------------------------------------------------------------- #
#  parsing helpers                                                             #
# --------------------------------------------------------------------------- #


class TestParseHelpers:
    def test_parse_articles_handles_missing_fields(self):
        client = NormattivaOpenDataClient()
        parsed = client._parse_articles(
            [
                {"numero": "1", "rubrica": "R", "testo": "T", "commi": ["a"]},
                {},  # all fields missing -> defaults
            ]
        )
        assert len(parsed) == 2
        assert parsed[0].numero == "1"
        assert parsed[0].commi == ["a"]
        # Missing-field article gets safe defaults.
        assert parsed[1].numero == ""
        assert parsed[1].rubrica is None
        assert parsed[1].testo == ""
        assert parsed[1].commi == []

    def test_parse_articles_empty_list(self):
        client = NormattivaOpenDataClient()
        assert client._parse_articles([]) == []

    def test_parse_xml_articles_without_rubrica(self):
        from xml.etree import ElementTree as ET

        xml = """
        <atto urn="x">
            <articolo numero="7">
                <comma>Primo comma</comma>
            </articolo>
        </atto>
        """
        element = ET.fromstring(xml)
        client = NormattivaOpenDataClient()
        articoli = client._parse_xml_articles(element)

        assert len(articoli) == 1
        assert articoli[0].numero == "7"
        assert articoli[0].rubrica is None
        assert articoli[0].commi == ["Primo comma"]
        assert isinstance(articoli[0], Articolo)

    def test_parse_xml_articles_empty_when_no_articolo(self):
        from xml.etree import ElementTree as ET

        element = ET.fromstring("<atto urn='x'></atto>")
        client = NormattivaOpenDataClient()
        assert client._parse_xml_articles(element) == []
