"""The letterhead of an organisation: what heads the PDFs it hands to its clients.

An admin writes it in the settings (``src/api/routers/letterhead.py``); the PDF
of a document check (``src/document_check/pdf.py``) reads it with ``load``.
Without a letterhead the PDF carries the name of the organisation only.

Texts. The name of the practice (one line, required, at most 200 characters),
the address (at most 3 lines and 300 characters), one line of contacts (at
most 200) and a note for the foot of every page (one line, at most 300).
Control and format characters are dropped (a bidirectional override could make
the printed name read otherwise than it was typed), spaces are collapsed, and
an optional text left empty is stored as NULL.

Logo. A PNG or a JPEG of at most ``LOGO_MAX_BYTES``, recognised by its content
and not by its name. Before anything is decoded its size is read from the
header and refused above ``LOGO_MAX_INPUT_SIDE`` pixels a side or
``LOGO_MAX_INPUT_PIXELS`` in all, so a small file that would unpack into a huge
image is never unpacked. The image is then encoded again, at most
``LOGO_MAX_SIDE`` pixels a side: what is stored carries none of the metadata of
the file (EXIF, the GPS position of a phone, comments), and a file shaped to
upset a decoder never reaches the PDF library.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from src.db.models import Organization, OrgLetterhead

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

NAME_MAX_CHARS = 200
ADDRESS_MAX_CHARS = 300
ADDRESS_MAX_LINES = 3
CONTACT_MAX_CHARS = 200
FOOTER_MAX_CHARS = 300

LOGO_MAX_BYTES = 2 * 1024 * 1024
LOGO_MAX_INPUT_SIDE = 6000
LOGO_MAX_INPUT_PIXELS = 25_000_000
LOGO_MIN_SIDE = 16
# What is stored: enough for a logo 8 cm wide at 300 dpi.
LOGO_MAX_SIDE = 1000
LOGO_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg"}


class LetterheadError(Exception):
    """A letterhead or a logo refused, with the HTTP status and the Italian sentence to show."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# ─── Texts ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LetterheadText:
    """The four texts of a letterhead, cleaned."""

    name: str
    address: str | None = None
    contact: str | None = None
    footer_note: str | None = None


_LINE_BREAKS = re.compile(r"\r\n|[\r\n\u2028\u2029\x0b\x0c\x85]")
_SPACES = re.compile(r"[ \t\u00a0]+")


def _clean_line(text: str) -> str:
    """One line: no control or format characters, single spaces, no spaces at the ends."""
    kept = "".join(
        " " if ch == "\t" else ch
        for ch in unicodedata.normalize("NFC", text)
        if ch == "\t" or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    return _SPACES.sub(" ", kept).strip()


def _lines(text: str | None) -> list[str]:
    """The non-empty lines of a text, each cleaned."""
    if not text:
        return []
    return [line for line in (_clean_line(part) for part in _LINE_BREAKS.split(text)) if line]


def _one_line(text: str | None) -> str:
    return " ".join(_lines(text))


def clean_texts(
    name: str | None,
    address: str | None = None,
    contact: str | None = None,
    footer_note: str | None = None,
) -> LetterheadText:
    """The texts as stored, or ``LetterheadError`` (422) with what to change."""
    clean_name = _one_line(name)
    if not clean_name:
        raise LetterheadError(422, "Scrivi il nome dello studio.")
    if len(clean_name) > NAME_MAX_CHARS:
        raise LetterheadError(
            422, f"Il nome dello studio può avere al massimo {NAME_MAX_CHARS} caratteri."
        )
    address_lines = _lines(address)
    if len(address_lines) > ADDRESS_MAX_LINES:
        raise LetterheadError(422, f"L'indirizzo può avere al massimo {ADDRESS_MAX_LINES} righe.")
    clean_address = "\n".join(address_lines)
    if len(clean_address) > ADDRESS_MAX_CHARS:
        raise LetterheadError(
            422, f"L'indirizzo può avere al massimo {ADDRESS_MAX_CHARS} caratteri."
        )
    clean_contact = _one_line(contact)
    if len(clean_contact) > CONTACT_MAX_CHARS:
        raise LetterheadError(
            422, f"La riga dei contatti può avere al massimo {CONTACT_MAX_CHARS} caratteri."
        )
    clean_footer = _one_line(footer_note)
    if len(clean_footer) > FOOTER_MAX_CHARS:
        raise LetterheadError(
            422, f"La nota a piè di pagina può avere al massimo {FOOTER_MAX_CHARS} caratteri."
        )
    return LetterheadText(
        name=clean_name,
        address=clean_address or None,
        contact=clean_contact or None,
        footer_note=clean_footer or None,
    )


# ─── Logo ────────────────────────────────────────────────────────────


def logo_too_large() -> LetterheadError:
    return LetterheadError(
        413, f"Il logo supera {LOGO_MAX_BYTES // (1024 * 1024)} MB: usa un file più leggero."
    )


def _unreadable() -> LetterheadError:
    return LetterheadError(
        422, "Il file del logo non si legge: prova a salvarlo di nuovo come PNG o JPEG."
    )


def normalize_logo(data: bytes) -> tuple[bytes, str]:
    """The logo as stored and its media type, or ``LetterheadError`` with what is wrong."""
    if not data:
        raise LetterheadError(422, "Il file del logo è vuoto.")
    if len(data) > LOGO_MAX_BYTES:
        raise logo_too_large()
    try:
        image = Image.open(io.BytesIO(data), formats=tuple(LOGO_TYPES))
    except UnidentifiedImageError:
        raise LetterheadError(415, "Il logo deve essere un'immagine PNG o JPEG.") from None
    except (OSError, SyntaxError, ValueError):
        raise _unreadable() from None
    with image:
        # A phone's JPEG with a second picture inside opens as MPO: still a JPEG.
        fmt = "JPEG" if image.format == "MPO" else str(image.format)
        if fmt not in LOGO_TYPES:
            raise LetterheadError(415, "Il logo deve essere un'immagine PNG o JPEG.")
        width, height = image.size
        if max(width, height) > LOGO_MAX_INPUT_SIDE or width * height > LOGO_MAX_INPUT_PIXELS:
            raise LetterheadError(
                422,
                f"Il logo è troppo grande: al massimo {LOGO_MAX_INPUT_SIDE} pixel per lato. "
                "Riducilo e caricalo di nuovo.",
            )
        if min(width, height) < LOGO_MIN_SIDE:
            raise LetterheadError(
                422, f"Il logo è troppo piccolo: servono almeno {LOGO_MIN_SIDE} pixel per lato."
            )
        try:
            image.load()
            encoded = _encode(image, fmt)
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            raise _unreadable() from None
    return encoded, LOGO_TYPES[fmt]


def _encode(image: Image.Image, fmt: str) -> bytes:
    """A new file of the image: turned as its EXIF says, no metadata, at most LOGO_MAX_SIDE."""
    upright = ImageOps.exif_transpose(image) or image
    transparent = upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info
    if fmt == "JPEG":
        picture = upright if upright.mode in ("RGB", "L") else upright.convert("RGB")
    elif transparent:
        picture = upright if upright.mode == "RGBA" else upright.convert("RGBA")
    else:
        picture = upright if upright.mode in ("RGB", "L") else upright.convert("RGB")
    if picture is image:
        picture = image.copy()
    picture.thumbnail((LOGO_MAX_SIDE, LOGO_MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    if fmt == "JPEG":
        picture.save(out, "JPEG", quality=90, optimize=True)
    else:
        picture.save(out, "PNG", optimize=True)
    return out.getvalue()


def logo_size(data: bytes) -> tuple[int, int]:
    """Width and height in pixels of a stored logo."""
    with Image.open(io.BytesIO(data), formats=tuple(LOGO_TYPES)) as image:
        return image.size


# ─── What a PDF reads ────────────────────────────────────────────────


@dataclass(frozen=True)
class Letterhead:
    """The letterhead a PDF is headed with: the stored one, or the organisation's name."""

    name: str
    address: str | None = None
    contact: str | None = None
    footer_note: str | None = None
    logo: bytes | None = None
    logo_type: str | None = None
    configured: bool = False
    updated_at: datetime | None = None

    @property
    def address_lines(self) -> list[str]:
        return self.address.split("\n") if self.address else []


def from_row(row: OrgLetterhead) -> Letterhead:
    return Letterhead(
        name=row.name,
        address=row.address,
        contact=row.contact,
        footer_note=row.footer_note,
        logo=row.logo or None,
        logo_type=row.logo_type if row.logo else None,
        configured=True,
        updated_at=row.updated_at,
    )


async def load_row(session: Any, org_id: uuid.UUID) -> OrgLetterhead | None:
    result = await session.execute(select(OrgLetterhead).where(OrgLetterhead.org_id == org_id))
    row: OrgLetterhead | None = result.scalars().first()
    return row


async def organisation_name(session: Any, org_id: uuid.UUID) -> str:
    result = await session.execute(select(Organization.name).where(Organization.id == org_id))
    return str(result.scalar_one_or_none() or "")


async def load(session: Any, org_id: uuid.UUID) -> Letterhead:
    """The organisation's letterhead; without one, its name and nothing else."""
    row = await load_row(session, org_id)
    if row is not None:
        return from_row(row)
    return Letterhead(name=await organisation_name(session, org_id))


def letterhead_object(letterhead: Letterhead) -> dict[str, Any]:
    """The answer of ``GET /organization/letterhead``: everything but the logo's bytes."""
    updated_at = letterhead.updated_at
    if updated_at is not None and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)  # stored in UTC; SQLite drops the zone
    return {
        "configured": letterhead.configured,
        "name": letterhead.name,
        "address": letterhead.address,
        "contact": letterhead.contact,
        "footer_note": letterhead.footer_note,
        "logo": (
            {"content_type": letterhead.logo_type, "size": len(letterhead.logo)}
            if letterhead.logo
            else None
        ),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
