"""
NLP Layer - Text processing, chunking, embedding, and retrieval.

Provides structured prefix building, hybrid retrieval, and semantic enrichment.
"""

from src.layers.nlp.prefixes import StructuredPrefixBuilder
from src.layers.nlp.retrieval import RetrievalResult, RetrievalService, RetrievedChunk

__all__ = [
    "StructuredPrefixBuilder",
    "RetrievalService",
    "RetrievalResult",
    "RetrievedChunk",
]
