"""Tests for the Parent Document Retrieval logic.

These tests exercise the pure, non-DB logic of
:class:`src.nlp.chunking.parent_retriever.ParentDocumentStore`:

- sentence splitting (with EU legal abbreviation protection)
- sub-chunk creation (windowing, metadata propagation, edge cases)
- the in-memory parent store back-end (upsert / hash dedup)
- resolving search hits back to parent documents (grouping, best-score,
  dedup, ordering, missing parent handling)

The store transparently falls back to an in-memory dict when the database
is unavailable. To keep these tests deterministic (and free of any DB
dependency), every store is forced into memory mode via ``_db_available``.
"""

from unittest.mock import patch

import pytest

from src.nlp.chunking.parent_retriever import ParentDocumentStore


@pytest.fixture
def store():
    """A ParentDocumentStore pinned to the in-memory back-end."""
    s = ParentDocumentStore()
    # Force memory mode so _check_db never touches the real engine.
    s._db_available = False
    return s


# ── _content_hash ────────────────────────────────────────────────────────


class TestContentHash:
    def test_is_sha256_hexdigest(self):
        import hashlib

        text = "Article 1: Member States shall comply."
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert ParentDocumentStore._content_hash(text) == expected
        # SHA-256 hex digest is always 64 chars.
        assert len(ParentDocumentStore._content_hash(text)) == 64

    def test_differs_for_different_text(self):
        assert ParentDocumentStore._content_hash("a") != ParentDocumentStore._content_hash("b")

    def test_stable_for_same_text(self):
        assert ParentDocumentStore._content_hash("same") == ParentDocumentStore._content_hash(
            "same"
        )

    def test_handles_unicode(self):
        # Should not raise on non-ASCII (utf-8 encoding).
        digest = ParentDocumentStore._content_hash("réglementation européenne €")
        assert len(digest) == 64


# ── _split_sentences ─────────────────────────────────────────────────────


class TestSplitSentences:
    def test_basic_period_split(self):
        result = ParentDocumentStore._split_sentences("First sentence. Second sentence.")
        assert result == ["First sentence.", "Second sentence."]

    def test_semicolon_split(self):
        result = ParentDocumentStore._split_sentences("Clause one; clause two.")
        assert result == ["Clause one;", "clause two."]

    def test_empty_string_returns_empty_list(self):
        assert ParentDocumentStore._split_sentences("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert ParentDocumentStore._split_sentences("   \n  ") == []

    def test_single_sentence_no_trailing_period(self):
        result = ParentDocumentStore._split_sentences("No terminal punctuation here")
        assert result == ["No terminal punctuation here"]

    def test_blank_parts_are_dropped(self):
        # Multiple spaces / a trailing split should not create empty entries.
        result = ParentDocumentStore._split_sentences("A.  B.   ")
        assert result == ["A.", "B."]
        assert "" not in result

    def test_protects_legal_abbreviation_art(self):
        # "Art. 29" must NOT be split into "Art." and "29 ...".
        text = "See Art. 29 for details. The next provision follows."
        result = ParentDocumentStore._split_sentences(text)
        assert result == ["See Art. 29 for details.", "The next provision follows."]

    def test_protects_multiple_abbreviations(self):
        text = "Cf. Dir. 2026/470, par. 3, i.e. the relevant rule. Then continue."
        result = ParentDocumentStore._split_sentences(text)
        # The whole first sentence (with its abbreviations) stays together.
        assert result[0] == "Cf. Dir. 2026/470, par. 3, i.e. the relevant rule."
        assert result[1] == "Then continue."

    def test_abbreviation_restored_in_output(self):
        # The null-byte placeholder used internally must be fully restored.
        result = ParentDocumentStore._split_sentences("Refer to No. 5 herein.")
        joined = " ".join(result)
        assert "No." in joined
        assert "\x00" not in joined


# ── create_sub_chunks ────────────────────────────────────────────────────


class TestCreateSubChunks:
    def test_empty_text_returns_empty_list(self, store):
        assert store.create_sub_chunks("pid-1", "") == []

    def test_whitespace_text_returns_empty_list(self, store):
        assert store.create_sub_chunks("pid-1", "   \n  ") == []

    def test_single_short_sentence_one_chunk(self, store):
        chunks = store.create_sub_chunks("pid-1", "A single short sentence.")
        assert len(chunks) == 1
        assert chunks[0]["text"] == "A single short sentence."
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["total_chunks"] == 1
        assert chunks[0]["parent_id"] == "pid-1"

    def test_metadata_is_propagated(self, store):
        chunks = store.create_sub_chunks(
            "pid-meta",
            "Some legal text here.",
            celex="32022L2464",
            framework="CSRD",
            article_number="Art. 29",
            section_title="Reporting",
        )
        assert len(chunks) == 1
        c = chunks[0]
        assert c["celex"] == "32022L2464"
        assert c["framework"] == "CSRD"
        assert c["article_number"] == "Art. 29"
        assert c["section_title"] == "Reporting"

    def test_default_metadata_is_empty_strings(self, store):
        chunks = store.create_sub_chunks("pid", "Short text.")
        c = chunks[0]
        assert c["celex"] == ""
        assert c["framework"] == ""
        assert c["article_number"] == ""
        assert c["section_title"] == ""

    def test_packs_multiple_short_sentences_into_one_chunk(self, store):
        # Three small sentences fit comfortably under the default 500 cap.
        text = "Alpha. Beta. Gamma."
        chunks = store.create_sub_chunks("pid", text)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Alpha. Beta. Gamma."

    def test_splits_when_max_chunk_size_exceeded(self, store):
        # Each sentence is ~30 chars; with max_chunk_size=40 only one fits per chunk.
        s1 = "This is the first long sentence."
        s2 = "This is the second long sentence."
        chunks = store.create_sub_chunks("pid", f"{s1} {s2}", max_chunk_size=40)
        assert len(chunks) == 2
        assert chunks[0]["text"] == s1
        assert chunks[1]["text"] == s2

    def test_total_chunks_matches_count_and_indices_are_sequential(self, store):
        text = "One sentence here. Two sentence here. Three sentence here."
        chunks = store.create_sub_chunks("pid", text, max_chunk_size=20)
        total = len(chunks)
        assert all(c["total_chunks"] == total for c in chunks)
        assert [c["chunk_index"] for c in chunks] == list(range(total))

    def test_oversized_single_sentence_kept_whole(self, store):
        # A single sentence longer than max_chunk_size is kept as-is (not truncated),
        # because the first sentence always seeds `current` regardless of size.
        big = "word " * 300 + "end."  # well over 500 chars, no internal sentence breaks
        chunks = store.create_sub_chunks("pid", big.strip(), max_chunk_size=50)
        assert len(chunks) == 1
        assert len(chunks[0]["text"]) > 50

    def test_text_is_stripped(self, store):
        chunks = store.create_sub_chunks("pid", "   Padded sentence.   ")
        assert chunks[0]["text"] == "Padded sentence."


# ── in-memory store_parent (upsert + hash dedup) ─────────────────────────


class TestStoreParentMemory:
    def test_store_returns_id_and_persists(self, store):
        pid = store.store_parent("32022L2464", "CSRD", "Art. 1", "Scope", "Full text body.")
        assert isinstance(pid, str)
        doc = store.get_parent(pid)
        assert doc is not None
        assert doc["celex"] == "32022L2464"
        assert doc["framework"] == "CSRD"
        assert doc["article_number"] == "Art. 1"
        assert doc["section_title"] == "Scope"
        assert doc["full_text"] == "Full text body."
        assert doc["chunk_ids"] == []

    def test_store_sets_content_hash(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        doc = store.get_parent(pid)
        assert doc["content_hash"] == ParentDocumentStore._content_hash("Body")

    def test_same_key_same_content_returns_same_id_no_rewrite(self, store):
        pid1 = store.store_parent("C1", "CSRD", "Art. 1", "S", "Identical body")
        pid2 = store.store_parent("C1", "CSRD", "Art. 1", "S", "Identical body")
        assert pid1 == pid2
        # Only one document should exist in the store.
        assert len(store._memory_store) == 1

    def test_same_key_changed_content_updates_in_place(self, store):
        pid1 = store.store_parent("C1", "CSRD", "Art. 1", "Old section", "Old body")
        pid2 = store.store_parent("C1", "DORA", "Art. 1", "New section", "New body")
        assert pid1 == pid2  # upsert key is (celex, article_number)
        assert len(store._memory_store) == 1
        doc = store.get_parent(pid1)
        assert doc["full_text"] == "New body"
        assert doc["framework"] == "DORA"
        assert doc["section_title"] == "New section"
        assert doc["content_hash"] == ParentDocumentStore._content_hash("New body")

    def test_different_article_creates_new_document(self, store):
        pid1 = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body 1")
        pid2 = store.store_parent("C1", "CSRD", "Art. 2", "S", "Body 2")
        assert pid1 != pid2
        assert len(store._memory_store) == 2

    def test_different_celex_creates_new_document(self, store):
        pid1 = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        pid2 = store.store_parent("C2", "CSRD", "Art. 1", "S", "Body")
        assert pid1 != pid2
        assert len(store._memory_store) == 2

    def test_none_article_number_matches_on_upsert(self, store):
        pid1 = store.store_parent("C1", "CSRD", None, "S", "Body v1")
        pid2 = store.store_parent("C1", "CSRD", None, "S2", "Body v2")
        assert pid1 == pid2
        doc = store.get_parent(pid1)
        assert doc["full_text"] == "Body v2"


# ── get_parent ───────────────────────────────────────────────────────────


class TestGetParent:
    def test_missing_returns_none(self, store):
        assert store.get_parent("nonexistent-id") is None

    def test_existing_returns_doc(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        assert store.get_parent(pid)["id"] == pid


# ── get_parents_for_chunks ───────────────────────────────────────────────


class TestGetParentsForChunks:
    def test_empty_input_returns_empty(self, store):
        assert store.get_parents_for_chunks([]) == []

    def test_dedup_by_parent_id(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        metas = [
            {"parent_id": pid, "chunk_index": 0},
            {"parent_id": pid, "chunk_index": 1},
            {"parent_id": pid, "chunk_index": 2},
        ]
        parents = store.get_parents_for_chunks(metas)
        assert len(parents) == 1
        assert parents[0]["id"] == pid

    def test_multiple_distinct_parents(self, store):
        pid1 = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body 1")
        pid2 = store.store_parent("C1", "CSRD", "Art. 2", "S", "Body 2")
        metas = [{"parent_id": pid1}, {"parent_id": pid2}, {"parent_id": pid1}]
        parents = store.get_parents_for_chunks(metas)
        returned_ids = {p["id"] for p in parents}
        assert returned_ids == {pid1, pid2}
        assert len(parents) == 2

    def test_chunk_without_parent_id_is_skipped(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        metas = [{"chunk_index": 0}, {"parent_id": None}, {"parent_id": pid}]
        parents = store.get_parents_for_chunks(metas)
        assert len(parents) == 1
        assert parents[0]["id"] == pid

    def test_unknown_parent_id_is_skipped(self, store):
        # parent_id present but no stored doc -> get_parent returns None -> skipped.
        metas = [{"parent_id": "ghost-id"}]
        assert store.get_parents_for_chunks(metas) == []


# ── resolve_to_parents ───────────────────────────────────────────────────


class TestResolveToParents:
    def test_empty_input_returns_empty(self, store):
        assert store.resolve_to_parents([]) == []

    def test_single_hit_resolves_to_parent(self, store):
        pid = store.store_parent("32022L2464", "CSRD", "Art. 29", "Reporting", "Full article text.")
        results = [
            {
                "text": "matched sub-chunk text",
                "score": 0.87,
                "metadata": {"parent_id": pid},
            }
        ]
        resolved = store.resolve_to_parents(results)
        assert len(resolved) == 1
        r = resolved[0]
        assert r["parent_id"] == pid
        assert r["full_text"] == "Full article text."
        assert r["celex"] == "32022L2464"
        assert r["framework"] == "CSRD"
        assert r["article_number"] == "Art. 29"
        assert r["section_title"] == "Reporting"
        assert r["score"] == 0.87
        assert r["matched_sub_chunks"] == [{"text": "matched sub-chunk text", "score": 0.87}]

    def test_keeps_best_score_among_sub_chunks(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        results = [
            {"text": "lo", "score": 0.30, "metadata": {"parent_id": pid}},
            {"text": "hi", "score": 0.95, "metadata": {"parent_id": pid}},
            {"text": "mid", "score": 0.60, "metadata": {"parent_id": pid}},
        ]
        resolved = store.resolve_to_parents(results)
        assert len(resolved) == 1
        assert resolved[0]["score"] == 0.95
        # All three sub-chunks are retained in matched_sub_chunks.
        assert len(resolved[0]["matched_sub_chunks"]) == 3

    def test_groups_by_parent_and_sorts_by_score_desc(self, store):
        pid_a = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body A")
        pid_b = store.store_parent("C1", "CSRD", "Art. 2", "S", "Body B")
        results = [
            {"text": "a1", "score": 0.40, "metadata": {"parent_id": pid_a}},
            {"text": "b1", "score": 0.90, "metadata": {"parent_id": pid_b}},
            {"text": "a2", "score": 0.50, "metadata": {"parent_id": pid_a}},
        ]
        resolved = store.resolve_to_parents(results)
        assert len(resolved) == 2
        # Sorted by best score descending: B (0.90) before A (0.50).
        assert resolved[0]["parent_id"] == pid_b
        assert resolved[0]["score"] == 0.90
        assert resolved[1]["parent_id"] == pid_a
        assert resolved[1]["score"] == 0.50

    def test_hit_without_parent_id_is_skipped(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        results = [
            {"text": "no-meta", "score": 0.99, "metadata": {}},
            {"text": "none-pid", "score": 0.99, "metadata": {"parent_id": None}},
            {"text": "ok", "score": 0.42, "metadata": {"parent_id": pid}},
        ]
        resolved = store.resolve_to_parents(results)
        assert len(resolved) == 1
        assert resolved[0]["parent_id"] == pid

    def test_missing_metadata_key_treated_as_no_parent(self, store):
        # result with no "metadata" key at all -> .get returns {} -> skipped.
        results = [{"text": "x", "score": 0.5}]
        assert store.resolve_to_parents(results) == []

    def test_unknown_parent_is_skipped_with_warning(self, store):
        results = [{"text": "x", "score": 0.5, "metadata": {"parent_id": "ghost"}}]
        with patch("src.nlp.chunking.parent_retriever.logger") as mock_logger:
            resolved = store.resolve_to_parents(results)
        assert resolved == []
        mock_logger.warning.assert_called_once()

    def test_missing_score_defaults_to_zero(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        results = [{"text": "no-score", "metadata": {"parent_id": pid}}]
        resolved = store.resolve_to_parents(results)
        assert resolved[0]["score"] == 0.0
        assert resolved[0]["matched_sub_chunks"][0]["score"] == 0.0

    def test_missing_text_defaults_to_empty_string(self, store):
        pid = store.store_parent("C1", "CSRD", "Art. 1", "S", "Body")
        results = [{"score": 0.7, "metadata": {"parent_id": pid}}]
        resolved = store.resolve_to_parents(results)
        assert resolved[0]["matched_sub_chunks"][0]["text"] == ""


# ── _check_db fallback behaviour ─────────────────────────────────────────


class TestCheckDbFallback:
    def test_cached_value_short_circuits(self, store):
        # store fixture already pinned _db_available=False; _check_db returns it
        # without re-importing anything.
        assert store._check_db() is False

    def test_import_failure_falls_back_to_memory(self):
        s = ParentDocumentStore()
        # Simulate the db engine import raising -> _db_available becomes False.
        with patch(
            "builtins.__import__",
            side_effect=ImportError("no db"),
        ):
            assert s._check_db() is False
        assert s._db_available is False

    def test_engine_none_means_unavailable(self):
        import types

        s = ParentDocumentStore()
        fake_module = types.SimpleNamespace(db_manager=types.SimpleNamespace(_engine=None))

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "src.db.engine":
                return fake_module
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert s._check_db() is False


# ── round-trip integration of the pure pipeline ──────────────────────────


class TestPipelineRoundTrip:
    def test_store_chunk_resolve_round_trip(self, store):
        full_text = (
            "Large undertakings shall include sustainability information. "
            "This applies under Art. 19a of the Directive. "
            "Member States shall ensure compliance with these provisions."
        )
        pid = store.store_parent("32022L2464", "CSRD", "Art. 19a", "Reporting", full_text)

        sub_chunks = store.create_sub_chunks(
            pid,
            full_text,
            max_chunk_size=60,
            celex="32022L2464",
            framework="CSRD",
            article_number="Art. 19a",
            section_title="Reporting",
        )
        assert len(sub_chunks) >= 2
        # Every sub-chunk points back to the parent.
        assert all(c["parent_id"] == pid for c in sub_chunks)

        # Simulate a hybrid-search result for two of the sub-chunks.
        search_results = [
            {"text": sub_chunks[0]["text"], "score": 0.55, "metadata": {"parent_id": pid}},
            {"text": sub_chunks[1]["text"], "score": 0.81, "metadata": {"parent_id": pid}},
        ]
        resolved = store.resolve_to_parents(search_results)
        assert len(resolved) == 1
        assert resolved[0]["parent_id"] == pid
        assert resolved[0]["full_text"] == full_text
        assert resolved[0]["score"] == 0.81
