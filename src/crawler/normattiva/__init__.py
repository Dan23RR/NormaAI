"""
Italian legislative URNs: validation, normalization, parsing and extraction
from free text (urn_validator.URNValidator).

The older Normattiva Open Data client that lived here called endpoints that
answer HTTP 409 and was removed; Italian texts are read by the document check
(src/document_check/normattiva.py).
"""

from .urn_validator import URNComponents, URNValidator

__all__ = [
    "URNValidator",
    "URNComponents",
]
