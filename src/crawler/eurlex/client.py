"""
EUR-Lex SPARQL Client - Core crawler for EU regulatory intelligence.

Connects to the EUR-Lex CELLAR SPARQL endpoint to:
1. Fetch metadata for known EU regulations (CELEX-based)
2. Detect amendments and modifications to tracked legislation
3. Download full text (HTML) for NLP processing
4. Monitor for new publications via date-range queries

Endpoint: https://publications.europa.eu/webapi/rdf/sparql
Ontology: CDM (Common Data Model) - FRBR-compliant OWL
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from SPARQLWrapper import JSON, SPARQLWrapper

from src.crawler.eurlex import celex as celex_utils

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
# Content negotiation: the document body is the XHTML manifestation -
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

# ─── Tracked act registry ───────────────────────────────────────────
# One entry per act we seed. ``CORE_FRAMEWORKS`` (framework -> {celex: title})
# is DERIVED from this tuple for backward compatibility: every existing caller
# (CoVe trusted set, scheduler, data router, pipeline.update) keeps working.
#
# ``eli_type`` is the ELI resource type (dir / reg / reg_del / reg_impl): CELEX
# alone cannot tell a delegated regulation from a basic one, and the chunker
# needs it to build a resolvable ``http://data.europa.eu/eli/...`` URI.
# ``consolidated=True`` means "prefer the latest CELLAR consolidated text when
# one exists" (basic acts that get amended); amending acts are never
# consolidated themselves, so the lookup is skipped for them.
FRAMEWORK_ORDER: tuple[str, ...] = (
    "CSRD",
    "CSDDD",
    "AI_ACT",
    "DORA",
    "NIS2",
    "TAXONOMY",
    "GDPR",
    "CRA",
)


@dataclass(frozen=True)
class TrackedAct:
    """A legal act in the seed registry."""

    celex: str
    framework: str
    title: str
    eli_type: str = "reg"  # dir | reg | dec | dir_del | dir_impl | reg_del | reg_impl
    kind: str = "basic"  # basic | amending | delegated | implementing
    amends: tuple[str, ...] = ()
    frameworks: tuple[str, ...] = ()  # additional frameworks the act is listed under
    consolidated: bool = True  # prefer the latest consolidated text when CELLAR has one

    @property
    def all_frameworks(self) -> tuple[str, ...]:
        return (self.framework, *self.frameworks)


TRACKED_ACTS: tuple[TrackedAct, ...] = (
    # ── CSRD ──
    TrackedAct(
        "32022L2464",
        "CSRD",
        "Corporate Sustainability Reporting Directive",
        eli_type="dir",
    ),
    TrackedAct(
        "32023R2772",
        "CSRD",
        "ESRS Set 1 (Delegated Regulation (EU) 2023/2772 - sustainability reporting standards)",
        eli_type="reg_del",
        kind="delegated",
    ),
    TrackedAct(
        "32025L0794",
        "CSRD",
        "Stop-the-Clock Directive (Omnibus)",
        eli_type="dir",
        kind="amending",
        amends=("32022L2464", "32024L1760"),
        frameworks=("CSDDD",),
        consolidated=False,
    ),
    TrackedAct(
        "32026L0470",
        "CSRD",
        "Omnibus I Directive (substantive CSRD/CSDDD amendments)",
        eli_type="dir",
        kind="amending",
        amends=("32022L2464", "32024L1760"),
        frameworks=("CSDDD",),
        consolidated=False,
    ),
    # ── CSDDD ──
    TrackedAct(
        "32024L1760",
        "CSDDD",
        "Corporate Sustainability Due Diligence Directive",
        eli_type="dir",
    ),
    # ── AI Act ──
    TrackedAct("32024R1689", "AI_ACT", "Artificial Intelligence Act", eli_type="reg"),
    TrackedAct(
        "32026R1744",
        "AI_ACT",
        "Regulation (EU) 2026/1744 - Digital Omnibus on AI (amends the AI Act timeline)",
        eli_type="reg",
        kind="amending",
        amends=("32024R1689",),
        consolidated=False,
    ),
    # ── DORA (+ the RTS/ITS the workflow presets cite) ──
    TrackedAct("32022R2554", "DORA", "Digital Operational Resilience Act", eli_type="reg"),
    TrackedAct(
        "32024R1773",
        "DORA",
        "DORA RTS (Delegated Regulation (EU) 2024/1773) - policy on ICT services supporting "
        "critical or important functions provided by ICT third-party providers (Art. 28(10))",
        eli_type="reg_del",
        kind="delegated",
    ),
    TrackedAct(
        "32024R1774",
        "DORA",
        "DORA RTS (Delegated Regulation (EU) 2024/1774) - ICT risk management tools, methods, "
        "processes and policies; simplified ICT risk management framework (Art. 15, 16(3))",
        eli_type="reg_del",
        kind="delegated",
    ),
    TrackedAct(
        "32024R2956",
        "DORA",
        "DORA ITS (Implementing Regulation (EU) 2024/2956) - standard templates for the "
        "register of information (Art. 28(9))",
        eli_type="reg_impl",
        kind="implementing",
    ),
    # ── NIS2 ──
    TrackedAct("32022L2555", "NIS2", "NIS 2 Directive", eli_type="dir"),
    # ── Taxonomy ──
    TrackedAct("32020R0852", "TAXONOMY", "EU Taxonomy Regulation", eli_type="reg"),
    TrackedAct(
        "32023R2486",
        "TAXONOMY",
        "Taxonomy Environmental Delegated Act (Delegated Regulation (EU) 2023/2486) - technical "
        "screening criteria for the water, circular economy, pollution and biodiversity objectives",
        eli_type="reg_del",
        kind="delegated",
    ),
    # ── GDPR ──
    TrackedAct("32016R0679", "GDPR", "General Data Protection Regulation", eli_type="reg"),
    # ── CRA - vulnerability/incident reporting applies from 2026-09-11, full
    # application 2027-12-11 (see ADR-004). ──
    TrackedAct("32024R2847", "CRA", "Cyber Resilience Act", eli_type="reg"),
    TrackedAct(
        "32025R2392",
        "CRA",
        "CRA Implementing Regulation (important/critical product categories)",
        eli_type="reg_impl",
        kind="implementing",
    ),
)


def _build_core_frameworks(acts: tuple[TrackedAct, ...]) -> dict[str, dict[str, str]]:
    frameworks: dict[str, dict[str, str]] = {fw: {} for fw in FRAMEWORK_ORDER}
    for act in acts:
        for fw in act.all_frameworks:
            frameworks.setdefault(fw, {})[act.celex] = act.title
    return frameworks


# Core EU frameworks we track - framework -> {CELEX: title}. Derived from
# TRACKED_ACTS; an act listed under several frameworks (Omnibus I amends both
# CSRD and CSDDD) appears under each of them.
CORE_FRAMEWORKS: dict[str, dict[str, str]] = _build_core_frameworks(TRACKED_ACTS)

_TRACKED_BY_CELEX: dict[str, TrackedAct] = {act.celex: act for act in TRACKED_ACTS}


def get_tracked_act(celex: str) -> TrackedAct | None:
    """Registry entry for a CELEX (original or consolidated id), or None."""
    return _TRACKED_BY_CELEX.get(celex_utils.base_celex(celex))


def tracked_acts(selection: list[str] | tuple[str, ...] | None = None) -> list[TrackedAct]:
    """Unique registry acts, optionally filtered by CELEX ids and/or framework names.

    ``selection`` entries are matched case-insensitively against both the
    CELEX number and the framework key, so ``["AI_ACT", "32022L2464"]`` selects
    every AI Act entry plus the CSRD directive. Unknown entries are ignored
    (with a warning) rather than raising, so a typo in ``--acts`` cannot abort
    a seed that is otherwise fine.
    """
    if not selection:
        return list(TRACKED_ACTS)
    wanted = {str(s).strip().upper() for s in selection if str(s).strip()}
    known = {act.celex.upper() for act in TRACKED_ACTS} | {fw.upper() for fw in CORE_FRAMEWORKS}
    for unknown in sorted(wanted - known):
        logger.warning("tracked_acts: ignoring unknown act/framework selector %r", unknown)
    return [
        act
        for act in TRACKED_ACTS
        if act.celex.upper() in wanted or any(fw.upper() in wanted for fw in act.all_frameworks)
    ]


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
        # base CELEX -> latest consolidated id (or None when CELLAR has none);
        # memoised per client so a seed asks once per act, not once per language.
        self._consolidated_cache: dict[str, str | None] = {}

    @staticmethod
    def _sanitize_celex(celex: str) -> str:
        """Sanitize CELEX number to prevent SPARQL injection.

        CELEX numbers are alphanumeric identifiers like '32022L2464'; CELLAR
        consolidated ids add a hyphen and the consolidation date
        ('02022L2464-20260318'). Only alphanumerics and a single inner hyphen
        survive, so nothing that could break out of a SPARQL literal or a URL
        path segment gets through.
        """
        import re

        sanitized = re.sub(r"[^a-zA-Z0-9-]", "", celex).strip("-")
        if "-" in sanitized:
            head, _, tail = sanitized.partition("-")
            sanitized = f"{head}-{tail.replace('-', '')}"
        alnum = sanitized.replace("-", "")
        if len(alnum) < 5 or len(sanitized) > 20:
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

    # CELLAR stores CELEX ids as xsd:string-TYPED literals. A plain "..." literal
    # in the triple pattern matches nothing on the Virtuoso endpoint (verified
    # live 2026-10-23: the untyped form returned zero bindings for every tracked
    # act, so in-force flags were always "unknown" and amendments never found).
    # Every CELEX lookup below must use the typed form.
    def fetch_regulation_metadata(self, celex: str) -> RegulationMetadata:
        """Fetch metadata for a single regulation by CELEX number."""
        celex = self._sanitize_celex(celex)
        query = self._build_sparql_query(
            """
        SELECT DISTINCT ?title ?date ?inForce WHERE {{
            ?work cdm:resource_legal_id_celex "{{celex}}"^^xsd:string .
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
            # CELLAR serves the flag as "true"/"false" or "1"/"0" depending on
            # the literal datatype; accept both spellings.
            meta.is_in_force = (
                in_force_val.lower() in ("true", "1") if in_force_val.strip() else None
            )

        # Determine framework from the tracked-act registry (works for a
        # consolidated id too, via its base CELEX).
        act = get_tracked_act(celex)
        if act is not None:
            meta.framework = act.framework
            if not meta.title:
                meta.title = act.title

        # Determine doc_type from CELEX pattern
        meta.doc_type = self._celex_to_doc_type(celex_utils.base_celex(celex))

        return meta

    def fetch_latest_consolidated_celex(self, celex: str) -> str | None:
        """Latest CELLAR consolidated id for an act, or None.

        CELLAR publishes each consolidated version of ``32022L2464`` as its own
        work with CELEX ``02022L2464-YYYYMMDD``; the id suffix is the
        consolidation date, so the lexicographically greatest id is the most
        recent text. The lookup is a prefix match on ``resource_legal_id_celex``
        (verified live against the endpoint - the consolidation relation
        properties do not resolve reliably).

        Degrades gracefully: any network/endpoint failure, a malformed answer or
        an act that simply has no consolidated text all yield None (and the
        caller falls back to the original act). The answer is memoised per
        client so the seed asks once per act, not once per language.
        """
        celex = self._sanitize_celex(celex)
        base = celex_utils.base_celex(celex)
        if base in self._consolidated_cache:
            return self._consolidated_cache[base]

        prefix = celex_utils.consolidated_prefix(base)
        if prefix is None:
            self._consolidated_cache[base] = None
            return None

        query = self._build_sparql_query(
            """
        SELECT DISTINCT ?celex WHERE {{
            ?work cdm:resource_legal_id_celex ?celex .
            FILTER(STRSTARTS(STR(?celex), "{{prefix}}"))
        }}
        ORDER BY DESC(?celex)
        LIMIT 20
        """,
            {"prefix": prefix},
        )
        latest: str | None = None
        try:
            results = self._execute_sparql(query)
            bindings = results.get("results", {}).get("bindings", [])
            candidates = sorted(
                {
                    b.get("celex", {}).get("value", "").strip()
                    for b in bindings
                    if celex_utils.is_consolidated_celex(b.get("celex", {}).get("value", ""))
                }
            )
            latest = candidates[-1] if candidates else None
        except Exception as e:  # offline / endpoint down / throttled
            logger.warning(
                f"Consolidated-version lookup failed for {base}: {e}; using the original act"
            )
            return None  # not cached: a later call may succeed

        if latest:
            logger.info(f"Latest consolidated text for {base}: {latest}")
        else:
            logger.info(f"No consolidated text for {base} in CELLAR")
        self._consolidated_cache[base] = latest
        return latest

    def resolve_download_celex(self, celex: str, prefer_consolidated: bool = True) -> str:
        """The CELEX to download for an act: its latest consolidated text when
        available and wanted, else the original act."""
        if not prefer_consolidated:
            return celex
        act = get_tracked_act(celex)
        if act is not None and not act.consolidated:
            return celex
        return self.fetch_latest_consolidated_celex(celex) or celex

    def fetch_amendments(self, celex: str) -> list[AmendmentInfo]:
        """Find all documents that amend a given regulation."""
        celex = self._sanitize_celex(celex)
        query = self._build_sparql_query(
            """
        SELECT DISTINCT ?amendingCelex ?amendingTitle ?amendDate WHERE {{
            ?originalWork cdm:resource_legal_id_celex "{{celex}}"^^xsd:string .
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
        eur-lex.europa.eu/legal-content frontend - the latter IP-walls
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
                    # No XHTML manifestation for this CELEX/language - deterministic,
                    # so retrying will not help.
                    logger.warning(f"No XHTML manifestation for {celex} (HTTP {status}) via CELLAR")
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

    def crawl_all_core_frameworks(
        self,
        celex_filter: list[str] | tuple[str, ...] | None = None,
        unique: bool = False,
    ) -> list[RegulationMetadata]:
        """
        Crawl metadata for the tracked acts. This is the initial seed crawl.

        Default (no args) keeps the historical shape: one entry per
        (framework, CELEX) pair of ``CORE_FRAMEWORKS``, so an act listed under
        two frameworks is returned twice. ``unique=True`` returns each act once,
        stamped with its primary framework (what the seed wants: one download
        per act). ``celex_filter`` narrows the crawl to CELEX ids and/or
        framework names (see ``tracked_acts``).

        A SPARQL failure for one act is logged and that act still gets a
        registry-only metadata record, so an endpoint hiccup never aborts a seed.
        """
        all_regulations = []

        if unique or celex_filter:
            targets = [(act.framework, act.celex, act.title) for act in tracked_acts(celex_filter)]
        else:
            targets = [
                (framework, celex, description)
                for framework, celex_map in CORE_FRAMEWORKS.items()
                for celex, description in celex_map.items()
            ]

        for framework, celex, description in targets:
            logger.info(f"Crawling {framework}/{celex}: {description}")

            # Fetch metadata via SPARQL (non-fatal: fall back to registry data)
            try:
                meta = self.fetch_regulation_metadata(celex)
            except Exception as e:
                logger.warning(f"  metadata lookup failed for {celex}: {e}; using registry entry")
                meta = RegulationMetadata(celex=celex, title=description)
            meta.framework = framework
            if not meta.title:
                meta.title = description

            # Fetch amendments (non-fatal)
            try:
                amendments = self.fetch_amendments(celex)
            except Exception as e:
                logger.warning(f"  amendment lookup failed for {celex}: {e}")
                amendments = []
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
        Format: {sector}{year}{type}{number} - e.g., 3|2022|L|2464
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
