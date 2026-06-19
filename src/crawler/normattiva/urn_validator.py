"""
URN Validation and Normalization

Handles Italian legislative URN format validation, normalization, parsing,
and extraction from free-form text. Supports Italian and EU legislative references.

Italian URN format: urn:nir:stato:legge:2024-01-15;3
EU URN format: urn:nir:unione.europea:regolamento:2024;1689
"""

import logging
import re
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from .client import NormattivaOpenDataClient, URNValidationResult

if __name__ != "__main__":
    # Import client only when used as module to avoid circular imports
    pass


logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Data Models
# ============================================================================


class URNComponents(BaseModel):
    """Parsed components of an Italian legislative URN."""

    autorita: str  # 'stato' or 'unione.europea'
    tipo: str  # legge, decreto.legislativo, regolamento, etc.
    data: str  # ISO date or year
    numero: str  # Act number
    articolo: str | None = None  # Optional article reference

    class Config:
        json_schema_extra = {
            "example": {
                "autorita": "stato",
                "tipo": "legge",
                "data": "2024",
                "numero": "123",
                "articolo": None,
            }
        }


# ============================================================================
# URN Validator
# ============================================================================


class URNValidator:
    """
    Validates, normalizes, and parses Italian legislative URNs.

    Supports all Italian act types and EU directives/regulations.
    Can extract URNs from free-form text and validate against Normattiva API.
    """

    # Italian act types and their aliases
    ITALIAN_ACT_TYPES = {
        "legge": ["legge", "l."],
        "decreto.legislativo": [
            "decreto.legislativo",
            "d.lgs.",
            "dlgs",
            "lgs.",
            "lgs",
            "legislativo",
        ],
        "decreto.legge": ["decreto.legge", "d.l.", "dl"],
        "decreto.presidente.repubblica": ["decreto.presidente.repubblica", "d.p.r.", "dpr"],
        "decreto.presidente.consiglio.ministri": [
            "decreto.presidente.consiglio.ministri",
            "d.p.c.m.",
            "dpcm",
        ],
        "regolamento": ["regolamento", "reg."],
        "direttiva": ["direttiva", "dir."],
    }

    # EU legislative types
    EU_ACT_TYPES = {
        "regolamento.ue": ["regolamento.ue", "regolamento ue", "reg. ue", "ue"],
        "direttiva.ue": ["direttiva.ue", "direttiva ue", "dir. ue"],
    }

    # Combined type patterns for regex
    ALL_ACT_TYPES = {**ITALIAN_ACT_TYPES, **EU_ACT_TYPES}

    # URN format regex pattern
    URN_PATTERN = re.compile(
        r"urn:nir:(?P<autorita>stato|unione\.europea):"
        r"(?P<tipo>[a-z\.]+):"
        r"(?P<data>\d{4}(?:-\d{2}-\d{2})?);(?P<numero>\d+)"
        r"(?:,(?P<articolo>\d+))?"
    )

    # Common Italian citation patterns
    CITATION_PATTERNS = [
        # "legge n. 123 del 2024" or "legge n. 123/2024" or "l. 123/2024"
        re.compile(
            r"(?P<tipo>legge|l\.)\s+(?:n\.?\s*)?(?P<numero>\d+)\s*(?:del|/)\s*(?P<anno>\d{4})",
            re.IGNORECASE,
        ),
        # "d.lgs. 138/2023" or "decreto legislativo n. 138 del 2023"
        re.compile(
            r"(?:decreto\.?\s*)?(?P<tipo>legislativo|lgs\.?)\s+n\.?\s*(?P<numero>\d+)\s*(?:del|/)\s*(?P<anno>\d{4})",
            re.IGNORECASE,
        ),
        # "D.L. 15 gennaio 2024, n. 3" or "decreto legge n. 3 del 15 gennaio 2024"
        re.compile(
            r"(?:decreto\.?\s*)?(?P<tipo>legge|l\.?)\s+(?:n\.?\s*)?(?P<numero>\d+)\s+"
            r"(?:del\s+)?(?P<giorno>\d{1,2})\s+(?P<mese>\w+)\s+(?P<anno>\d{4})",
            re.IGNORECASE,
        ),
        # "D.L. 15 gennaio 2024, n. 3" - alternative format
        re.compile(
            r"(?P<tipo>d\.l\.|d\.lgs\.|decreto\.?\s*(?:legge|legislativo))\s+"
            r"(?P<giorno>\d{1,2})\s+(?P<mese>\w+)\s+(?P<anno>\d{4}),?\s+n\.?\s*(?P<numero>\d+)",
            re.IGNORECASE,
        ),
        # "art. 5, comma 2, legge n. 123/2024"
        re.compile(
            r"art\.?\s+\d+(?:,\s*comma\s+\d+)?.*?(?P<tipo>legge|l\.)\s+n\.?\s*(?P<numero>\d+)(?:del|/)\s*(?P<anno>\d{4})",
            re.IGNORECASE,
        ),
        # "Regolamento (UE) 2024/1689" - capture tipo + an `eu` marker so
        # _build_urn_from_match emits an EU URN (previously dropped: no tipo group).
        re.compile(
            r"(?P<tipo>regolamento)\s*\((?P<eu>ue|eu)\)\s+(?P<anno>\d{4})/(?P<numero>\d+)",
            re.IGNORECASE,
        ),
        # "Direttiva (UE) 2024/1689"
        re.compile(
            r"(?P<tipo>direttiva)\s*\((?P<eu>ue|eu)\)\s+(?P<anno>\d{4})/(?P<numero>\d+)",
            re.IGNORECASE,
        ),
    ]

    # Month mapping for Italian dates
    ITALIAN_MONTHS = {
        "gennaio": 1,
        "febbraio": 2,
        "marzo": 3,
        "aprile": 4,
        "maggio": 5,
        "giugno": 6,
        "luglio": 7,
        "agosto": 8,
        "settembre": 9,
        "ottobre": 10,
        "novembre": 11,
        "dicembre": 12,
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    @staticmethod
    def validate_format(urn: str) -> bool:
        """
        Validate URN format using regex.

        Args:
            urn: URN string to validate

        Returns:
            True if URN matches expected format, False otherwise
        """
        return URNValidator.URN_PATTERN.match(urn.strip()) is not None

    @staticmethod
    def normalize(urn: str) -> str:
        """
        Normalize a URN string.

        Applies: lowercase, strip whitespace, normalize common variations.

        Args:
            urn: URN string to normalize

        Returns:
            Normalized URN
        """
        urn = urn.strip().lower()

        # Replace common variations
        urn = urn.replace("d.l.", "decreto.legge:")
        urn = urn.replace("d.lgs.", "decreto.legislativo:")
        urn = urn.replace("d.p.r.", "decreto.presidente.repubblica:")
        urn = urn.replace("d.p.c.m.", "decreto.presidente.consiglio.ministri:")

        # Remove extra spaces
        urn = re.sub(r"\s+", " ", urn)

        return urn

    @staticmethod
    def parse(urn: str) -> URNComponents | None:
        """
        Parse URN into structured components.

        Args:
            urn: URN string

        Returns:
            URNComponents if valid, None otherwise
        """
        match = URNValidator.URN_PATTERN.match(urn.strip())
        if not match:
            return None

        return URNComponents(
            autorita=match.group("autorita"),
            tipo=match.group("tipo"),
            data=match.group("data"),
            numero=match.group("numero"),
            articolo=match.group("articolo"),
        )

    @staticmethod
    def from_citation(text: str) -> list[str]:
        """
        Extract URNs from free-form text citation.

        Supports multiple Italian legislative citation formats:
        - "legge n. 123 del 2024"
        - "d.lgs. 138/2023"
        - "D.L. 15 gennaio 2024, n. 3"
        - "art. 5, comma 2, legge n. 123/2024"
        - "Regolamento (UE) 2024/1689"

        Args:
            text: Text containing legislative citations

        Returns:
            List of extracted URNs (or potential URNs that can be built)
        """
        extracted_urns = []

        for pattern in URNValidator.CITATION_PATTERNS:
            matches = pattern.finditer(text)

            for match in matches:
                groups = match.groupdict()
                urn = URNValidator._build_urn_from_match(groups)

                if urn and urn not in extracted_urns:
                    extracted_urns.append(urn)

        return extracted_urns

    @staticmethod
    def _build_urn_from_match(groups: dict) -> str | None:
        """Build URN from regex match groups."""
        tipo = groups.get("tipo", "").lower()
        numero = groups.get("numero", "")
        anno = groups.get("anno", "")

        if not (tipo and numero and anno):
            return None

        # Determine authority and normalize the act type. EU citations carry an
        # `eu` group (or "ue"/"eu" inside tipo); Italian ones go through the alias
        # table. The two branches are mutually exclusive, so the Italian alias
        # loop can no longer clobber the ".ue" suffix (the old bug where EU types
        # fell through to "regolamento" without the EU authority).
        is_eu = bool(groups.get("eu")) or "ue" in tipo or "eu" in tipo
        if is_eu:
            autorita = "unione.europea"
            urn_tipo = "direttiva.ue" if "direttiva" in tipo else "regolamento.ue"
        else:
            autorita = "stato"
            urn_tipo = tipo
            for full_type, aliases in URNValidator.ITALIAN_ACT_TYPES.items():
                if tipo in aliases:
                    urn_tipo = full_type
                    break

        # Parse date if we have day and month
        if groups.get("giorno") and groups.get("mese"):
            try:
                mese_num = URNValidator.ITALIAN_MONTHS.get(groups["mese"].lower(), None)
                data = f"{anno}-{mese_num:02d}-{int(groups['giorno']):02d}" if mese_num else anno
            except (ValueError, KeyError):
                data = anno
        else:
            data = anno

        return f"urn:nir:{autorita}:{urn_tipo}:{data};{numero}"

    @staticmethod
    def build_url(urn: str) -> str:
        """
        Build Normattiva web URL from URN.

        Args:
            urn: URN string

        Returns:
            Normattiva URL

        Example:
            urn:nir:stato:legge:2024;123 ->
            https://www.normattiva.it/atto/stato/legge/2024-01-15/123
        """
        components = URNValidator.parse(urn)
        if not components:
            return ""

        # Extract year from data (might be full date)
        data = components.data
        if "-" in data:
            data = data.split("-")[0]  # Get just year if full date provided

        url = (
            f"https://www.normattiva.it/atto/"
            f"{components.autorita}/"
            f"{components.tipo}/"
            f"{data}/"
            f"{components.numero}"
        )

        if components.articolo:
            url += f"#{components.articolo}"

        return url

    @staticmethod
    async def verify_remote(
        urn: str, client: "NormattivaOpenDataClient"
    ) -> Optional["URNValidationResult"]:
        """
        Verify URN validity against Normattiva API.

        Args:
            urn: URN to verify
            client: NormattivaOpenDataClient instance

        Returns:
            URNValidationResult from API, None on error
        """
        try:
            result = await client.validate_urn(urn)
            return result
        except Exception as e:
            logger.error(f"Error verifying URN {urn}: {e}")
            return None

    @staticmethod
    def extract_and_validate(text: str) -> dict[str, list[str]]:
        """
        Extract URNs from text and separate valid from invalid.

        Args:
            text: Text to search for URNs

        Returns:
            Dict with 'valid' and 'invalid' URN lists
        """
        urns = URNValidator.from_citation(text)

        valid = []
        invalid = []

        for urn in urns:
            if URNValidator.validate_format(urn):
                valid.append(urn)
            else:
                invalid.append(urn)

        return {"valid": valid, "invalid": invalid}

    @staticmethod
    def get_citation_format(urn: str) -> str | None:
        """
        Generate human-readable citation format from URN.

        Args:
            urn: URN string

        Returns:
            Formatted citation string, or None if invalid URN
        """
        components = URNValidator.parse(urn)
        if not components:
            return None

        # Extract year (first 4 chars of data field)
        anno = components.data[:4]

        tipo_label = components.tipo.replace(".", " ").title()

        # Handle EU types specially
        if "ue" in components.tipo.lower():
            tipo_label = f"{tipo_label} (UE)"

        citation = f"{tipo_label} n. {components.numero} del {anno}"

        if components.articolo:
            citation += f", art. {components.articolo}"

        return citation
