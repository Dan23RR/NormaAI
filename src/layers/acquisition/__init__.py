"""
Acquisition Layer — Regulatory data crawling and indexing.

Schedules periodic acquisition from EUR-Lex and Normattiva.
"""

from src.layers.acquisition.scheduler import AcquisitionScheduler

__all__ = [
    "AcquisitionScheduler",
]
