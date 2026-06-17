"""Generate frontend/public/og-image.png (1200x630, OpenGraph/Twitter card).

Warm-paper editorial theme - mirrors the public landing (tailwind tokens
paper/night/clay). Re-run after copy or palette changes:
    python scripts/generate_og_image.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
PAPER = (250, 249, 245)      # #FAF9F5
PAPER2 = (240, 238, 230)     # #F0EEE6
NIGHT = (20, 20, 19)         # #141413
NIGHT2 = (94, 93, 89)        # #5E5D59
NIGHT3 = (135, 134, 127)     # #87867F
CLAY = (217, 119, 87)        # #D97757
LINE = (227, 223, 211)       # #E3DFD3

# Framework chips - darkened hues, legible on paper (mirrors page.tsx FW_COLOR)
FRAMEWORKS = [
    ("CSRD", (31, 122, 83)),
    ("CSDDD", (29, 111, 184)),
    ("AI Act", (124, 77, 188)),
    ("DORA", (192, 86, 33)),
    ("NIS2", (161, 106, 11)),
    ("EU Taxonomy", (15, 118, 110)),
    ("GDPR", (197, 48, 72)),
]

FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def main() -> None:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # Serif (Georgia ~ editorial) for brand/headline, Segoe UI for labels
    f_brand = font("georgia.ttf", 40)
    f_title = font("georgia.ttf", 76)
    f_title_i = font("georgiai.ttf", 76)  # italic for the accent word
    f_eyebrow = font("segoeui.ttf", 22)
    f_sub = font("segoeui.ttf", 30)
    f_chip = font("segoeui.ttf", 22)
    f_foot = font("segoeui.ttf", 22)

    # Brand mark: night square, serif N, clay underline
    d.rounded_rectangle([72, 60, 124, 112], radius=12, fill=NIGHT)
    d.text((98, 64), "N", font=f_brand, fill=PAPER, anchor="ma")
    d.text((140, 72), "NormaAI", font=f_brand, fill=NIGHT)

    # Eyebrow
    d.text((74, 178), "REGULATORY INTELLIGENCE · 7 FRAMEWORK EU", font=f_eyebrow, fill=NIGHT2)

    # Headline: serif, accent word in clay italic
    d.text((72, 226), "Compliance EU, senza", font=f_title, fill=NIGHT)
    d.text((72, 318), "allucinazioni", font=f_title_i, fill=CLAY)
    w_alluc = d.textlength("allucinazioni", font=f_title_i)
    d.text((72 + w_alluc + 18, 318), "AI.", font=f_title, fill=NIGHT)

    # Subtitle
    d.text(
        (74, 432),
        "Citazioni EUR-Lex verificate · Gap analysis · Monitor normativo",
        font=f_sub,
        fill=NIGHT2,
    )

    # Framework chips on white pills with darkened hues
    x, y = 72, 496
    for label, color in FRAMEWORKS:
        tw = d.textlength(label, font=f_chip)
        pad = 16
        d.rounded_rectangle(
            [x, y, x + tw + pad * 2, y + 42], radius=21,
            fill=(255, 255, 255), outline=LINE, width=2,
        )
        d.text((x + pad, y + 8), label, font=f_chip, fill=color)
        x += int(tw) + pad * 2 + 12

    # Footer
    d.text((74, 572), "normaai.org", font=f_foot, fill=NIGHT3)
    # Clay rule, bottom-right signature
    d.rounded_rectangle([1040, 580, 1128, 586], radius=3, fill=CLAY)

    out = Path(__file__).resolve().parents[1] / "frontend" / "public" / "og-image.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"Saved {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
