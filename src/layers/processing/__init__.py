"""
Processing Layer — Document extraction and routing.

Provides document processing with intelligent routing between dots.ocr and Docling.
"""

from src.layers.processing.router import ProcessingResult, ProcessorRouter

__all__ = [
    "ProcessorRouter",
    "ProcessingResult",
]
