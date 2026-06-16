"""LibreOffice headless converter for DOC/DOCX/RTF/ODT → PDF.

Inspired by Mike OSS (willchen96/mike) which uses LibreOffice for legal
document conversion in their upload pipeline. Adopted here because:

1. NormaAI's Docling + dots.ocr handle PDF well but DOC/DOCX native is
   rougher (DOCX = XML zip, DOC = binary OLE — Docling does DOCX but
   misses styles; for legal text fidelity matters).
2. LibreOffice headless is industry-standard for server-side conversion
   and runs in Docker.
3. Once converted to PDF, the existing Docling pipeline applies cleanly.

This module is intentionally minimal: subprocess wrapper around
`soffice --headless --convert-to pdf`. No state, idempotent, fail-safe.

Prerequisites (Docker layer or host):
    apt-get install -y libreoffice-core libreoffice-writer fonts-liberation

Env vars:
    LIBREOFFICE_BIN     (default: `soffice` — must be in PATH)
    LIBREOFFICE_TIMEOUT (default: 60s per document)

Usage:
    from src.nlp.processing.libreoffice_converter import convert_to_pdf

    pdf_bytes = convert_to_pdf(docx_bytes, source_format='docx')
    # or
    pdf_path = convert_file_to_pdf('/tmp/policy.docx')
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


SUPPORTED_INPUT_FORMATS = {"doc", "docx", "rtf", "odt", "ott", "txt"}
LIBREOFFICE_BIN = os.environ.get("LIBREOFFICE_BIN", "soffice").strip() or "soffice"
LIBREOFFICE_TIMEOUT = int(os.environ.get("LIBREOFFICE_TIMEOUT", "60"))


class LibreOfficeNotAvailableError(RuntimeError):
    """Raised when soffice binary is missing or not executable."""


class ConversionError(RuntimeError):
    """Raised when LibreOffice conversion fails or times out."""


def libreoffice_available() -> bool:
    """Quick check: is soffice in PATH and executable?

    Returns True if available, False otherwise. No exception raised —
    callers can fall back to other processors gracefully.
    """
    return shutil.which(LIBREOFFICE_BIN) is not None


def _run_soffice(input_path: Path, output_dir: Path) -> Path:
    """Invoke `soffice --headless --convert-to pdf` and return output PDF path.

    Raises ConversionError on non-zero exit, missing output, or timeout.
    """
    cmd = [
        LIBREOFFICE_BIN,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(input_path),
    ]
    logger.info(
        "libreoffice_convert_start",
        input=input_path.name,
        outdir=str(output_dir),
        timeout=LIBREOFFICE_TIMEOUT,
    )
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=LIBREOFFICE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("libreoffice_timeout", input=input_path.name, timeout=LIBREOFFICE_TIMEOUT)
        raise ConversionError(f"LibreOffice timeout after {LIBREOFFICE_TIMEOUT}s")
    except FileNotFoundError:
        raise LibreOfficeNotAvailableError(
            f"LibreOffice binary not found in PATH: {LIBREOFFICE_BIN}. "
            f"Install with: apt-get install libreoffice-core libreoffice-writer"
        )

    if proc.returncode != 0:
        logger.error(
            "libreoffice_failed",
            returncode=proc.returncode,
            stderr=proc.stderr[:500],
            input=input_path.name,
        )
        raise ConversionError(f"LibreOffice returned {proc.returncode}: {proc.stderr[:300]}")

    # LibreOffice writes to <outdir>/<input_stem>.pdf
    output_pdf = output_dir / f"{input_path.stem}.pdf"
    if not output_pdf.exists():
        raise ConversionError(f"LibreOffice claimed success but PDF not found at {output_pdf}")

    logger.info(
        "libreoffice_convert_ok",
        input=input_path.name,
        output_size_bytes=output_pdf.stat().st_size,
    )
    return output_pdf


def convert_file_to_pdf(input_path: str | Path) -> Path:
    """Convert a file on disk to PDF in the same directory (or temp).

    Returns the Path to the produced PDF. Caller is responsible for
    cleaning up if input was in a temp location.

    Raises:
        LibreOfficeNotAvailableError: soffice not found
        ConversionError: conversion failed
        ValueError: unsupported input format
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = input_path.suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_INPUT_FORMATS:
        raise ValueError(
            f"Unsupported input format '.{suffix}'. "
            f"Supported: {sorted(SUPPORTED_INPUT_FORMATS)}"
        )

    # If already PDF, no-op (idempotent)
    if suffix == "pdf":
        return input_path

    output_dir = input_path.parent
    return _run_soffice(input_path, output_dir)


def convert_to_pdf(
    content: bytes,
    source_format: str,
    *,
    cleanup: bool = True,
) -> bytes:
    """Convert in-memory bytes (DOC/DOCX/RTF/ODT/TXT) to PDF bytes.

    Writes the content to a temp file, runs soffice, reads the resulting
    PDF, and (by default) cleans up the temp directory.

    Args:
        content: file bytes
        source_format: 'doc' | 'docx' | 'rtf' | 'odt' | 'txt'
        cleanup: if True, remove temp dir after conversion (default True)

    Returns:
        PDF as bytes
    """
    if not content:
        raise ValueError("Empty content")

    fmt = source_format.lower().lstrip(".")
    if fmt not in SUPPORTED_INPUT_FORMATS:
        raise ValueError(
            f"Unsupported source_format '{fmt}'. " f"Supported: {sorted(SUPPORTED_INPUT_FORMATS)}"
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="normaai_loconv_"))
    try:
        input_path = tmpdir / f"input.{fmt}"
        input_path.write_bytes(content)

        output_pdf = _run_soffice(input_path, tmpdir)
        return output_pdf.read_bytes()
    finally:
        if cleanup:
            shutil.rmtree(tmpdir, ignore_errors=True)


def safe_convert_to_pdf(
    content: bytes,
    source_format: str,
) -> bytes | None:
    """Same as `convert_to_pdf` but returns None on failure instead of raising.

    Useful in pipeline contexts where LibreOffice availability is best-effort
    and a fallback path (e.g. docling raw DOCX) is acceptable.

    Returns:
        PDF bytes on success, None on any failure (logged at WARNING level)
    """
    try:
        return convert_to_pdf(content, source_format)
    except LibreOfficeNotAvailableError as e:
        logger.warning("libreoffice_unavailable_fallback", error=str(e))
        return None
    except (ConversionError, ValueError, FileNotFoundError) as e:
        logger.warning(
            "libreoffice_convert_soft_fail",
            error=str(e)[:200],
            source_format=source_format,
        )
        return None
