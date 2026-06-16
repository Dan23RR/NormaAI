"""
EUR-Lex SPARQL Client — Core crawler for EU regulatory intelligence.

Connects to the EUR-Lex CELLAR SPARQL endpoint to:
1. Fetch metadata for known EU regulations (CELEX-based)
2. Detect amendments and modifications to tracked legislation
3. Download full text (HTML) for NLP processing
4. Monitor for new publications via date-range queries

Endpoint: https://publications.europa.eu/webapi/rdf/sparql
Ontology: CDM (Common Data Model) — FRBR-compliant OWL
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from SPARQLWrapper import JSON, SPARQLWrapper

logger = logging.getLogger(__name__)

# CDM Ontology prefixes
SPARQL_PREFIXES = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

# Resource type URIs
RESOURCE_TYPES = {
    "directive": "http://publications.europa.eu/resource/authority/resource-type/DIR",
    "regulation": "http://publications.europa.eu/resource/authority/resource-type/REG",
    "delegated_dir": "http://publications.europa.eu/resource/authority/resource-type/DIR_DEL",
    "delegated_reg": "http://publications.europa.eu/resource/authority/resource-type/REG_DEL",
    "implementing_dir": "http://publications.europa.eu/resource/authority/resource-type/DIR_IMPL",
    "implementing_reg": "http://publications.europa.eu/resource/authority/resource-type/REG_IMPL",
}

# ─── Full-text source: CELLAR, not the legal-content web frontend ───
# eur-lex.europa.eu/legal-content/.../HTML/ IP-walls datacenter clients:
# it returns HTTP 202 + an empty body even with a browser User-Agent
# (verified from the production server, 2026-06-15). The Publications
# Office CELLAR endpoint serves the same official documents from the host
# that already answers our SPARQL queries, with no such wall.
# Content negotiation: the document body is the XHTML manifestation —
# request it with `Accept: application/xhtml+xml` (text/html 404s) and the
# language as an ISO 639-3 code via Accept-Language.
CELLAR_CELEX_BASE = "http://publications.europa.eu/resource/celex"

# CELLAR language negotiation uses ISO 639-3 codes, not the 2-letter form.
LANG_ISO639_3 = {
    "EN": "eng",
    "IT": "ita",
    "FR": "fra",
    "DE": "deu",
    "ES": "spa",
    "NL": "nld",
    "PL": "pol",
    "PT": "por",
    "EL": "ell",
    "RO": "ron",
}

# Core EU frameworks we track — CELEX numbers
CORE_FRAMEWORKS: dict[str, dict[str, str]] = {
    "CSRD": {
        "32022L2464": "Corporate Sustainability Reporting Directive",
        "32023R2772": "ESRS Set 1 (Delegated Regulation)",
        "32025L0794": "Stop-the-Clock Directive (Omnibus)",
        "32026L0470": "Omnibus I Directive (substantive CSRD/CSDDD amendments)",
    },
    "CSDDD": {
        "32024L1760": "Corporate Sustainability Due Diligence Directive",
        "32026L0470": "Omnibus I Directive (substantive CSRD/CSDDD amendments)",
    },
    "AI_ACT": {
        "32024R1689": "Artificial Intelligence Act",
    },
    "DORA": {
        "32022R2554": "Digital Operational Resilience Act",
    },
    "NIS2": {
        "32022L2555": "NIS 2 Directive",
    },
    "TAXONOMY": {
        "32020R0852": "EU Taxonomy Regulation",
    },
    "GDPR": {
        "32016R0679": "General Data Protection Regulation",
    },
    # Cyber Resilience Act — vulnerability/incident reporting applies from
    # 2026-09-11, full application 2027-12-11 (see ADR-004).
    "CRA": {
        "32024R2847": "Cyber Resilience Act",
        "32025R2392": "CRA Implementing Regulation (important/critical product categories)",
    },
}


@dataclass
class RegulationMetadata:
    """Parsed metadata for an EU regulation."""

    celex: str
    title: str = ""
    framework: str = ""
    doc_type: str = ""
    date_document: str | None = None
    is_in_force: bool | None = None
    amendments: list[str] = field(default_factory=list)
    full_text_url: str = ""


@dataclass
class AmendmentInfo:
    """Information about an amendment to a tracked regulation."""

    original_celex: str
    amending_celex: str
    amending_title: str = ""
    amendment_date: str | None = None


class EurLexClient:
    """
    Client for EUR-Lex CELLAR SPARQL endpoint.

    Handles:
    - SPARQL queries with retry logic and rate limiting
    - Full text download via EUR-Lex REST API
    - Amendment detection for tracked regulations
    """

    def __init__(
        self,
        endpoint: str = "https://publications.europa.eu/webapi/rdf/sparql",
        request_delay: float = 1.5,  # seconds between requests
        max_retries: int = 3,
    ):
        self.endpoint = endpoint
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._sparql = SPARQLWrapper(endpoint)
        self._sparql.setReturnFormat(JSON)
        self._http = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "NormaAI/0.1 (EU Compliance Monitor)"},
        )
        self._last_request_time = 0.0

    @staticmethod
    def _sanitize_celex(celex: str) -> str:
        """Sanitize CELEX number to prevent SPARQL injection.

        CELEX numbers are alphanumeric identifiers like '32022L2464'.
        Only allow alphanumeric characters to prevent injection.
        """
        import re

        sanitized = re.sub(r"[^a-zA-Z0-9]", "", celex)
        if len(sanitized) < 5 or len(sanitized) > 20:
            raise ValueError(f"Invalid CELEX number format: '{celex}'")
        return sanitized

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def _execute_sparql(self, query: str) -> dict:
        """Execute SPARQL query with retry and rate limiting."""
        full_query = SPARQL_PREFIXES + query

        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                self._sparql.setQuery(full_query)
                results = self._sparql.query().convert()
                return results
            except Exception as e:
                wait_time = (2**attempt) * 2  # Exponential backoff: 2, 4, 8 seconds
                logger.warning(
                    f"SPARQL query failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    logger.error(f"SPARQL query failed after {self.max_retries} attempts: {e}")
                    raise

        return {"results": {"bindings": []}}

    # ─── Core Queries ───────────────────────────────────────────

    @staticmethod
    def _build_sparql_query(template: str, params: dict[str, str]) -> str:
        """Build SPARQL query from template with sanitized parameter substitution.

        All string parameters are sanitized to prevent SPARQL injection:
        - CELEX numbers: alphanumeric only (via _sanitize_celex)
        - Dates: ISO format validated
        - Language codes: 2 lowercase letters only

        Parameters are substituted as SPARQL string literals using double-brace
        syntax: {{param_name}} in template, replaced with sanitized values.
        """
        import re as _re

        for key, value in params.items():
            placeholder = "{{" + key + "}}"
            # Additional defense: strip any SPARQL-special characters
            safe_value = _re.sub(r'["\\\n\r{}]', "", str(value))
            template = template.replace(placeholder, safe_value)
        return template

    def fetch_regulation_metadata(self, celex: str) -> RegulationMetadata:
        """Fetch metadata for a single regulation by CELEX number."""
        celex = self._sanitize_celex(celex)
        query = self._build_sparql_query(
            """
        SELECT DISTINCT ?title ?date ?inForce WHERE {{
            ?work cdm:resource_legal_id_celex "{{celex}}" .
            OPTIONAL {{ ?work cdm:work_title ?title . FILTER(LANG(?title) = "en") }}
            OPTIONAL {{ ?work cdm:work_date_document ?date }}
            OPTIONAL {{ ?work cdm:resource_legal_in-force ?inForce }}
        }}
        LIMIT 5
        """,
            {"celex": celex},
        )
        results = self._execute_sparql(query)
        bindings = results.get("results", {}).get("bindings", [])

        meta = RegulationMetadata(celex=celex)
        if bindings:
            b = bindings[0]
            meta.title = b.get("title", {}).get("value", "")
            meta.date_document = b.get("date", {}).get("value", "")
            in_force_val = b.get("inForce", {}).get("value", "")
            meta.is_in_force = in_force_val.lower() == "true" if in_force_val else None

        # Determine framework from our known CELEX map
        for framework, celex_map in CORE_FRAMEWORKS.items():
            if celex in celex_map:
                meta.framework = framework
                if not meta.title:
                    meta.title = celex_map[celex]
                break

        # Determine doc_type from CELEX pattern
        meta.doc_type = self._celex_to_doc_type(celex)

        return meta

    def fetch_amendments(self, celex: str) -> list[AmendmentInfo]:
        """Find all documents that amend a given regulation."""
        celex = self._sanitize_celex(celex)
        query = self._build_sparql_query(
            """
        SELECT DISTINCT ?amendingCelex ?amendingTitle ?amendDate WHERE {{
            ?originalWork cdm:resource_legal_id_celex "{{celex}}" .
            ?amendingWork cdm:work_amends ?originalWork .
            OPTIONAL {{ ?amendingWork cdm:resource_legal_id_celex ?amendingCelex }}
            OPTIONAL {{ ?amendingWork cdm:work_title ?amendingTitle . FILTER(LANG(?amendingTitle) = "en") }}
            OPTIONAL {{ ?amendingWork cdm:work_date_document ?amendDate }}
        }}
        ORDER BY DESC(?amendDate)
        LIMIT 50
        """,
            {"celex": celex},
        )
        results = self._execute_sparql(query)
        bindings = results.get("results", {}).get("bindings", [])

        amendments = []
        for b in bindings:
            amend_celex = b.get("amendingCelex", {}).get("value", "")
            if amend_celex:
                amendments.append(
                    AmendmentInfo(
                        original_celex=celex,
                        amending_celex=amend_celex,
                        amending_title=b.get("amendingTitle", {}).get("value", ""),
                        amendment_date=b.get("amendDate", {}).get("value", ""),
                    )
                )

        return amendments

    def fetch_recent_legislation(self, days_back: int = 7) -> list[RegulationMetadata]:
        """Find recently published EU legislation (last N days)."""
        import re as _re

        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        # Validate date format strictly
        if not _re.match(r"^\d{4}-\d{2}-\d{2}$", date_from):
            raise ValueError(f"Invalid date format: {date_from}")
        query = self._build_sparql_query(
            """
        SELECT DISTINCT ?celex ?title ?date WHERE {{
            ?work cdm:resource_legal_id_celex ?celex .
            ?work cdm:work_title ?title .
            ?work cdm:work_date_document ?date .
            ?work cdm:work_has_resource-type ?type .
            FILTER(?type IN (
                <{dir}>,
                <{reg}>,
                <{del_dir}>,
                <{del_reg}>,
                <{impl_dir}>,
                <{impl_reg}>
            ))
            FILTER(?date >= "{{date_from}}"^^xsd:date)
            FILTER(LANG(?title) = "en")
            FILTER NOT EXISTS {{
                ?work cdm:do_not_index "true"^^xsd:boolean
            }}
        }}
        ORDER BY DESC(?date)
        LIMIT 100
        """.format(
                dir=RESOURCE_TYPES["directive"],
                reg=RESOURCE_TYPES["regulation"],
                del_dir=RESOURCE_TYPES["delegated_dir"],
                del_reg=RESOURCE_TYPES["delegated_reg"],
                impl_dir=RESOURCE_TYPES["implementing_dir"],
                impl_reg=RESOURCE_TYPES["implementing_reg"],
            ),
            {"date_from": date_from},
        )
        results = self._execute_sparql(query)
        bindings = results.get("results", {}).get("bindings", [])

        regulations = []
        for b in bindings:
            celex = b.get("celex", {}).get("value", "")
            if celex:
                regulations.append(
                    RegulationMetadata(
                        celex=celex,
                        title=b.get("title", {}).get("value", ""),
                        date_document=b.get("date", {}).get("value", ""),
                        doc_type=self._celex_to_doc_type(celex),
                    )
                )

        return regulations

    # ─── Full Text Download ─────────────────────────────────────

    def download_full_text_html(self, celex: str, lang: str = "EN") -> str | None:
        """
        Download a regulation's full text as XHTML from CELLAR.

        Fetches the official XHTML manifestation from the Publications Office
        CELLAR endpoint (publications.europa.eu), NOT the
        eur-lex.europa.eu/legal-content frontend — the latter IP-walls
        datacenter clients (HTTP 202 + empty body). CELLAR is the same host
        that answers our SPARQL metadata queries, so it is reachable from the
        production server.

        Content negotiation: `Accept: application/xhtml+xml` returns the
        document body (text/html 404s); the language is sent as an ISO 639-3
        code. Returns the XHTML string, or None if the document has no text
        manifestation in this language (404/406) or all retries are exhausted.
        """
        import re as _re

        celex = self._sanitize_celex(celex)
        lang_key = _re.sub(r"[^A-Za-z]", "", lang).upper()[:2]
        accept_language = LANG_ISO639_3.get(lang_key, "eng")
        url = f"{CELLAR_CELEX_BASE}/{celex}"
        headers = {
            "Accept": "application/xhtml+xml",
            "Accept-Language": accept_language,
        }

        for attempt in range(self.max_retries):
            wait = 2**attempt
            try:
                self._rate_limit()
                # The client follows the CELLAR 303 content-negotiation chain;
                # allow a longer read for large consolidated acts (~1 MB).
                response = self._http.get(url, headers=headers, timeout=60.0)
                status = response.status_code

                if status == 200 and response.text:
                    logger.info(
                        f"Downloaded full text for {celex} "
                        f"({len(response.text)} chars) via CELLAR"
                    )
                    return response.text

                if status in (404, 406):
                    # No XHTML manifestation for this CELEX/language — deterministic,
                    # so retrying will not help.
                    logger.warning(
                        f"No XHTML manifestation for {celex} (HTTP {status}) via CELLAR"
                    )
                    return None

                # Transient (202 still rendering, 429/503 throttling, empty 200):
                # honor Retry-After when present, otherwise exponential backoff.
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = float(retry_after)
                logger.warning(
                    f"Transient HTTP {status} for {celex} via CELLAR "
                    f"(attempt {attempt + 1}/{self.max_retries}); retrying in {wait}s"
                )
            except Exception as e:
                logger.warning(
                    f"Download failed for {celex} (attempt {attempt + 1}/{self.max_retries}): {e}"
                )

            if attempt < self.max_retries - 1:
                time.sleep(wait)

        logger.error(f"Failed to download full text for {celex} after {self.max_retries} attempts")
        return None

    # ─── Full Crawl ─────────────────────────────────────────────

    def crawl_all_core_frameworks(self) -> list[RegulationMetadata]:
        """
        Crawl metadata + full text for all core framework regulations.
        This is the initial seed crawl.
        """
        all_regulations = []

        for framework, celex_map in CORE_FRAMEWORKS.items():
            for celex, description in celex_map.items():
                logger.info(f"Crawling {framework}/{celex}: {description}")

                # Fetch metadata via SPARQL
                meta = self.fetch_regulation_metadata(celex)
                meta.framework = framework

                # Fetch amendments
                amendments = self.fetch_amendments(celex)
                meta.amendments = [a.amending_celex for a in amendments]
                if amendments:
                    logger.info(f"  Found {len(amendments)} amendments for {celex}")

                # Build full text URL
                meta.full_text_url = (
                    f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
                )

                all_regulations.append(meta)

        logger.info(f"Crawl complete: {len(all_regulations)} regulations processed")
        return all_regulations

    def check_for_new_amendments(self, tracked_celex_numbers: list[str]) -> list[AmendmentInfo]:
        """
        Check all tracked regulations for new amendments.
        Called by the periodic crawl job (every 6 hours).
        """
        all_new_amendments = []

        for celex in tracked_celex_numbers:
            amendments = self.fetch_amendments(celex)
            if amendments:
                all_new_amendments.extend(amendments)
                logger.info(f"Found {len(amendments)} amendments for {celex}")

        return all_new_amendments

    # ─── Utils ──────────────────────────────────────────────────

    @staticmethod
    def _celex_to_doc_type(celex: str) -> str:
        """Infer document type from CELEX number pattern.
        Format: {sector}{year}{type}{number} — e.g., 3|2022|L|2464
        Sector=1 char, Year=4 chars, Type=1 char at index 5.
        """
        if len(celex) < 7:
            return "unknown"
        type_char = celex[5]
        return {
            "L": "directive",
            "R": "regulation",
            "D": "decision",
            "O": "other",
        }.get(type_char, "unknown")

    def close(self) -> None:
        """Close HTTP client."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
