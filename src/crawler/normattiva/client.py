"""
Normattiva Open Data API Client

Comprehensive async HTTP client for the Italian Normattiva Open Data API.
Provides access to Italian legislative documents, decrees, regulations, and EU directives.

API documentation: https://www.normattiva.it/opendata/
Available since: January 1, 2026
"""

import asyncio
import logging
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Data Models
# ============================================================================


class Articolo(BaseModel):
    """Represents a single article in an Italian legislative text."""

    numero: str
    rubrica: str | None = None
    testo: str
    commi: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "numero": "1",
                "rubrica": "Disposizioni generali",
                "testo": "The article text here",
                "commi": ["Comma 1 text", "Comma 2 text"],
            }
        }
    )


class NormativeActSummary(BaseModel):
    """Summary of a normative act returned from search results."""

    urn: str
    tipo: str  # legge, decreto.legislativo, etc.
    anno: int
    numero: int
    titolo: str
    data_pubblicazione: datetime
    in_vigore: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "urn": "urn:nir:stato:legge:2024;123",
                "tipo": "legge",
                "anno": 2024,
                "numero": 123,
                "titolo": "Legge di conversione",
                "data_pubblicazione": "2024-01-15T00:00:00",
                "in_vigore": True,
            }
        }
    )


class SearchResult(BaseModel):
    """Result of a search query against Normattiva Open Data."""

    total: int
    page: int
    results: list[NormativeActSummary]


class NormativeText(BaseModel):
    """Full legislative text with parsed articles and metadata."""

    urn: str
    tipo: str
    anno: int
    numero: int
    titolo: str
    testo_html: str
    testo_plain: str
    articoli: list[Articolo]
    data_vigenza: datetime
    url: str


class MultivigenzaResult(BaseModel):
    """Multi-version result showing how a law changed over time."""

    urn: str
    versioni: list["Versione"]


class Versione(BaseModel):
    """Single version of a law at a point in time."""

    data_inizio: datetime
    data_fine: datetime | None = None
    testo: str
    modifiche: list[str] = Field(default_factory=list)


class NormativeActXML(BaseModel):
    """XML representation of a normative act with parsed content."""

    urn: str
    xml_content: str
    parsed_articles: list[Articolo]


class URNValidationResult(BaseModel):
    """Result of URN validation against Normattiva."""

    urn: str
    exists: bool
    is_in_force: bool
    tipo: str | None = None
    anno: int | None = None
    numero: int | None = None
    titolo: str | None = None
    url: str | None = None


# Update forward references
MultivigenzaResult.model_rebuild()


# ============================================================================
# Normattiva Open Data Client
# ============================================================================


class NormattivaOpenDataClient:
    """
    Async HTTP client for the Italian Normattiva Open Data API.

    Provides methods to search, retrieve, and analyze Italian and EU legislative
    documents with automatic rate limiting and retry logic.
    """

    def __init__(
        self,
        base_url: str = "https://www.normattiva.it/opendata",
        rate_limit_delay: float = 1.0,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the Normattiva Open Data client.

        Args:
            base_url: Base URL for the Normattiva Open Data API
            rate_limit_delay: Delay in seconds between requests
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.base_url = base_url
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time: float = 0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": "NormaAI/1.0 (Italian Legislative Intelligence Platform)",
                "Accept": "application/json, application/xml",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "NormaAI/1.0 (Italian Legislative Intelligence Platform)",
                    "Accept": "application/json, application/xml",
                },
            )
        return self._client

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        current_time = asyncio.get_event_loop().time()
        time_since_last_request = current_time - self._last_request_time

        if time_since_last_request < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last_request)

        self._last_request_time = asyncio.get_event_loop().time()

    async def _request_with_retry(self, method: str, path: str, **kwargs) -> httpx.Response:
        """
        Execute HTTP request with exponential backoff retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path relative to base_url
            **kwargs: Additional arguments to pass to httpx

        Returns:
            HTTP response

        Raises:
            httpx.HTTPError: If all retries are exhausted
        """
        await self._apply_rate_limit()
        client = await self._ensure_client()

        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code < 500:
                    # Don't retry on client errors
                    logger.error(f"HTTP {e.response.status_code} error: {e}")
                    raise
                # Retry on server errors
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt  # exponential backoff
                    logger.warning(
                        f"Server error on attempt {attempt + 1}/{self.max_retries}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
            except httpx.RequestError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Request error on attempt {attempt + 1}/{self.max_retries}: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)

        logger.error(f"All {self.max_retries} retry attempts exhausted")
        if last_exception:
            raise last_exception
        raise RuntimeError("Request failed after all retries")

    async def search(
        self,
        query: str,
        tipo_atto: str | None = None,
        anno: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> SearchResult:
        """
        Search for normative acts in Normattiva.

        Args:
            query: Search query string
            tipo_atto: Optional filter by act type (legge, decreto.legislativo, etc.)
            anno: Optional filter by year
            page: Result page number (1-indexed)
            limit: Results per page (default 20, max typically 100)

        Returns:
            SearchResult containing matching acts and pagination info
        """
        try:
            params = {"q": query, "page": page, "limit": limit}
            if tipo_atto:
                params["tipo_atto"] = tipo_atto
            if anno:
                params["anno"] = anno

            response = await self._request_with_retry("GET", "/api/ricerca", params=params)

            data = response.json()
            results = [
                NormativeActSummary(
                    urn=act["urn"],
                    tipo=act["tipo"],
                    anno=act["anno"],
                    numero=act["numero"],
                    titolo=act["titolo"],
                    data_pubblicazione=datetime.fromisoformat(
                        act["data_pubblicazione"].replace("Z", "+00:00")
                    ),
                    in_vigore=act.get("in_vigore", True),
                )
                for act in data.get("results", [])
            ]

            return SearchResult(total=data.get("total", 0), page=page, results=results)
        except Exception as e:
            logger.error(f"Search error for '{query}': {e}")
            return SearchResult(total=0, page=page, results=[])

    async def get_atto(
        self, tipo: str, anno: int, numero: int, articolo: int | None = None
    ) -> NormativeText | None:
        """
        Retrieve full text of a normative act.

        Args:
            tipo: Act type (e.g., 'legge', 'decreto.legislativo')
            anno: Year of act
            numero: Act number
            articolo: Optional specific article number

        Returns:
            NormativeText with full content and parsed articles, or None if not found
        """
        try:
            path = f"/api/atto/{tipo}/{anno}/{numero}"
            params = {}
            if articolo:
                params["articolo"] = articolo

            response = await self._request_with_retry(
                "GET", path, params=params if params else None
            )

            data = response.json()
            articoli = self._parse_articles(data.get("articoli", []))

            return NormativeText(
                urn=data["urn"],
                tipo=data["tipo"],
                anno=data["anno"],
                numero=data["numero"],
                titolo=data["titolo"],
                testo_html=data.get("testo_html", ""),
                testo_plain=data.get("testo_plain", ""),
                articoli=articoli,
                data_vigenza=datetime.fromisoformat(data["data_vigenza"].replace("Z", "+00:00")),
                url=data.get("url", ""),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Act not found: {tipo}/{anno}/{numero}")
                return None
            logger.error(f"HTTP error retrieving act: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving act {tipo}/{anno}/{numero}: {e}")
            return None

    async def get_multivigenza(
        self, urn: str, data_vigenza: str | None = None
    ) -> MultivigenzaResult | None:
        """
        Retrieve version history of a normative act.

        Args:
            urn: URN of the act
            data_vigenza: Optional ISO date string for point-in-time text

        Returns:
            MultivigenzaResult with all versions, or None if not found
        """
        try:
            path = f"/api/multivigenza/{urn}"
            params = {}
            if data_vigenza:
                params["data"] = data_vigenza

            response = await self._request_with_retry(
                "GET", path, params=params if params else None
            )

            data = response.json()
            versioni = [
                Versione(
                    data_inizio=datetime.fromisoformat(v["data_inizio"].replace("Z", "+00:00")),
                    data_fine=datetime.fromisoformat(v["data_fine"].replace("Z", "+00:00"))
                    if v.get("data_fine")
                    else None,
                    testo=v.get("testo", ""),
                    modifiche=v.get("modifiche", []),
                )
                for v in data.get("versioni", [])
            ]

            return MultivigenzaResult(urn=urn, versioni=versioni)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"URN not found: {urn}")
                return None
            logger.error(f"HTTP error retrieving multivigenza: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving multivigenza for {urn}: {e}")
            return None

    async def download_bulk_xml(
        self, tipo_atto: str = "legge", anno_from: int = 2020, anno_to: int = 2026
    ) -> list[NormativeActXML]:
        """
        Download bulk XML exports in XML:NIR format.

        Args:
            tipo_atto: Act type to download
            anno_from: Start year (inclusive)
            anno_to: End year (inclusive)

        Returns:
            List of parsed NormativeActXML objects
        """
        results = []

        try:
            for year in range(anno_from, anno_to + 1):
                try:
                    params = {"tipo": tipo_atto, "anno": year, "format": "xml"}

                    response = await self._request_with_retry("GET", "/api/bulk", params=params)

                    # Parse XML content. Source is the official Normattiva
                    # opendata API over HTTPS (trusted government endpoint).
                    root = ET.fromstring(response.content)  # nosec B314
                    acts = root.findall(".//atto")

                    for act in acts:
                        urn = act.get("urn", "")
                        articoli = self._parse_xml_articles(act)

                        results.append(
                            NormativeActXML(
                                urn=urn,
                                xml_content=ET.tostring(act, encoding="unicode"),
                                parsed_articles=articoli,
                            )
                        )
                except Exception as e:
                    logger.warning(f"Error processing {tipo_atto} {year}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error downloading bulk XML: {e}")

        return results

    async def validate_urn(self, urn: str) -> URNValidationResult:
        """
        Validate that a URN exists in Normattiva.

        Args:
            urn: URN to validate

        Returns:
            URNValidationResult with validation details
        """
        try:
            params = {"urn": urn}
            response = await self._request_with_retry("GET", "/api/validate", params=params)

            data = response.json()

            return URNValidationResult(
                urn=urn,
                exists=data.get("exists", False),
                is_in_force=data.get("is_in_force", False),
                tipo=data.get("tipo"),
                anno=data.get("anno"),
                numero=data.get("numero"),
                titolo=data.get("titolo"),
                url=data.get("url"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return URNValidationResult(urn=urn, exists=False, is_in_force=False)
            logger.error(f"HTTP error validating URN: {e}")
            return URNValidationResult(urn=urn, exists=False, is_in_force=False)
        except Exception as e:
            logger.error(f"Error validating URN {urn}: {e}")
            return URNValidationResult(urn=urn, exists=False, is_in_force=False)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _parse_articles(self, articles_data: list[dict]) -> list[Articolo]:
        """Parse articles from API response."""
        articoli = []
        for art in articles_data:
            articoli.append(
                Articolo(
                    numero=art.get("numero", ""),
                    rubrica=art.get("rubrica"),
                    testo=art.get("testo", ""),
                    commi=art.get("commi", []),
                )
            )
        return articoli

    def _parse_xml_articles(self, act_element: ET.Element) -> list[Articolo]:
        """Parse articles from XML:NIR format."""
        articoli = []

        for articolo in act_element.findall(".//articolo"):
            numero = articolo.get("numero", "")
            rubrica_elem = articolo.find("rubrica")
            rubrica = rubrica_elem.text if rubrica_elem is not None else None

            # Extract article text
            testo_parts = []
            for elem in articolo.iter():
                if elem.text:
                    testo_parts.append(elem.text.strip())
            testo = " ".join(testo_parts)

            # Extract commi (paragraphs)
            commi = []
            for comma in articolo.findall(".//comma"):
                comma_text = "".join(comma.itertext()).strip()
                if comma_text:
                    commi.append(comma_text)

            articoli.append(Articolo(numero=numero, rubrica=rubrica, testo=testo, commi=commi))

        return articoli
