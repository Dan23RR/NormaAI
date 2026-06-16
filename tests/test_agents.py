"""Tests for NormaAI agent graph with mocked LLM."""

from src.agents.graph import _build_graph as build_normaai_graph
from src.agents.llm import extract_confidence as _extract_confidence
from src.agents.llm import format_retrieved_chunks as _format_retrieved_chunks
from src.agents.llm import parse_json_response as _parse_json_response
from src.agents.nodes import route_to_agent
from src.agents.sanitization import sanitize_input as _sanitize_input


class TestJsonParsing:
    def test_valid_json(self):
        result = _parse_json_response('{"answer": "test", "score": 0.9}')
        assert result["answer"] == "test"

    def test_json_in_code_block(self):
        content = '```json\n{"answer": "test"}\n```'
        result = _parse_json_response(content)
        assert result["answer"] == "test"

    def test_json_with_trailing_text(self):
        content = '{"answer": "test"}\n\nHere is some extra explanation.'
        result = _parse_json_response(content)
        assert result["answer"] == "test"

    def test_invalid_json_returns_raw(self):
        result = _parse_json_response("Not JSON at all, just text.")
        assert "answer" in result
        assert result["parse_warning"]

    def test_empty_string(self):
        result = _parse_json_response("")
        assert "answer" in result


class TestConfidenceExtraction:
    def test_valid_float(self):
        assert _extract_confidence({"confidence_score": 0.85}) == 0.85

    def test_clamped_high(self):
        assert _extract_confidence({"confidence_score": 1.5}) == 1.0

    def test_clamped_low(self):
        assert _extract_confidence({"confidence_score": -0.5}) == 0.0

    def test_missing_key(self):
        assert _extract_confidence({}) == 0.0

    def test_non_dict(self):
        assert _extract_confidence("not a dict") == 0.0

    def test_string_value(self):
        assert _extract_confidence({"confidence_score": "0.7"}) == 0.7


class TestChunkFormatting:
    def test_empty_chunks(self):
        result = _format_retrieved_chunks([])
        assert "No relevant" in result

    def test_dict_chunks(self):
        chunks = [
            {"framework": "CSRD", "article_number": "Art. 1", "text": "Test content"},
        ]
        result = _format_retrieved_chunks(chunks)
        assert "CSRD" in result
        assert "Art. 1" in result
        assert "Test content" in result

    def test_string_chunks(self):
        result = _format_retrieved_chunks(["raw text chunk"])
        assert "raw text chunk" in result


class TestInputSanitization:
    def test_normal_input(self):
        assert _sanitize_input("What are CSRD requirements?") == "What are CSRD requirements?"

    def test_truncation(self):
        long_text = "a" * 10000
        result = _sanitize_input(long_text, max_length=100)
        assert len(result) == 100

    def test_non_string(self):
        result = _sanitize_input(12345)
        assert result == "12345"


class TestRouting:
    def test_qa_route(self):
        assert route_to_agent({"task_type": "qa"}) == "qa_bot"

    def test_monitor_route(self):
        assert route_to_agent({"task_type": "monitor"}) == "monitor_agent"

    def test_gap_analysis_route(self):
        assert route_to_agent({"task_type": "gap_analysis"}) == "gap_analyst"

    def test_unknown_defaults_to_qa(self):
        assert route_to_agent({"task_type": "unknown"}) == "qa_bot"

    def test_empty_defaults_to_qa(self):
        assert route_to_agent({}) == "qa_bot"


class TestGraphBuild:
    def test_graph_compiles(self):
        graph = build_normaai_graph()
        assert graph is not None
