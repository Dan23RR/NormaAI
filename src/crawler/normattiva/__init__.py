"""
Normattiva Open Data crawler module.

Provides access to Italian legislative documents, decrees, regulations,
and EU directives through the Normattiva Open Data API.
"""

from .client import (
    Articolo,
    MultivigenzaResult,
    NormativeActSummary,
    NormativeActXML,
    NormativeText,
    NormattivaOpenDataClient,
    SearchResult,
    URNValidationResult,
    Versione,
)
from .urn_validator import URNComponents, URNValidator

__all__ = [
    "NormattivaOpenDataClient",
    "URNValidator",
    "Articolo",
    "NormativeActSummary",
    "SearchResult",
    "NormativeText",
    "MultivigenzaResult",
    "Versione",
    "NormativeActXML",
    "URNValidationResult",
    "URNComponents",
]
