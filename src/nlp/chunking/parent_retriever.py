"""Parent Document Retrieval for EU legal text.

Stores full articles as 'parent documents' and creates smaller sub-chunks
for precise vector search. When the LLM needs context, the full parent
article is retrieved instead of just the matching sub-chunk.

This solves a core RAG trade-off:
- Small chunks give precise search hits but lack surrounding context.
- Large chunks give good context but dilute the embedding signal.

With parent retrieval we get both: search on small chunks, respond with
the full article so the LLM can reason over complete legal provisions.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class ParentDocumentStore:
    """Manages the mapping between small search chunks and their parent articles.

    Storage back-end: the ``parent_documents`` PostgreSQL table created by
    Alembic migration 003.  If the database is not reachable (e.g. during
    tests or standalone scripting), the store falls back to an in-memory
    dictionary so the chunking logic can still be exercised.
    """

    def __init__(self) -> None:
        self._db_available: bool | None = None  # lazy-checked on first call
        self._memory_store: dict[str, dict] = {}

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _content_hash(text: str) -> str:
        """Return the SHA-256 hex digest of *text*."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _check_db(self) -> bool:
        """Try to import the async db_manager and mark DB as available."""
        if self._db_available is not None:
            return self._db_available
        try:
            from src.db.engine import db_manager  # noqa: F401

            self._db_available = db_manager._engine is not None
        except Exception:
            self._db_available = False
        if not self._db_available:
            logger.warning(
                "Database not available -- ParentDocumentStore will use "
                "in-memory storage (data will not persist across restarts)"
            )
        return self._db_available

    # ── public API ───────────────────────────────────────────────────────

    def store_parent(
        self,
        celex: str,
        framework: str,
        article_number: str | None,
        section_title: str | None,
        full_text: str,
    ) -> str:
        """Store (or upsert) a parent document and return its ID.

        The upsert key is ``(celex, article_number)``.  If a row with the
        same key already exists and the content hash differs, the row is
        updated; if the hash matches, the existing ID is returned without
        writing.

        Returns:
            The UUID (as a hex string) of the parent document.
        """
        content_hash = self._content_hash(full_text)

        if self._check_db():
            return self._store_parent_db(
                celex, framework, article_number, section_title, full_text, content_hash
            )
        return self._store_parent_memory(
            celex, framework, article_number, section_title, full_text, content_hash
        )

    def create_sub_chunks(
        self,
        parent_id: str,
        full_text: str,
        *,
        max_chunk_size: int = 500,
        celex: str = "",
        framework: str = "",
        article_number: str = "",
        section_title: str = "",
    ) -> list[dict[str, Any]]:
        """Split *full_text* into sentence-boundary sub-chunks.

        Each sub-chunk carries metadata linking it back to its parent so
        that :meth:`resolve_to_parents` can later expand search hits.

        Args:
            parent_id: UUID of the parent document.
            full_text: The complete article / section text to split.
            max_chunk_size: Target maximum characters per sub-chunk (default 500).
            celex: CELEX number for metadata.
            framework: Framework key (e.g. ``"CSRD"``).
            article_number: Article reference (e.g. ``"Art. 29"``).
            section_title: Section heading text.

        Returns:
            List of dicts, each with ``text``, ``parent_id``, ``chunk_index``,
            ``total_chunks``, and regulation metadata.
        """
        sentences = self._split_sentences(full_text)
        raw_chunks: list[str] = []
        current = ""

        for sentence in sentences:
            # If a single sentence already exceeds the limit, keep it as-is
            if not current:
                current = sentence
            elif len(current) + len(sentence) + 1 <= max_chunk_size:
                current = current + " " + sentence
            else:
                raw_chunks.append(current.strip())
                current = sentence

        if current.strip():
            raw_chunks.append(current.strip())

        # Guard against empty input
        if not raw_chunks:
            return []

        total = len(raw_chunks)
        return [
            {
                "text": chunk_text,
                "parent_id": parent_id,
                "chunk_index": idx,
                "total_chunks": total,
                "celex": celex,
                "framework": framework,
                "article_number": article_number,
                "section_title": section_title,
            }
            for idx, chunk_text in enumerate(raw_chunks)
        ]

    def get_parent(self, parent_id: str) -> dict[str, Any] | None:
        """Retrieve a single parent document by its ID.

        Returns:
            A dict with the parent document fields, or ``None`` if not found.
        """
        if self._check_db():
            return self._get_parent_db(parent_id)
        return self._memory_store.get(parent_id)

    def get_parents_for_chunks(self, chunk_metadatas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Given a list of chunk metadata dicts (each with a ``parent_id``),
        return the corresponding parent documents.

        Duplicate parent IDs are deduplicated so that each parent appears
        only once in the output.

        Returns:
            List of parent-document dicts (order not guaranteed).
        """
        seen: set[str] = set()
        parents: list[dict[str, Any]] = []

        for meta in chunk_metadatas:
            pid = meta.get("parent_id")
            if pid and pid not in seen:
                seen.add(pid)
                doc = self.get_parent(pid)
                if doc is not None:
                    parents.append(doc)

        return parents

    def resolve_to_parents(self, search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expand hybrid-search sub-chunk results into full parent articles.

        Steps:
        1. Group results by ``parent_id``.
        2. For each parent, keep the **highest score** among its sub-chunks.
        3. Retrieve the full parent text.
        4. Return parent-level results sorted by descending score.

        Each returned dict contains:
        - ``parent_id``, ``full_text``, ``celex``, ``framework``,
          ``article_number``, ``section_title``
        - ``score`` (best sub-chunk score)
        - ``matched_sub_chunks`` (list of the original sub-chunk hits)

        Args:
            search_results: List of dicts, each with at least ``text``,
                ``metadata`` (containing ``parent_id``), and ``score``.

        Returns:
            Deduplicated parent-level results sorted by score (descending).
        """
        groups: dict[str, list[dict]] = defaultdict(list)

        for result in search_results:
            meta = result.get("metadata", {})
            pid = meta.get("parent_id")
            if pid is None:
                continue
            groups[pid].append(result)

        resolved: list[dict[str, Any]] = []

        for pid, hits in groups.items():
            parent = self.get_parent(pid)
            if parent is None:
                logger.warning("Parent document %s not found -- skipping", pid)
                continue

            best_score = max(h.get("score", 0.0) for h in hits)

            resolved.append(
                {
                    "parent_id": pid,
                    "full_text": parent.get("full_text", ""),
                    "celex": parent.get("celex", ""),
                    "framework": parent.get("framework", ""),
                    "article_number": parent.get("article_number", ""),
                    "section_title": parent.get("section_title", ""),
                    "score": best_score,
                    "matched_sub_chunks": [
                        {"text": h.get("text", ""), "score": h.get("score", 0.0)} for h in hits
                    ],
                }
            )

        resolved.sort(key=lambda r: r["score"], reverse=True)
        return resolved

    # ── sentence splitting ───────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split *text* on sentence boundaries (period/semicolon + space).

        Handles common EU legal abbreviations (Art., No., par., etc.) so
        they are not treated as sentence endings.
        """
        # Protect common abbreviations from being treated as sentence ends
        protected = text
        abbreviations = [
            "Art.",
            "art.",
            "No.",
            "no.",
            "par.",
            "Par.",
            "Dir.",
            "dir.",
            "Reg.",
            "reg.",
            "cf.",
            "Cf.",
            "al.",
            "etc.",
            "i.e.",
            "e.g.",
            "vs.",
        ]
        placeholder_map: dict[str, str] = {}
        for abbr in abbreviations:
            placeholder = abbr.replace(".", "\x00")
            placeholder_map[placeholder] = abbr
            protected = protected.replace(abbr, placeholder)

        # Split on period or semicolon followed by whitespace
        parts = re.split(r"(?<=[.;])\s+", protected)

        # Restore abbreviations
        restored: list[str] = []
        for part in parts:
            for placeholder, original in placeholder_map.items():
                part = part.replace(placeholder, original)
            stripped = part.strip()
            if stripped:
                restored.append(stripped)

        return restored

    # ── in-memory back-end ───────────────────────────────────────────────

    def _store_parent_memory(
        self,
        celex: str,
        framework: str,
        article_number: str | None,
        section_title: str | None,
        full_text: str,
        content_hash: str,
    ) -> str:
        # Check for existing document with same (celex, article_number)
        for doc_id, doc in self._memory_store.items():
            if doc["celex"] == celex and doc["article_number"] == article_number:
                if doc["content_hash"] == content_hash:
                    return doc_id  # unchanged
                # Update in place
                doc["framework"] = framework
                doc["section_title"] = section_title
                doc["full_text"] = full_text
                doc["content_hash"] = content_hash
                return doc_id

        doc_id = str(uuid.uuid4())
        self._memory_store[doc_id] = {
            "id": doc_id,
            "celex": celex,
            "framework": framework,
            "article_number": article_number,
            "section_title": section_title,
            "full_text": full_text,
            "content_hash": content_hash,
            "chunk_ids": [],
        }
        return doc_id

    # ── database back-end (sync via run_sync on the async engine) ────────

    def _store_parent_db(
        self,
        celex: str,
        framework: str,
        article_number: str | None,
        section_title: str | None,
        full_text: str,
        content_hash: str,
    ) -> str:
        """Upsert a parent document using a synchronous connection.

        Uses ``INSERT ... ON CONFLICT`` for atomic upsert.
        """
        from sqlalchemy import text as sa_text

        from src.db.engine import db_manager

        engine = db_manager._engine
        if engine is None:
            raise RuntimeError("Database engine is not initialized")

        # Use the underlying sync engine for synchronous access
        sync_engine = engine.sync_engine

        upsert_sql = sa_text("""
            INSERT INTO parent_documents
                (celex, framework, article_number, section_title, full_text, content_hash)
            VALUES
                (:celex, :framework, :article_number, :section_title, :full_text, :content_hash)
            ON CONFLICT (celex, article_number)
            DO UPDATE SET
                framework      = EXCLUDED.framework,
                section_title  = EXCLUDED.section_title,
                full_text      = EXCLUDED.full_text,
                content_hash   = EXCLUDED.content_hash,
                updated_at     = now()
            RETURNING id::text
        """)

        with sync_engine.connect() as conn:
            result = conn.execute(
                upsert_sql,
                {
                    "celex": celex,
                    "framework": framework,
                    "article_number": article_number,
                    "section_title": section_title,
                    "full_text": full_text,
                    "content_hash": content_hash,
                },
            )
            row = result.fetchone()
            conn.commit()
            return row[0]

    def _get_parent_db(self, parent_id: str) -> dict[str, Any] | None:
        """Retrieve a parent document from the database by ID."""
        from sqlalchemy import text as sa_text

        from src.db.engine import db_manager

        engine = db_manager._engine
        if engine is None:
            raise RuntimeError("Database engine is not initialized")

        sync_engine = engine.sync_engine

        sql = sa_text("""
            SELECT id::text, celex, framework, article_number, section_title,
                   full_text, content_hash, chunk_ids, created_at, updated_at
            FROM parent_documents
            WHERE id = :pid::uuid
        """)

        with sync_engine.connect() as conn:
            result = conn.execute(sql, {"pid": parent_id})
            row = result.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "celex": row[1],
                "framework": row[2],
                "article_number": row[3],
                "section_title": row[4],
                "full_text": row[5],
                "content_hash": row[6],
                "chunk_ids": row[7] or [],
                "created_at": row[8],
                "updated_at": row[9],
            }
