"""Shared API schemas and enums.

Extracted to avoid FrameworkEnum duplication across routers.
"""

from enum import Enum


class FrameworkEnum(str, Enum):
    """EU regulatory frameworks tracked by NormaAI."""

    CSRD = "CSRD"
    CSDDD = "CSDDD"
    AI_ACT = "AI_ACT"
    DORA = "DORA"
    NIS2 = "NIS2"
    TAXONOMY = "TAXONOMY"
    GDPR = "GDPR"
    CRA = "CRA"
