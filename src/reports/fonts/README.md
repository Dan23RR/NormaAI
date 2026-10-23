# Report fonts

DejaVu Sans 2.35 (Regular, Bold, Oblique), vendored for the PDF report
generator (`src/reports/generator.py`).

fpdf2's built-in core fonts (Helvetica) only cover Latin-1: characters such as
`€`, typographic quotes (`’ “ ”`), dashes (`– —`) or `…` - all common in Italian
compliance text - raise an encoding error at render time. DejaVu Sans is a
Unicode TrueType font that covers them, so the generator registers these files
and uses them for every text cell. If the files are missing the generator falls
back to Helvetica with transliteration (see `_NormaPDF.safe_text`).

Source: the DejaVu fonts project (https://dejavu-fonts.github.io/), files as
redistributed with matplotlib. Licence: `LICENSE-DejaVu.txt` (Bitstream Vera
licence + public-domain DejaVu changes; free to use and redistribute).
