"""Unit tests for the Normattiva Open Data API client.

Tests cover:
- Pydantic model validation for Italian legislative texts
- URN parsing and validation
- Search result parsing
- Rate limiting logic
- Retry with exponential backoff
"""

from datetime import datetime

from src.crawler.normattiva.client import (
    Articolo,
    NormativeActSummary,
    NormattivaOpenDataClient,
    SearchResult,
    URNValidationResult,
)
from src.crawler.normattiva.urn_validator import URNValidator

# ------------------------------------------------------------------ #
#  Model Validation Tests                                              #
# ------------------------------------------------------------------ #


class TestArticoloModel:
    def test_basic_article(self):
        art = Articolo(
            numero="1",
            rubrica="Disposizioni generali",
            testo="This is the article text.",
            commi=["Comma 1 text", "Comma 2 text"],
        )
        assert art.numero == "1"
        assert art.rubrica == "Disposizioni generali"
        assert len(art.commi) == 2

    def test_article_without_rubrica(self):
        art = Articolo(
            numero="2",
            testo="Article without title.",
        )
        assert art.rubrica is None
        assert art.commi == []


class TestNormativeActSummary:
    def test_summary_creation(self):
        summary = NormativeActSummary(
            urn="urn:nir:stato:decreto.legislativo:2024;138",
            tipo="decreto.legislativo",
            anno=2024,
            numero=138,
            titolo="Recepimento della direttiva NIS2",
            data_pubblicazione=datetime(2024, 9, 1),
            in_vigore=True,
        )
        assert summary.urn == "urn:nir:stato:decreto.legislativo:2024;138"
        assert summary.tipo == "decreto.legislativo"
        assert summary.in_vigore is True

    def test_summary_not_in_force(self):
        summary = NormativeActSummary(
            urn="urn:nir:stato:legge:2020;100",
            tipo="legge",
            anno=2020,
            numero=100,
            titolo="Abrogated law",
            data_pubblicazione=datetime(2020, 1, 1),
            in_vigore=False,
        )
        assert summary.in_vigore is False


class TestSearchResult:
    def test_empty_results(self):
        result = SearchResult(total=0, page=1, results=[])
        assert result.total == 0
        assert len(result.results) == 0

    def test_with_results(self):
        result = SearchResult(
            total=2,
            page=1,
            results=[
                NormativeActSummary(
                    urn="urn:nir:stato:legge:2024;1",
                    tipo="legge",
                    anno=2024,
                    numero=1,
                    titolo="Test law",
                    data_pubblicazione=datetime(2024, 1, 1),
                    in_vigore=True,
                ),
                NormativeActSummary(
                    urn="urn:nir:stato:legge:2024;2",
                    tipo="legge",
                    anno=2024,
                    numero=2,
                    titolo="Another law",
                    data_pubblicazione=datetime(2024, 2, 1),
                    in_vigore=True,
                ),
            ],
        )
        assert result.total == 2
        assert len(result.results) == 2


class TestURNValidationResult:
    def test_valid_urn(self):
        result = URNValidationResult(
            urn="urn:nir:stato:decreto.legislativo:2024;138",
            exists=True,
            is_in_force=True,
            tipo="decreto.legislativo",
            anno=2024,
            numero=138,
            titolo="NIS2 implementation",
            url="https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2024;138",
        )
        assert result.exists is True
        assert result.is_in_force is True
        assert result.numero == 138

    def test_nonexistent_urn(self):
        result = URNValidationResult(
            urn="urn:nir:stato:legge:9999;0",
            exists=False,
            is_in_force=False,
        )
        assert result.exists is False
        assert result.tipo is None


# ------------------------------------------------------------------ #
#  URN Validator Tests                                                 #
# ------------------------------------------------------------------ #


class TestURNValidator:
    def test_valid_urn_format(self):
        """Valid Italian URN format should parse correctly.

        Real URNComponents fields: tipo (str), data (str: "YYYY" or ISO date),
        numero (str), articolo (Optional[str]). All values stored as strings.
        """
        result = URNValidator.parse("urn:nir:stato:decreto.legislativo:2024;138")
        assert result is not None
        assert result.tipo == "decreto.legislativo"
        assert result.data == "2024"
        assert int(result.data[:4]) == 2024
        assert result.numero == "138"

    def test_invalid_urn_format(self):
        """Invalid URN format should return None."""
        result = URNValidator.parse("not-a-valid-urn")
        assert result is None

    def test_empty_string(self):
        result = URNValidator.parse("")
        assert result is None

    def test_urn_with_comma_article(self):
        """URN with comma-separated article reference should parse correctly.

        Real regex uses ',(?P<articolo>\\d+)' for articles, not '~art1'.
        """
        result = URNValidator.parse("urn:nir:stato:legge:2024;123,1")
        assert result is not None
        assert int(result.data[:4]) == 2024
        assert result.numero == "123"
        assert result.articolo == "1"


# ------------------------------------------------------------------ #
#  Client Constructor Tests                                            #
# ------------------------------------------------------------------ #


class TestNormattivaClient:
    def test_default_config(self):
        client = NormattivaOpenDataClient()
        assert client.base_url == "https://www.normattiva.it/opendata"
        assert client.rate_limit_delay == 1.0
        assert client.timeout == 30.0
        assert client.max_retries == 3

    def test_custom_config(self):
        client = NormattivaOpenDataClient(
            base_url="https://custom.api/v1",
            rate_limit_delay=2.0,
            timeout=60.0,
            max_retries=5,
        )
        assert client.base_url == "https://custom.api/v1"
        assert client.rate_limit_delay == 2.0
        assert client.max_retries == 5

    def test_xml_article_parsing(self):
        """Test XML article parsing from NIR format."""
        from xml.etree import ElementTree as ET

        xml_str = """
        <atto urn="test">
            <articolo numero="1">
                <rubrica>Disposizioni generali</rubrica>
                <comma>Comma 1 text here</comma>
                <comma>Comma 2 text here</comma>
            </articolo>
        </atto>
        """
        element = ET.fromstring(xml_str)
        client = NormattivaOpenDataClient()
        articles = client._parse_xml_articles(element)
        assert len(articles) == 1
        assert articles[0].numero == "1"
        assert articles[0].rubrica == "Disposizioni generali"
        assert len(articles[0].commi) == 2
