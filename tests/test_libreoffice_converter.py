"""Unit tests for the LibreOffice headless DOC/DOCX/RTF/ODT -> PDF converter.

Target module: src/nlp/processing/libreoffice_converter.py

The module is a thin, stateless subprocess wrapper around
`soffice --headless --convert-to pdf`. These tests exercise it WITHOUT any
real LibreOffice binary, real subprocess, or real network/LLM/DB:

- `subprocess.run` is patched where it is imported
  (`...libreoffice_converter.subprocess.run`) for every path that would
  otherwise spawn `soffice`.
- `shutil.which` is patched for the availability check.
- Real temp directories (via the genuine `tempfile`) are used so that file
  I/O paths (`write_bytes`, `read_bytes`, `rmtree`) are exercised against the
  filesystem, but the "conversion" itself is faked by having the patched
  `subprocess.run` materialise the expected output PDF.

Covered behaviour:
- command construction (exact argv passed to soffice)
- success path (bytes round-trip, on-disk path)
- non-zero exit -> ConversionError
- timeout -> ConversionError
- missing binary -> LibreOfficeNotAvailableError / FileNotFoundError mapping
- "claimed success but no PDF" -> ConversionError
- format detection / validation (supported, unsupported, suffix normalisation)
- idempotency / empty-content / missing-file guards
- the soft (`safe_*`) wrapper swallowing each error class into None
- temp-dir cleanup vs. cleanup=False

Run:
    pytest tests/test_libreoffice_converter.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.nlp.processing import libreoffice_converter as lo
from src.nlp.processing.libreoffice_converter import (
    SUPPORTED_INPUT_FORMATS,
    ConversionError,
    LibreOfficeNotAvailableError,
    convert_file_to_pdf,
    convert_to_pdf,
    libreoffice_available,
    safe_convert_to_pdf,
)

# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

PDF_MAGIC = b"%PDF-1.7\nfake-pdf-body\n%%EOF"


def _ok_proc(stderr: str = "") -> MagicMock:
    """A CompletedProcess-like stub representing a clean soffice run."""
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "convert ... -> ... using filter"
    proc.stderr = stderr
    return proc


def _fail_proc(returncode: int = 1, stderr: str = "boom") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = ""
    proc.stderr = stderr
    return proc


def _make_run_writing_pdf(captured: dict, *, stem: str | None = None):
    """Build a fake `subprocess.run` that writes the expected output PDF.

    The real `_run_soffice` computes the output path as
    `<outdir>/<input_stem>.pdf`. To emulate a successful conversion we parse
    the argv we are handed, find `--outdir <dir>` and the trailing input path,
    and drop a PDF where the code will look for it.
    """

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        input_path = Path(cmd[-1])
        out_stem = stem if stem is not None else input_path.stem
        (outdir / f"{out_stem}.pdf").write_bytes(PDF_MAGIC)
        return _ok_proc()

    return _fake_run


# --------------------------------------------------------------------------- #
#  libreoffice_available / format-detection constants                         #
# --------------------------------------------------------------------------- #


def test_libreoffice_available_true_when_which_finds_binary():
    with patch.object(lo.shutil, "which", return_value="/usr/bin/soffice") as which:
        assert libreoffice_available() is True
    which.assert_called_once_with(lo.LIBREOFFICE_BIN)


def test_libreoffice_available_false_when_which_returns_none():
    with patch.object(lo.shutil, "which", return_value=None):
        assert libreoffice_available() is False


def test_supported_formats_are_the_documented_set():
    # Guards against accidental format-list drift; these are the formats the
    # docstring/Docling pipeline promises to accept.
    assert {"doc", "docx", "rtf", "odt", "ott", "txt"} == SUPPORTED_INPUT_FORMATS


# --------------------------------------------------------------------------- #
#  _run_soffice: command construction                                         #
# --------------------------------------------------------------------------- #


def test_run_soffice_builds_expected_command(tmp_path):
    captured: dict = {}
    input_path = tmp_path / "policy.docx"
    input_path.write_bytes(b"docx-bytes")

    with patch.object(lo.subprocess, "run", side_effect=_make_run_writing_pdf(captured)):
        out = lo._run_soffice(input_path, tmp_path)

    cmd = captured["cmd"]
    # Binary first, conversion flags present and in the documented order.
    assert cmd[0] == lo.LIBREOFFICE_BIN
    assert cmd[1:5] == ["--headless", "--norestore", "--nolockcheck", "--convert-to"]
    assert cmd[5] == "pdf"
    assert cmd[6] == "--outdir"
    assert cmd[7] == str(tmp_path)
    assert cmd[8] == str(input_path)
    # Output path matches <outdir>/<stem>.pdf and really exists on disk.
    assert out == tmp_path / "policy.pdf"
    assert out.read_bytes() == PDF_MAGIC


def test_run_soffice_uses_safe_subprocess_options(tmp_path):
    captured: dict = {}
    input_path = tmp_path / "x.docx"
    input_path.write_bytes(b"data")

    with patch.object(lo.subprocess, "run", side_effect=_make_run_writing_pdf(captured)):
        lo._run_soffice(input_path, tmp_path)

    kwargs = captured["kwargs"]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert kwargs["timeout"] == lo.LIBREOFFICE_TIMEOUT


# --------------------------------------------------------------------------- #
#  _run_soffice: error handling                                               #
# --------------------------------------------------------------------------- #


def test_run_soffice_nonzero_exit_raises_conversion_error(tmp_path):
    input_path = tmp_path / "bad.docx"
    input_path.write_bytes(b"data")

    with (
        patch.object(lo.subprocess, "run", return_value=_fail_proc(3, "filter error")),
        pytest.raises(ConversionError) as exc,
    ):
        lo._run_soffice(input_path, tmp_path)
    assert "3" in str(exc.value)
    assert "filter error" in str(exc.value)


def test_run_soffice_timeout_raises_conversion_error(tmp_path):
    input_path = tmp_path / "slow.docx"
    input_path.write_bytes(b"data")

    err = subprocess.TimeoutExpired(cmd="soffice", timeout=lo.LIBREOFFICE_TIMEOUT)
    with (
        patch.object(lo.subprocess, "run", side_effect=err),
        pytest.raises(ConversionError) as exc,
    ):
        lo._run_soffice(input_path, tmp_path)
    assert "timeout" in str(exc.value).lower()
    assert str(lo.LIBREOFFICE_TIMEOUT) in str(exc.value)


def test_run_soffice_missing_binary_raises_not_available(tmp_path):
    input_path = tmp_path / "x.docx"
    input_path.write_bytes(b"data")

    with (
        patch.object(lo.subprocess, "run", side_effect=FileNotFoundError("no soffice")),
        pytest.raises(LibreOfficeNotAvailableError) as exc,
    ):
        lo._run_soffice(input_path, tmp_path)
    assert lo.LIBREOFFICE_BIN in str(exc.value)


def test_run_soffice_success_but_no_pdf_raises_conversion_error(tmp_path):
    """soffice returns 0 yet writes no PDF -> the code must not lie about success."""
    input_path = tmp_path / "ghost.docx"
    input_path.write_bytes(b"data")

    # returncode 0 but we DON'T create the output file.
    with (
        patch.object(lo.subprocess, "run", return_value=_ok_proc()),
        pytest.raises(ConversionError) as exc,
    ):
        lo._run_soffice(input_path, tmp_path)
    assert "not found" in str(exc.value).lower()
    assert "ghost.pdf" in str(exc.value)


# --------------------------------------------------------------------------- #
#  convert_file_to_pdf                                                         #
# --------------------------------------------------------------------------- #


def test_convert_file_to_pdf_happy_path(tmp_path):
    captured: dict = {}
    src = tmp_path / "report.docx"
    src.write_bytes(b"docx")

    with patch.object(lo.subprocess, "run", side_effect=_make_run_writing_pdf(captured)):
        out = convert_file_to_pdf(src)

    assert out == tmp_path / "report.pdf"
    assert out.exists()
    # Output dir defaults to the input file's parent.
    assert captured["cmd"][captured["cmd"].index("--outdir") + 1] == str(tmp_path)


def test_convert_file_to_pdf_accepts_str_path(tmp_path):
    captured: dict = {}
    src = tmp_path / "memo.odt"
    src.write_bytes(b"odt")

    with patch.object(lo.subprocess, "run", side_effect=_make_run_writing_pdf(captured)):
        out = convert_file_to_pdf(str(src))

    assert isinstance(out, Path)
    assert out == tmp_path / "memo.pdf"


def test_convert_file_to_pdf_missing_file_raises(tmp_path):
    missing = tmp_path / "nope.docx"
    with (
        patch.object(lo.subprocess, "run") as run,
        pytest.raises(FileNotFoundError),
    ):
        convert_file_to_pdf(missing)
    run.assert_not_called()


def test_convert_file_to_pdf_unsupported_format_raises(tmp_path):
    src = tmp_path / "data.xlsx"
    src.write_bytes(b"junk")
    with (
        patch.object(lo.subprocess, "run") as run,
        pytest.raises(ValueError) as exc,
    ):
        convert_file_to_pdf(src)
    assert "xlsx" in str(exc.value)
    run.assert_not_called()


def test_convert_file_to_pdf_suffix_is_case_insensitive(tmp_path):
    captured: dict = {}
    src = tmp_path / "UPPER.DOCX"
    src.write_bytes(b"docx")

    with patch.object(lo.subprocess, "run", side_effect=_make_run_writing_pdf(captured)):
        out = convert_file_to_pdf(src)
    # stem preserves original casing; conversion still proceeds.
    assert out == tmp_path / "UPPER.pdf"


# --------------------------------------------------------------------------- #
#  convert_to_pdf (in-memory bytes round-trip)                                #
# --------------------------------------------------------------------------- #


def test_convert_to_pdf_returns_pdf_bytes(tmp_path):
    captured: dict = {}
    # mkdtemp creates "input.<fmt>", so the stem is always "input".
    fake_run = _make_run_writing_pdf(captured, stem="input")

    with patch.object(lo.subprocess, "run", side_effect=fake_run):
        result = convert_to_pdf(b"some-docx-bytes", "docx")

    assert result == PDF_MAGIC
    # The temp input file was named input.docx and fed to soffice.
    assert captured["cmd"][-1].endswith("input.docx")


def test_convert_to_pdf_empty_content_raises():
    with (
        patch.object(lo.subprocess, "run") as run,
        pytest.raises(ValueError) as exc,
    ):
        convert_to_pdf(b"", "docx")
    assert "empty" in str(exc.value).lower()
    run.assert_not_called()


def test_convert_to_pdf_unsupported_format_raises():
    with (
        patch.object(lo.subprocess, "run") as run,
        pytest.raises(ValueError) as exc,
    ):
        convert_to_pdf(b"data", "pages")
    assert "pages" in str(exc.value)
    run.assert_not_called()


def test_convert_to_pdf_normalises_leading_dot_in_format(tmp_path):
    captured: dict = {}
    fake_run = _make_run_writing_pdf(captured, stem="input")
    with patch.object(lo.subprocess, "run", side_effect=fake_run):
        result = convert_to_pdf(b"data", ".RTF")
    assert result == PDF_MAGIC
    # ".RTF" -> "rtf"; temp input file is input.rtf
    assert captured["cmd"][-1].endswith("input.rtf")


def test_convert_to_pdf_cleans_up_tempdir_by_default(tmp_path):
    captured: dict = {}
    fake_run = _make_run_writing_pdf(captured, stem="input")
    created_dirs: list[str] = []

    real_mkdtemp = lo.tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(d)
        return d

    with (
        patch.object(lo.subprocess, "run", side_effect=fake_run),
        patch.object(lo.tempfile, "mkdtemp", side_effect=_tracking_mkdtemp),
    ):
        convert_to_pdf(b"data", "docx", cleanup=True)

    assert created_dirs, "expected a temp dir to be created"
    assert not Path(created_dirs[0]).exists()  # removed by finally/cleanup


def test_convert_to_pdf_keeps_tempdir_when_cleanup_false(tmp_path):
    captured: dict = {}
    fake_run = _make_run_writing_pdf(captured, stem="input")
    created_dirs: list[str] = []

    real_mkdtemp = lo.tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(d)
        return d

    try:
        with (
            patch.object(lo.subprocess, "run", side_effect=fake_run),
            patch.object(lo.tempfile, "mkdtemp", side_effect=_tracking_mkdtemp),
        ):
            convert_to_pdf(b"data", "docx", cleanup=False)

        assert created_dirs
        leftover = Path(created_dirs[0])
        assert leftover.exists()
        assert (leftover / "input.pdf").exists()
    finally:
        # Test-side cleanup so we don't litter the temp area.
        for d in created_dirs:
            lo.shutil.rmtree(d, ignore_errors=True)


def test_convert_to_pdf_propagates_conversion_error_and_cleans_up(tmp_path):
    created_dirs: list[str] = []
    real_mkdtemp = lo.tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(d)
        return d

    with (
        patch.object(lo.subprocess, "run", return_value=_fail_proc(2, "nope")),
        patch.object(lo.tempfile, "mkdtemp", side_effect=_tracking_mkdtemp),
        pytest.raises(ConversionError),
    ):
        convert_to_pdf(b"data", "docx")

    # Even on failure the finally-block must wipe the temp dir.
    assert created_dirs
    assert not Path(created_dirs[0]).exists()


# --------------------------------------------------------------------------- #
#  safe_convert_to_pdf (never-raises wrapper)                                  #
# --------------------------------------------------------------------------- #


def test_safe_convert_returns_bytes_on_success():
    with patch.object(lo, "convert_to_pdf", return_value=PDF_MAGIC) as inner:
        assert safe_convert_to_pdf(b"data", "docx") == PDF_MAGIC
    inner.assert_called_once_with(b"data", "docx")


def test_safe_convert_returns_none_on_not_available():
    with patch.object(lo, "convert_to_pdf", side_effect=LibreOfficeNotAvailableError("missing")):
        assert safe_convert_to_pdf(b"data", "docx") is None


def test_safe_convert_returns_none_on_conversion_error():
    with patch.object(lo, "convert_to_pdf", side_effect=ConversionError("boom")):
        assert safe_convert_to_pdf(b"data", "docx") is None


def test_safe_convert_returns_none_on_value_error():
    with patch.object(lo, "convert_to_pdf", side_effect=ValueError("bad format")):
        assert safe_convert_to_pdf(b"data", "xyz") is None


def test_safe_convert_does_not_swallow_unexpected_errors():
    # Only the documented exception classes are caught; a programming error
    # (e.g. KeyError) must still surface.
    with (
        patch.object(lo, "convert_to_pdf", side_effect=KeyError("unexpected")),
        pytest.raises(KeyError),
    ):
        safe_convert_to_pdf(b"data", "docx")


# --------------------------------------------------------------------------- #
#  Parametrised format acceptance                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fmt", sorted(SUPPORTED_INPUT_FORMATS))
def test_convert_to_pdf_accepts_every_supported_format(fmt):
    captured: dict = {}
    fake_run = _make_run_writing_pdf(captured, stem="input")
    with patch.object(lo.subprocess, "run", side_effect=fake_run):
        result = convert_to_pdf(b"payload", fmt)
    assert result == PDF_MAGIC
    assert captured["cmd"][-1].endswith(f"input.{fmt}")
