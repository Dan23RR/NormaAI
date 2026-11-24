"""Tests for src/reports/letterhead.py: the texts, the logo, what a PDF reads.

The logo tests build their images with Pillow in memory: a PNG with
transparency, a palette PNG, a JPEG from a phone with its EXIF (orientation,
GPS position), a CMYK JPEG, and files that are not what they say.
"""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from src.db.models import OrgLetterhead
from src.reports import letterhead
from src.reports.letterhead import Letterhead, LetterheadError, clean_texts, normalize_logo
from tests.documents_support import Database

# Characters built from their code points: a bidirectional override, a zero-width
# space, a no-break space, a line separator.
RLO = chr(0x202E)
ZWSP = chr(0x200B)
NBSP = chr(0xA0)
LINE_SEPARATOR = chr(0x2028)


def _image(fmt: str, size=(400, 120), mode="RGB", color=(10, 58, 156), **save) -> bytes:
    image = Image.new(mode, size, color)
    out = io.BytesIO()
    image.save(out, fmt, **save)
    return out.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# ─── Texts ───────────────────────────────────────────────────────────


class TestTexts:
    def test_clean_texts(self):
        texts = clean_texts(
            "  Studio   Rossi\t& Associati ",
            f"Via Roma 1{LINE_SEPARATOR}\r\n\n20121 Milano  ",
            f"tel. 02 1234567{NBSP}{NBSP}· info@studio.example",
            "Documento riservato.",
        )
        assert texts.name == "Studio Rossi & Associati"
        assert texts.address == "Via Roma 1\n20121 Milano"
        assert texts.contact == "tel. 02 1234567 · info@studio.example"
        assert texts.footer_note == "Documento riservato."

    def test_empty_optional_texts_are_none(self):
        texts = clean_texts("Studio Rossi", "  \n ", "", None)
        assert texts == letterhead.LetterheadText(name="Studio Rossi")

    def test_the_name_and_the_one_line_texts_have_no_line_breaks(self):
        texts = clean_texts("Studio\nRossi", None, "tel. 1\nemail", "riga uno\r\nriga due")
        assert texts.name == "Studio Rossi"
        assert texts.contact == "tel. 1 email"
        assert texts.footer_note == "riga uno riga due"

    def test_control_and_format_characters_are_dropped(self):
        texts = clean_texts(f"Studio {RLO}issoR{ZWSP}", "Via\x00 Roma\x07 1", None, None)
        assert texts.name == "Studio issoR"
        assert texts.address == "Via Roma 1"

    def test_accents_and_quotes_stay(self):
        texts = clean_texts("Studio «Città» d’Italia – è", None, None, None)
        assert texts.name == "Studio «Città» d’Italia – è"

    @pytest.mark.parametrize(
        ("fields", "detail"),
        [
            ({"name": "  "}, "Scrivi il nome dello studio."),
            ({"name": None}, "Scrivi il nome dello studio."),
            ({"name": "x" * 201}, "Il nome dello studio può avere al massimo 200 caratteri."),
            ({"address": "a\nb\nc\nd"}, "L'indirizzo può avere al massimo 3 righe."),
            ({"address": "a" * 301}, "L'indirizzo può avere al massimo 300 caratteri."),
            ({"contact": "c" * 201}, "La riga dei contatti può avere al massimo 200 caratteri."),
            (
                {"footer_note": "n" * 301},
                "La nota a piè di pagina può avere al massimo 300 caratteri.",
            ),
        ],
    )
    def test_refused(self, fields, detail):
        values = {"name": "Studio Rossi", "address": None, "contact": None, "footer_note": None}
        values.update(fields)
        with pytest.raises(LetterheadError) as error:
            clean_texts(**values)
        assert error.value.status_code == 422
        assert error.value.detail == detail

    def test_the_limits_count_what_is_kept(self):
        """Spaces collapsed and lines dropped do not count against the limits."""
        texts = clean_texts("x" * 200, "\n\n".join(["a" * 99] * 3), " " * 500 + "c", None)
        assert len(texts.name) == 200
        assert texts.address == "\n".join(["a" * 99] * 3)
        assert texts.contact == "c"


# ─── Logo ────────────────────────────────────────────────────────────


class TestLogo:
    def test_png_with_transparency_stays_png_with_its_alpha(self):
        data = _image("PNG", mode="RGBA", color=(10, 58, 156, 0))
        logo, media_type = normalize_logo(data)
        assert media_type == "image/png"
        with _open(logo) as image:
            assert image.format == "PNG" and image.mode == "RGBA" and image.size == (400, 120)
            assert image.getpixel((0, 0))[3] == 0

    def test_palette_png_with_transparency_becomes_rgba(self):
        image = Image.new("P", (64, 64), 0)
        out = io.BytesIO()
        image.save(out, "PNG", transparency=0)
        logo, media_type = normalize_logo(out.getvalue())
        assert media_type == "image/png"
        with _open(logo) as stored:
            assert stored.mode == "RGBA"

    def test_jpeg_from_a_phone_loses_its_metadata_and_stands_upright(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: rotate 90 degrees clockwise to show
        exif[0x8825] = {1: "N", 2: (45.0, 28.0, 0.0)}  # GPS: a position
        exif[0x010F] = "PhoneMaker"
        data = _image("JPEG", size=(300, 100), exif=exif.tobytes())
        logo, media_type = normalize_logo(data)
        assert media_type == "image/jpeg"
        with _open(logo) as image:
            assert image.format == "JPEG"
            assert image.size == (100, 300)  # turned as the EXIF said
            assert not image.getexif()
            assert "exif" not in image.info
        assert b"PhoneMaker" not in logo

    def test_cmyk_jpeg_becomes_rgb(self):
        logo, media_type = normalize_logo(_image("JPEG", mode="CMYK", color=(0, 80, 160, 0)))
        assert media_type == "image/jpeg"
        with _open(logo) as image:
            assert image.mode == "RGB"

    def test_a_large_logo_is_made_smaller(self):
        logo, _ = normalize_logo(_image("PNG", size=(3000, 1500)))
        with _open(logo) as image:
            assert image.size == (letterhead.LOGO_MAX_SIDE, letterhead.LOGO_MAX_SIDE // 2)

    def test_png_text_chunks_are_not_kept(self):
        from PIL import PngImagePlugin

        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", "segreto del cliente")
        logo, _ = normalize_logo(_image("PNG", pnginfo=info))
        assert b"segreto" not in logo

    @pytest.mark.parametrize("fmt", ["GIF", "BMP", "TIFF", "WEBP"])
    def test_other_image_types_are_refused(self, fmt):
        with pytest.raises(LetterheadError) as error:
            normalize_logo(_image(fmt, size=(64, 64)))
        assert error.value.status_code == 415
        assert error.value.detail == "Il logo deve essere un'immagine PNG o JPEG."

    def test_a_file_that_is_not_an_image_is_refused(self):
        with pytest.raises(LetterheadError) as error:
            normalize_logo(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        assert error.value.status_code == 415

    def test_an_empty_file_is_refused(self):
        with pytest.raises(LetterheadError) as error:
            normalize_logo(b"")
        assert (error.value.status_code, error.value.detail) == (422, "Il file del logo è vuoto.")

    def test_a_file_too_heavy_is_refused_before_it_is_read(self):
        with pytest.raises(LetterheadError) as error:
            normalize_logo(b"\x89PNG" + b"0" * letterhead.LOGO_MAX_BYTES)
        assert error.value.status_code == 413
        assert error.value.detail == "Il logo supera 2 MB: usa un file più leggero."

    def test_too_many_pixels_are_refused_before_decoding(self, monkeypatch):
        from PIL import ImageFile

        data = _image("PNG", size=(letterhead.LOGO_MAX_INPUT_SIDE + 1, 16))
        decoded = []
        monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: decoded.append(self))
        with pytest.raises(LetterheadError) as error:
            normalize_logo(data)
        assert error.value.status_code == 422
        assert "al massimo 6000 pixel per lato" in error.value.detail
        assert decoded == []

    def test_too_small_is_refused(self):
        with pytest.raises(LetterheadError) as error:
            normalize_logo(_image("PNG", size=(8, 8)))
        assert error.value.detail == "Il logo è troppo piccolo: servono almeno 16 pixel per lato."

    def test_a_truncated_file_is_refused(self):
        data = _image("PNG", size=(400, 400))
        with pytest.raises(LetterheadError) as error:
            normalize_logo(data[: len(data) // 2])
        assert error.value.status_code == 422
        assert error.value.detail.startswith("Il file del logo non si legge")

    def test_logo_size(self):
        logo, _ = normalize_logo(_image("PNG", size=(400, 120)))
        assert letterhead.logo_size(logo) == (400, 120)


# ─── What a PDF reads ────────────────────────────────────────────────


class TestLoad:
    async def test_without_a_letterhead_the_name_of_the_organisation(self):
        db = Database()
        org = db.add_org("Studio Bianchi")
        async with db.session(org_id=str(org)) as session:
            found = await letterhead.load(session, org)
        assert found == Letterhead(name="Studio Bianchi")
        assert letterhead.letterhead_object(found) == {
            "configured": False,
            "name": "Studio Bianchi",
            "address": None,
            "contact": None,
            "footer_note": None,
            "logo": None,
            "updated_at": None,
        }

    async def test_the_stored_letterhead_of_the_organisation(self):
        db = Database()
        org, other = db.add_org("Studio Bianchi"), db.add_org("Studio Verdi")
        logo, logo_type = normalize_logo(_image("PNG"))
        with db.sync_session() as session:
            session.add(
                OrgLetterhead(
                    org_id=org,
                    name="Studio Bianchi Avvocati",
                    address="Via Po 3\nTorino",
                    contact="info@bianchi.example",
                    footer_note="Riservato",
                    logo=logo,
                    logo_type=logo_type,
                )
            )
            session.commit()
        async with db.session(org_id=str(org)) as session:
            found = await letterhead.load(session, org)
        assert found.configured and found.name == "Studio Bianchi Avvocati"
        assert found.address_lines == ["Via Po 3", "Torino"]
        assert found.logo == logo and found.logo_type == "image/png"
        body = letterhead.letterhead_object(found)
        assert body["logo"] == {"content_type": "image/png", "size": len(logo)}
        assert body["updated_at"]
        async with db.session(org_id=str(other)) as session:
            assert await letterhead.load(session, other) == Letterhead(name="Studio Verdi")

    async def test_an_unknown_organisation_has_an_empty_name(self):
        db = Database()
        async with db.session() as session:
            assert (await letterhead.load(session, uuid.uuid4())).name == ""
