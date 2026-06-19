"""Unit tests for the dots.ocr document processor: src/nlp/processing/dots_ocr_processor.py.

dots.ocr is an OPTIONAL vision-language OCR backend. In the test environment the
`dots_ocr` package is NOT installed, so the module imports with
DOTS_OCR_AVAILABLE=False and DOTS_OCR_MODE="vllm" (httpx is present). These tests
control behaviour deterministically by patching the module-level availability
globals and the locally-imported httpx / dots_ocr dependencies. No real model is
downloaded, no real inference runs, and no network call is made.

Coverage targets:
- DotsOCRProcessor.is_available / mode across local / vllm / unavailable
- _check_vllm_health: healthy 200, non-200, exception, and the cache short-circuit
- process_pdf / process_image: missing-file guard, mode routing, not-available path
- _process_local: fake DotsOCRParser happy path + exception -> None
- _process_vllm: payload/mime/base64 wiring, choices parsing, exception -> None
- _normalize_result: every element-category branch, list-vs-dict input, counts
- _parse_ocr_output: structured-JSON path vs raw-text fallback
- UnifiedDocumentProcessor: smart routing, force_engine, available_engines,
  the _try_* helpers, lazy docling property, and _empty_result shape

Every external dependency (httpx, the dots_ocr parser, docling) is mocked.
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.nlp.processing import dots_ocr_processor as mod
from src.nlp.processing.dots_ocr_processor import (
    DotsOCRProcessor,
    UnifiedDocumentProcessor,
)

MODULE = "src.nlp.processing.dots_ocr_processor"


# ─── Helpers ──────────────────────────────────────────────────────


def _existing_path(monkeypatch, exists=True):
    """Force Path.exists() to a fixed value for every Path in the module."""
    monkeypatch.setattr(f"{MODULE}.Path.exists", lambda self: exists)


# ─── DotsOCRProcessor.__init__ ────────────────────────────────────


class TestInit:
    def test_defaults(self):
        proc = DotsOCRProcessor()
        assert proc.vllm_url == "http://localhost:8001/v1"
        assert proc.model_path == ""
        assert proc.dpi == 200
        assert proc.max_pages == 100
        assert proc._local_parser is None
        assert proc._vllm_available is None

    def test_overrides(self):
        proc = DotsOCRProcessor(
            vllm_url="http://srv:9000/v1", model_path="/m", dpi=300, max_pages=5
        )
        assert proc.vllm_url == "http://srv:9000/v1"
        assert proc.model_path == "/m"
        assert proc.dpi == 300
        assert proc.max_pages == 5


# ─── is_available / mode ──────────────────────────────────────────


class TestAvailabilityProperties:
    def test_is_available_local(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "local")
        assert DotsOCRProcessor().is_available is True

    def test_is_available_vllm_delegates_to_health(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "vllm")
        proc = DotsOCRProcessor()
        with patch.object(proc, "_check_vllm_health", return_value=True) as health:
            assert proc.is_available is True
            health.assert_called_once()

    def test_is_available_vllm_health_false(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "vllm")
        proc = DotsOCRProcessor()
        with patch.object(proc, "_check_vllm_health", return_value=False):
            assert proc.is_available is False

    def test_is_available_unavailable(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "unavailable")
        assert DotsOCRProcessor().is_available is False

    def test_mode_local_short_circuits_health(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "local")
        proc = DotsOCRProcessor()
        with patch.object(proc, "_check_vllm_health", return_value=False) as health:
            assert proc.mode == "local"
            health.assert_not_called()

    def test_mode_vllm_when_healthy(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "vllm")
        proc = DotsOCRProcessor()
        with patch.object(proc, "_check_vllm_health", return_value=True):
            assert proc.mode == "vllm"

    def test_mode_unavailable_when_not_healthy(self, monkeypatch):
        monkeypatch.setattr(mod, "DOTS_OCR_MODE", "unavailable")
        proc = DotsOCRProcessor()
        with patch.object(proc, "_check_vllm_health", return_value=False):
            assert proc.mode == "unavailable"


# ─── _check_vllm_health ───────────────────────────────────────────


class TestCheckVllmHealth:
    def test_healthy_200(self):
        proc = DotsOCRProcessor(vllm_url="http://vllm:8001/v1")
        resp = MagicMock(status_code=200)
        with patch("httpx.get", return_value=resp) as get:
            assert proc._check_vllm_health() is True
            get.assert_called_once_with("http://vllm:8001/v1/models", timeout=5.0)
        assert proc._vllm_available is True

    def test_non_200_is_unhealthy(self):
        proc = DotsOCRProcessor()
        with patch("httpx.get", return_value=MagicMock(status_code=503)):
            assert proc._check_vllm_health() is False
        assert proc._vllm_available is False

    def test_exception_is_unhealthy(self):
        proc = DotsOCRProcessor()
        with patch("httpx.get", side_effect=OSError("connection refused")):
            assert proc._check_vllm_health() is False
        assert proc._vllm_available is False

    def test_result_is_cached_no_second_call(self):
        proc = DotsOCRProcessor()
        with patch("httpx.get", return_value=MagicMock(status_code=200)) as get:
            assert proc._check_vllm_health() is True
            assert proc._check_vllm_health() is True
            get.assert_called_once()

    def test_cached_false_short_circuits(self):
        proc = DotsOCRProcessor()
        proc._vllm_available = False
        with patch("httpx.get") as get:
            assert proc._check_vllm_health() is False
            get.assert_not_called()


# ─── process_pdf / process_image: file guards + routing ───────────


class TestProcessEntrypoints:
    def test_process_pdf_missing_file_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=False)
        assert DotsOCRProcessor().process_pdf("/nope.pdf") is None

    def test_process_image_missing_file_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=False)
        assert DotsOCRProcessor().process_image("/nope.png") is None

    def test_process_pdf_routes_to_local(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        sentinel = {"markdown": "local"}
        with (
            patch.object(type(proc), "mode", new=property(lambda self: "local")),
            patch.object(proc, "_process_local", return_value=sentinel) as local,
            patch.object(proc, "_process_vllm") as vllm,
        ):
            assert proc.process_pdf("/doc.pdf") is sentinel
            local.assert_called_once()
            vllm.assert_not_called()

    def test_process_pdf_routes_to_vllm(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        sentinel = {"markdown": "vllm"}
        with (
            patch.object(type(proc), "mode", new=property(lambda self: "vllm")),
            patch.object(proc, "_process_vllm", return_value=sentinel) as vllm,
            patch.object(proc, "_process_local") as local,
        ):
            assert proc.process_pdf("/doc.pdf") is sentinel
            vllm.assert_called_once()
            local.assert_not_called()

    def test_process_pdf_unavailable_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        with patch.object(type(proc), "mode", new=property(lambda self: "unavailable")):
            assert proc.process_pdf("/doc.pdf") is None

    def test_process_image_routes_to_local(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        sentinel = {"markdown": "img"}
        with (
            patch.object(type(proc), "mode", new=property(lambda self: "local")),
            patch.object(proc, "_process_local", return_value=sentinel) as local,
        ):
            assert proc.process_image("/scan.png") is sentinel
            local.assert_called_once()

    def test_process_image_routes_to_vllm(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        sentinel = {"markdown": "imgvllm"}
        with (
            patch.object(type(proc), "mode", new=property(lambda self: "vllm")),
            patch.object(proc, "_process_vllm", return_value=sentinel) as vllm,
        ):
            assert proc.process_image("/scan.png") is sentinel
            vllm.assert_called_once()

    def test_process_image_unavailable_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        with patch.object(type(proc), "mode", new=property(lambda self: "unavailable")):
            assert proc.process_image("/scan.png") is None


# ─── _process_local (fake dots_ocr parser) ────────────────────────


class TestProcessLocal:
    def _inject_fake_dots_ocr(self, parse_return=None, raise_exc=None):
        """Build a fake `dots_ocr.parser` module exposing DotsOCRParser."""
        parser_instance = MagicMock()
        if raise_exc is not None:
            parser_instance.parse.side_effect = raise_exc
        else:
            parser_instance.parse.return_value = parse_return
        parser_cls = MagicMock(return_value=parser_instance)
        fake_parser_mod = SimpleNamespace(DotsOCRParser=parser_cls)
        fake_pkg = SimpleNamespace(parser=fake_parser_mod)
        modules = {"dots_ocr": fake_pkg, "dots_ocr.parser": fake_parser_mod}
        return modules, parser_cls, parser_instance

    def test_local_happy_path_normalizes(self):
        elements = [
            {"category": "title", "text": "Regolamento UE"},
            {"category": "text", "text": "Articolo 1"},
        ]
        modules, parser_cls, parser_instance = self._inject_fake_dots_ocr(parse_return=elements)
        proc = DotsOCRProcessor(model_path="/weights")
        with patch.dict("sys.modules", modules):
            result = proc._process_local("/doc.pdf")
        # Parser constructed with the configured model path.
        parser_cls.assert_called_once_with(model_path="/weights")
        parser_instance.parse.assert_called_once_with("/doc.pdf")
        assert "## Regolamento UE" in result["markdown"]
        assert "Articolo 1" in result["markdown"]
        assert result["metadata"]["processor"] == "dots_ocr_local"
        assert result["metadata"]["elements_count"] == 2

    def test_local_empty_model_path_passes_none(self):
        modules, parser_cls, _ = self._inject_fake_dots_ocr(parse_return=[])
        proc = DotsOCRProcessor(model_path="")
        with patch.dict("sys.modules", modules):
            proc._process_local("/doc.pdf")
        parser_cls.assert_called_once_with(model_path=None)

    def test_local_exception_returns_none(self):
        modules, _, _ = self._inject_fake_dots_ocr(raise_exc=RuntimeError("OOM"))
        proc = DotsOCRProcessor()
        with patch.dict("sys.modules", modules):
            assert proc._process_local("/doc.pdf") is None

    def test_local_import_error_returns_none(self):
        # No dots_ocr in sys.modules and not installed -> ImportError -> None.
        proc = DotsOCRProcessor()
        with patch.dict("sys.modules", {"dots_ocr": None, "dots_ocr.parser": None}):
            assert proc._process_local("/doc.pdf") is None


# ─── _process_vllm (mock httpx + file IO) ─────────────────────────


class TestProcessVllm:
    def test_vllm_happy_path_parses_choices(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        # Model returns structured JSON content via the chat completions API.
        content = json.dumps([{"category": "text", "text": "hello"}])
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"content": content}}]}
        proc = DotsOCRProcessor(vllm_url="http://vllm:8001/v1", dpi=222)
        with (
            patch("builtins.open", mock_open(read_data=b"PDFBYTES")),
            patch("httpx.post", return_value=resp) as post,
        ):
            result = proc._process_vllm("/doc.pdf")

        # Endpoint, timeout and payload essentials.
        assert post.call_args.args[0] == "http://vllm:8001/v1/chat/completions"
        assert post.call_args.kwargs["timeout"] == 120.0
        payload = post.call_args.kwargs["json"]
        assert payload["temperature"] == 0.0
        assert payload["model"] == "rednote-hilab/dots.ocr-1.5"
        image_url = payload["messages"][0]["content"][0]["image_url"]["url"]
        expected_b64 = base64.b64encode(b"PDFBYTES").decode("utf-8")
        assert image_url == f"data:application/pdf;base64,{expected_b64}"
        # Output normalized.
        assert "hello" in result["markdown"]
        assert result["metadata"]["processor"] == "dots_ocr_vllm"
        assert result["metadata"]["dpi"] == 222

    @pytest.mark.parametrize(
        ("path", "mime"),
        [
            ("/a.png", "image/png"),
            ("/a.jpg", "image/jpeg"),
            ("/a.jpeg", "image/jpeg"),
            ("/a.tiff", "image/tiff"),
            ("/a.bmp", "image/bmp"),
            ("/a.pdf", "application/pdf"),
            ("/a.xyz", "application/octet-stream"),
        ],
    )
    def test_vllm_mime_mapping(self, monkeypatch, path, mime):
        _existing_path(monkeypatch, exists=True)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        proc = DotsOCRProcessor()
        with (
            patch("builtins.open", mock_open(read_data=b"D")),
            patch("httpx.post", return_value=resp) as post,
        ):
            proc._process_vllm(path)
        url = post.call_args.kwargs["json"]["messages"][0]["content"][0]["image_url"]["url"]
        assert url.startswith(f"data:{mime};base64,")

    def test_vllm_http_error_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        resp = MagicMock()
        resp.raise_for_status.side_effect = RuntimeError("500")
        proc = DotsOCRProcessor()
        with (
            patch("builtins.open", mock_open(read_data=b"D")),
            patch("httpx.post", return_value=resp),
        ):
            assert proc._process_vllm("/doc.pdf") is None

    def test_vllm_malformed_response_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": []}  # KeyError/IndexError on [0]
        proc = DotsOCRProcessor()
        with (
            patch("builtins.open", mock_open(read_data=b"D")),
            patch("httpx.post", return_value=resp),
        ):
            assert proc._process_vllm("/doc.pdf") is None

    def test_vllm_open_failure_returns_none(self, monkeypatch):
        _existing_path(monkeypatch, exists=True)
        proc = DotsOCRProcessor()
        with patch("builtins.open", side_effect=OSError("denied")):
            assert proc._process_vllm("/doc.pdf") is None


# ─── _normalize_result (every category branch) ────────────────────


class TestNormalizeResult:
    def setup_method(self):
        self.proc = DotsOCRProcessor(dpi=150)

    def test_list_input_all_branches(self):
        elements = [
            {"category": "title", "text": "T1"},
            {"category": "section_header", "text": "S1"},
            {"category": "table", "text": "row", "html": "<table></table>", "bbox": [1, 2]},
            {"category": "formula", "text": "E=mc^2"},
            {"category": "text", "text": "para text"},
            {"category": "list_item", "text": "item"},
            {"category": "image", "text": "caption"},  # unknown w/ text -> appended
            {"category": "image", "text": ""},  # unknown w/o text -> skipped
        ]
        result = self.proc._normalize_result(elements, "/f.pdf", "local")
        md = result["markdown"]
        assert "## T1" in md
        assert "## S1" in md
        assert "[TABLE]" in md and "row" in md
        assert "$$E=mc^2$$" in md
        assert "para text" in md
        assert "item" in md
        assert "caption" in md
        # Tables collected with html + bbox.
        assert len(result["tables"]) == 1
        assert result["tables"][0]["html"] == "<table></table>"
        assert result["tables"][0]["bbox"] == [1, 2]
        # Metadata counts.
        assert result["metadata"]["elements_count"] == 8
        assert result["metadata"]["tables_count"] == 1
        assert result["metadata"]["processor"] == "dots_ocr_local"
        assert result["metadata"]["dpi"] == 150
        # Layout is the raw element list.
        assert result["layout"] == elements

    def test_dict_input_uses_elements_key(self):
        raw = {"elements": [{"category": "text", "text": "abc"}]}
        result = self.proc._normalize_result(raw, "/f.pdf", "vllm")
        assert "abc" in result["markdown"]
        assert result["metadata"]["elements_count"] == 1

    def test_dict_without_elements_key_is_empty(self):
        result = self.proc._normalize_result({"foo": "bar"}, "/f.pdf", "vllm")
        assert result["markdown"] == ""
        assert result["metadata"]["elements_count"] == 0

    def test_type_key_fallback_when_no_category(self):
        # Element uses "type" + "content" instead of "category" + "text".
        elements = [{"type": "title", "content": "Heading"}]
        result = self.proc._normalize_result(elements, "/f.pdf", "local")
        assert "## Heading" in result["markdown"]

    def test_default_text_category_when_keys_missing(self):
        # No category/type -> defaults to "text"; no text/content -> "".
        result = self.proc._normalize_result([{}], "/f.pdf", "local")
        # An empty text paragraph is still appended (the text/paragraph branch).
        assert result["metadata"]["elements_count"] == 1
        assert result["markdown"] == ""


# ─── _parse_ocr_output (JSON vs raw text) ─────────────────────────


class TestParseOcrOutput:
    def setup_method(self):
        self.proc = DotsOCRProcessor()

    def test_valid_json_list_normalized(self):
        content = json.dumps([{"category": "text", "text": "json text"}])
        result = self.proc._parse_ocr_output(content, "/f.pdf", "vllm")
        assert "json text" in result["markdown"]
        # Structured path produces an elements list, not raw_text.
        assert result["metadata"].get("output_format") != "raw_text"

    def test_invalid_json_falls_back_to_raw_text(self):
        content = "Just some **markdown** text, not JSON."
        result = self.proc._parse_ocr_output(content, "/f.pdf", "vllm")
        assert result["markdown"] == content
        assert result["tables"] == []
        assert result["layout"] == []
        assert result["metadata"]["output_format"] == "raw_text"
        assert result["metadata"]["processor"] == "dots_ocr_vllm"

    def test_none_content_falls_back_to_raw_text(self):
        # json.loads(None) raises TypeError -> caught -> raw-text fallback.
        result = self.proc._parse_ocr_output(None, "/f.pdf", "vllm")
        assert result["markdown"] is None
        assert result["metadata"]["output_format"] == "raw_text"


# ─── UnifiedDocumentProcessor ─────────────────────────────────────


class TestUnifiedInit:
    def test_init_wires_dots_ocr_url(self):
        u = UnifiedDocumentProcessor(dots_ocr_url="http://x:1/v1", prefer_dots_ocr=False)
        assert isinstance(u.dots_ocr, DotsOCRProcessor)
        assert u.dots_ocr.vllm_url == "http://x:1/v1"
        assert u.prefer_dots_ocr is False
        assert u._docling is None

    def test_docling_lazy_loaded_once(self):
        u = UnifiedDocumentProcessor()
        fake_docling = MagicMock()
        fake_cls = MagicMock(return_value=fake_docling)
        fake_mod = SimpleNamespace(DoclingProcessor=fake_cls)
        with patch.dict("sys.modules", {"src.nlp.processing.docling_processor": fake_mod}):
            first = u.docling
            second = u.docling
        assert first is fake_docling
        assert second is fake_docling
        fake_cls.assert_called_once()


class TestUnifiedAvailableEngines:
    def test_lists_dots_ocr_docling_and_fallback(self):
        u = UnifiedDocumentProcessor()
        u.dots_ocr = MagicMock(is_available=True, mode="vllm")
        u._docling = MagicMock(is_available=True)
        engines = u.available_engines
        assert "dots_ocr (vllm)" in engines
        assert "docling" in engines
        assert "beautifulsoup (fallback)" in engines

    def test_omits_unavailable_engines_but_keeps_fallback(self):
        u = UnifiedDocumentProcessor()
        u.dots_ocr = MagicMock(is_available=False)
        u._docling = MagicMock(is_available=False)
        engines = u.available_engines
        assert not any(e.startswith("dots_ocr") for e in engines)
        assert "docling" not in engines
        assert engines == ["beautifulsoup (fallback)"]


class TestUnifiedRouting:
    def _proc(self):
        u = UnifiedDocumentProcessor()
        u.dots_ocr = MagicMock()
        u._docling = MagicMock()
        return u

    def test_image_routes_to_dots_ocr(self, monkeypatch):
        u = self._proc()
        u.dots_ocr.is_available = True
        out = {"markdown": "img"}
        u.dots_ocr.process_image.return_value = out
        result = u.process("/scan.png")
        assert result is out
        u.dots_ocr.process_image.assert_called_once_with("/scan.png")

    def test_image_no_processor_returns_empty(self):
        u = self._proc()
        u.dots_ocr.is_available = False
        result = u.process("/scan.png")
        assert result["markdown"] == ""
        assert "Install dots.ocr" in result["metadata"]["error"]
        assert result["metadata"]["processor"] == "none"

    def test_pdf_prefers_dots_ocr_when_available(self):
        u = self._proc()
        u.prefer_dots_ocr = True
        u.dots_ocr.is_available = True
        out = {"markdown": "from dots"}
        u.dots_ocr.process_pdf.return_value = out
        result = u.process("/doc.pdf")
        assert result is out
        u._docling.process_pdf.assert_not_called()

    def test_pdf_falls_back_to_docling_when_dots_fails(self):
        u = self._proc()
        u.prefer_dots_ocr = True
        u.dots_ocr.is_available = True
        u.dots_ocr.process_pdf.return_value = None  # dots.ocr fails
        u._docling.is_available = True
        out = {"markdown": "from docling"}
        u._docling.process_pdf.return_value = out
        result = u.process("/doc.pdf")
        assert result is out

    def test_pdf_last_resort_dots_ocr_when_not_preferred(self):
        u = self._proc()
        u.prefer_dots_ocr = False
        u.dots_ocr.is_available = True
        u._docling.is_available = False  # docling unavailable -> skipped
        out = {"markdown": "dots last resort"}
        u.dots_ocr.process_pdf.return_value = out
        result = u.process("/doc.pdf")
        assert result is out
        u.dots_ocr.process_pdf.assert_called_once()

    def test_pdf_no_processor_returns_empty(self):
        u = self._proc()
        u.prefer_dots_ocr = True
        u.dots_ocr.is_available = False
        u._docling.is_available = False
        result = u.process("/doc.pdf")
        assert result["markdown"] == ""
        assert "No PDF processor available" in result["metadata"]["error"]

    def test_html_routes_to_docling(self):
        u = self._proc()
        out = {"markdown": "html"}
        u._docling.process_html.return_value = out
        with patch.object(mod.Path, "read_text", return_value="<html></html>"):
            result = u.process("/page.html")
        assert result is out
        u._docling.process_html.assert_called_once()

    def test_html_failure_returns_empty(self):
        u = self._proc()
        with patch.object(mod.Path, "read_text", side_effect=OSError("missing")):
            result = u.process("/page.html")
        assert result["markdown"] == ""
        assert "HTML processing failed" in result["metadata"]["error"]

    def test_unsupported_type_returns_empty(self):
        u = self._proc()
        result = u.process("/data.docx")
        assert result["markdown"] == ""
        assert "Unsupported file type" in result["metadata"]["error"]
        assert ".docx" in result["metadata"]["error"]

    def test_force_dots_ocr_success(self):
        u = self._proc()
        u.dots_ocr.is_available = True
        out = {"markdown": "forced dots"}
        u.dots_ocr.process_pdf.return_value = out
        result = u.process("/doc.pdf", force_engine="dots_ocr")
        assert result is out

    def test_force_dots_ocr_failure_returns_empty(self):
        u = self._proc()
        u.dots_ocr.is_available = False  # _try_dots_ocr returns None
        result = u.process("/doc.pdf", force_engine="dots_ocr")
        assert result["markdown"] == ""
        assert "dots_ocr forced but failed" in result["metadata"]["error"]

    def test_force_docling_routes_to_pdf(self):
        # force_engine="docling" routes to _try_docling_pdf for a PDF (the old
        # code called a non-existent self._try_docling and raised AttributeError).
        u = self._proc()
        u._docling.is_available = True
        u._docling.process_pdf.return_value = {"markdown": "forced docling"}
        result = u.process("/doc.pdf", force_engine="docling")
        assert result == {"markdown": "forced docling"}

    def test_force_docling_unavailable_returns_empty(self):
        # docling unavailable -> _try_docling_pdf returns None -> the
        # "docling forced but failed" empty result (no more AttributeError).
        u = self._proc()
        u._docling.is_available = False
        result = u.process("/doc.pdf", force_engine="docling")
        assert result["markdown"] == ""
        assert "docling forced but failed" in result["metadata"]["error"]


class TestUnifiedTryHelpers:
    def _proc(self):
        u = UnifiedDocumentProcessor()
        u.dots_ocr = MagicMock()
        u._docling = MagicMock()
        return u

    def test_try_dots_ocr_unavailable_returns_none(self):
        u = self._proc()
        u.dots_ocr.is_available = False
        assert u._try_dots_ocr("/doc.pdf") is None

    def test_try_dots_ocr_pdf_uses_process_pdf(self):
        u = self._proc()
        u.dots_ocr.is_available = True
        u.dots_ocr.process_pdf.return_value = {"markdown": "p"}
        assert u._try_dots_ocr("/doc.pdf") == {"markdown": "p"}
        u.dots_ocr.process_pdf.assert_called_once_with("/doc.pdf")
        u.dots_ocr.process_image.assert_not_called()

    def test_try_dots_ocr_image_uses_process_image(self):
        u = self._proc()
        u.dots_ocr.is_available = True
        u.dots_ocr.process_image.return_value = {"markdown": "i"}
        assert u._try_dots_ocr("/scan.png") == {"markdown": "i"}
        u.dots_ocr.process_image.assert_called_once_with("/scan.png")

    def test_try_dots_ocr_swallows_exception(self):
        u = self._proc()
        u.dots_ocr.is_available = True
        u.dots_ocr.process_pdf.side_effect = RuntimeError("boom")
        assert u._try_dots_ocr("/doc.pdf") is None

    def test_try_docling_pdf_unavailable_returns_none(self):
        u = self._proc()
        u._docling.is_available = False
        assert u._try_docling_pdf("/doc.pdf") is None

    def test_try_docling_pdf_swallows_exception(self):
        u = self._proc()
        u._docling.is_available = True
        u._docling.process_pdf.side_effect = ValueError("bad")
        assert u._try_docling_pdf("/doc.pdf") is None

    def test_try_docling_html_reads_and_processes(self):
        u = self._proc()
        u._docling.process_html.return_value = {"markdown": "h"}
        with patch.object(mod.Path, "read_text", return_value="<p>hi</p>") as rt:
            result = u._try_docling_html("/page.html")
        assert result == {"markdown": "h"}
        rt.assert_called_once_with(encoding="utf-8")
        u._docling.process_html.assert_called_once_with("<p>hi</p>", source_url="/page.html")

    def test_try_docling_html_swallows_exception(self):
        u = self._proc()
        with patch.object(mod.Path, "read_text", side_effect=OSError("nope")):
            assert u._try_docling_html("/page.html") is None


class TestEmptyResult:
    def test_shape_and_reason(self):
        u = UnifiedDocumentProcessor()
        result = u._empty_result("/x.pdf", "some reason")
        assert result == {
            "markdown": "",
            "tables": [],
            "layout": [],
            "metadata": {
                "source": "/x.pdf",
                "processor": "none",
                "error": "some reason",
            },
        }
