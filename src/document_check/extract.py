"""Find the legal references in a document: acts, provisions, quotes.

Pure functions, no network. The patterns cover how Italian and English
documents usually cite EU and Italian law:

- EU acts: "Regolamento (UE) 2016/679", "Regulation (EU) 2024/1689",
  "Direttiva 2013/34/UE", "Regolamento (CE) n. 1907/2006", and the short names
  (GDPR, AI Act, NIS2, DORA, CSRD, CSDDD, CRA, ...).
- Names a document defines: "Regolamento (UE) 2016/679 (di seguito
  «Regolamento»)" makes "Regolamento" mean that act from there on.
- Italian acts, each resolved to the URN:NIR that Normattiva answers to:
  "d.lgs. 196/2003", "D.Lgs. n. 196 del 2003", "decreto legislativo 30 giugno
  2003, n. 196", "legge 23 settembre 2025, n. 132", "l. 300/1970", "l. 241/90",
  "decreto-legge 21 settembre 2021, n. 127", "D.P.R. 445/2000", "r.d. 267/1942",
  the codes ("art. 2043 c.c.", "cod. civ.", "c.p.", "c.p.c.", "c.p.p."), the
  Constitution ("art. 41 Cost.") and the usual names (Codice privacy, Statuto
  dei lavoratori, Codice del consumo, CAD, TUIR, TUF, TUB, TUEL). Regional laws,
  ministerial decrees, d.P.C.M. and circulars are recognised so that a
  reference next to them is not given to another act, and are reported as
  outside what the check reads.
- Provisions: "art. 13", "artt. 13 e 14", "articolo 50, paragrafo 5",
  "Art. 6(1)(f)", "art. 4 bis", "art. 2-quaterdecies", "art. 4, comma 1-bis",
  "art. 2119, primo comma", "considerando 47", "Allegato III".

A reference takes the act written right after it ("art. 13 del GDPR") or right
before it ("GDPR, art. 13"); failing that, the last act named earlier in the
same paragraph, marked as inferred; failing that, the only act the document
names. An act is never guessed: "decreto 81/2008" without its type, or an
article with two acts to choose from, stays without act. A quote («...», “...”,
"...") belongs to the nearest reference in its paragraph.

An act that amends another does not take the article. In "Article 50(2), as
amended by Regulation (EU) 2026/1744", in "Regolamento (UE) 2024/1689, come
modificato dal Regolamento (UE) 2026/1744, articolo 50" and in a paragraph that
names only the amending act, the article is the amended act's, read in its
consolidated text: the words around the act say it amends ("as amended by",
"inserted by", "amending", "come modificato dal", "che modifica"), or ``AMENDS``
knows it does. Acts named side by side ("Regulation (EU) 2016/679, Regulation
(EU) 2018/1725 or Directive (EU) 2016/680") are acts to choose from: an article
after them takes none of them.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.crawler.normattiva.urn_validator import URNValidator

if TYPE_CHECKING:
    from pathlib import Path

# ─── Acts ────────────────────────────────────────────────────────────

# Short names of the acts NormaAI tracks (and SFDR, which CELLAR serves too).
ACT_NAMES: dict[str, str] = {
    "32016R0679": "GDPR",
    "32024R1689": "AI Act",
    "32022L2555": "NIS2",
    "32022R2554": "DORA",
    "32022L2464": "CSRD",
    "32024L1760": "CSDDD",
    "32024R2847": "Cyber Resilience Act",
    "32020R0852": "Tassonomia",
    "32023R2772": "ESRS",
    "32013L0034": "Direttiva contabile",
    "32019R2088": "SFDR",
    "32026R1744": "Omnibus digitale sull'IA",
    "32026L0470": "Omnibus I",
}

# Acts that amend others, with the acts they amend as their titles list them, the
# act they are about first. An article cited next to one of them and not written
# as its own ("Article 4 of Regulation (EU) 2026/1744") is an article of an act
# it amends: the one the document names, failing that the first.
AMENDS: dict[str, tuple[str, ...]] = {
    # Digital Omnibus on AI: Articles 1 to 3 amend these acts, Article 4 is its entry into force.
    "32026R1744": ("32024R1689", "32018R1139", "32023R1230"),
}

_SECTOR = {
    "regolamento": "R",
    "regulation": "R",
    "direttiva": "L",
    "directive": "L",
    "decisione": "D",
    "decision": "D",
}
_ORG = r"(?:UE|EU|CE|EC|CEE|EEC)"
_EU_ACT_RE = re.compile(
    r"\b(?P<kind>regolamento|direttiva|decisione|regulation|directive|decision)"
    r"(?:\s+(?:delegato|di\s+esecuzione|delegated|implementing))?"
    rf"\s*\(\s*{_ORG}\s*\)\s*"
    r"(?P<n>n\.\s*|no\.?\s*)?(?P<a>\d{1,4})\s*/\s*(?P<b>\d{1,4})(?!\d)",
    re.IGNORECASE,
)
# The older form of directives: "Direttiva 2013/34/UE".
_EU_DIRECTIVE_RE = re.compile(
    rf"\b(?P<kind>direttiva|directive)\s+(?P<a>\d{{4}})/(?P<b>\d{{1,4}})/{_ORG}\b",
    re.IGNORECASE,
)
_SHORT_NAMES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:GDPR|RGPD)\b"), "32016R0679"),
    (
        re.compile(
            r"\bAI\s?Act\b|\b[Rr]egolamento\s+(?:europeo\s+)?(?:sull['’]\s?)?"
            r"(?:IA|intelligenza\s+artificiale)\b"
        ),
        "32024R1689",
    ),
    (re.compile(r"\bNIS\s?2\b"), "32022L2555"),
    (re.compile(r"\bDORA\b"), "32022R2554"),
    (re.compile(r"\bCSRD\b"), "32022L2464"),
    (re.compile(r"\b(?:CSDDD|CS3D)\b"), "32024L1760"),
    (re.compile(r"\bCRA\b|\bCyber\s+Resilience\s+Act\b"), "32024R2847"),
    (
        re.compile(r"\b(?:[Rr]egolamento\s+)?[Tt]assonomia\b|\bTaxonomy\s+Regulation\b"),
        "32020R0852",
    ),
    (re.compile(r"\bESRS\b"), "32023R2772"),
    (re.compile(r"\bSFDR\b"), "32019R2088"),
)

# ─── Italian acts ────────────────────────────────────────────────────

# Month names and their numbers come from the URN validator of the older
# Normattiva crawler (the English abbreviations it also knows are left out).
_IT_MONTH_NUMBERS = {
    name: number for name, number in URNValidator.ITALIAN_MONTHS.items() if len(name) > 3
}
_IT_MONTHS = "|".join(_IT_MONTH_NUMBERS)

# How an Italian act is written, by kind; tried in this order ("d.lgs." before
# "d.l.", "legge costituzionale" before "legge"). These are read on Normattiva.
_IT_READ_KINDS: tuple[tuple[str, str], ...] = (
    ("lcost", r"legge\s+costituzionale|l\.\s?cost\."),
    ("dlgs", r"decreto\s+legislativo|d\.?\s?lgs\.?|d\.\s?l\.?\s?vo\.?"),
    ("dl", r"decreto[\s-]legge|d\.\s?l\."),
    ("dpr", r"decreto\s+del\s+presidente\s+della\s+repubblica|d\.\s?p\.\s?r\.|dpr"),
    ("rd", r"regio\s+decreto|r\.\s?d\."),
    ("legge", r"legge|l\."),
)
# Acts the check recognises but does not read. A bare "decreto" does not say
# which kind of decree it is, and the kind is never guessed.
_IT_OTHER_KINDS: tuple[tuple[str, str], ...] = (
    (
        "lr",
        r"legg[ei]\s+(?:regional[ei]|provincial[ei])|legge\s+della\s+(?:regione|provincia)"
        r"|l\.\s?r\.|l\.\s?p\.",
    ),
    (
        "dpcm",
        r"decreto\s+del\s+presidente\s+del\s+consiglio(?:\s+dei\s+ministri)?"
        r"|d\.\s?p\.\s?c\.\s?m\.|dpcm",
    ),
    ("dm", r"decreto\s+(?:inter)?ministeriale|decreto\s+del\s+ministr[oi]|d\.\s?m\."),
    (
        "decreto",
        r"decreto(?![\s-]+(?:legislativo|legge\b|del\s+presidente|ministeriale|interministeriale"
        r"|del\s+ministr))",
    ),
)
# Kinds whose URN Normattiva answers to (verified on the API), and its act type.
_IT_URN_TYPES = {
    "legge": "legge",
    "dlgs": "decreto.legislativo",
    "dl": "decreto.legge",
    "dpr": "decreto.del.presidente.della.repubblica",
    "rd": "regio.decreto",
    "lcost": "legge.costituzionale",
}
_IT_KIND_LABELS = {
    "legge": "Legge",
    "dlgs": "D.Lgs.",
    "dl": "D.L.",
    "dpr": "D.P.R.",
    "rd": "R.D.",
    "lcost": "Legge costituzionale",
    "lr": "Legge regionale",
    "dm": "D.M.",
    "dpcm": "D.P.C.M.",
}
# Acts with one URN each: the codes are annexes of the decrees that approved them.
_IT_FIXED: dict[str, tuple[str, str]] = {
    "IT:cost": ("Costituzione", "urn:nir:stato:costituzione:1947-12-27"),
    "IT:cc": ("Codice civile", "urn:nir:stato:regio.decreto:1942-03-16;262:2"),
    "IT:cp": ("Codice penale", "urn:nir:stato:regio.decreto:1930-10-19;1398:1"),
    "IT:cpc": ("Codice di procedura civile", "urn:nir:stato:regio.decreto:1940-10-28;1443:1"),
    "IT:cpp": (
        "Codice di procedura penale",
        "urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447",
    ),
}
# Acts cited by their own number whose articles are those of the text they
# approve: royal decree 267 of 1942 has two articles, the bankruptcy law it
# approves (annex 1) is what "art. 67 r.d. 267/1942" means.
_IT_ANNEXES = {("rd", "1942", "267"): ":1"}
# Names by which an act is usually called, checked against the title Normattiva gives it.
_IT_COMMON_NAMES: dict[tuple[str, str, str], str] = {
    ("dlgs", "2003", "196"): "Codice privacy",
    ("legge", "1970", "300"): "Statuto dei lavoratori",
    ("dlgs", "2005", "206"): "Codice del consumo",
    ("dlgs", "2005", "82"): "CAD",
    ("dpr", "1986", "917"): "TUIR",
    ("dlgs", "1998", "58"): "TUF",
    ("dlgs", "1993", "385"): "TUB",
    ("dlgs", "2000", "267"): "TUEL",
    ("dlgs", "2019", "14"): "Codice della crisi",
    ("legge", "2000", "212"): "Statuto del contribuente",
    ("rd", "1942", "267"): "legge fallimentare",
}
# Why the check does not read an act of this kind.
_IT_NOT_READ = {
    "lr": "Le leggi regionali non sono tra gli atti che il controllo legge su Normattiva",
    "dm": "I decreti ministeriali non sono ancora tra gli atti che il controllo legge",
    "dpcm": (
        "I decreti del Presidente del Consiglio dei ministri non sono ancora tra gli atti "
        "che il controllo legge"
    ),
    "decreto": (
        "Il documento scrive «decreto» senza dire di che tipo (legislativo, legge, "
        "ministeriale): il controllo non indovina l'atto"
    ),
    "circ": "Le circolari non sono tra gli atti che il controllo legge",
    "dispatt": (
        "Le disposizioni di attuazione dei codici non sono ancora tra gli atti che il "
        "controllo legge"
    ),
}

_IT_DATE = rf"(?:\d{{1,2}})[°º]?\s+(?:{_IT_MONTHS})\s+\d{{4}}"
# The ways the date, the number and the year of an act are written.
_IT_NUMBERED = (
    # "20.5.1970, n. 300"
    r"(?P<d1>\d{1,2})[./](?P<m1>\d{1,2})[./](?P<y1>\d{4}|\d{2})\s*(?:,\s*)?n\.?\s*(?P<n1>\d{1,5})"
    # "30 giugno 2003, n. 196"
    rf"|(?:del\s+|dell['’]\s?)?(?P<d2>\d{{1,2}})[°º]?\s+(?P<m2>{_IT_MONTHS})\s+(?P<y2>\d{{4}})"
    r"\s*(?:,\s*)?n\.?\s*(?P<n2>\d{1,5})"
    # "n. 196 del 2003", "n. 196 del 30 giugno 2003"
    r"|n\.?\s*(?P<n3>\d{1,5})\s+del(?:l['’])?\s*"
    rf"(?:(?P<d3>\d{{1,2}})[°º]?\s+(?P<m3>{_IT_MONTHS})\s+)?(?P<y3>\d{{4}})"
    # "196/2003", "n. 231/01"
    r"|(?:n\.?\s*)?(?P<n4>\d{1,5})\s*/\s*(?P<y4>\d{4}|\d{2})(?!\d|[./]\d)"
)
# "14 gennaio 2008": a decree that has no number.
_IT_DATED = (
    rf"|(?:del\s+|dell['’]\s?)?(?P<d5>\d{{1,2}})[°º]?\s+(?P<m5>{_IT_MONTHS})\s+(?P<y5>\d{{4}})"
)
# Not the tail of a longer abbreviation ("c.c.n.l. 14/2020" is not a law).
_IT_START = r"(?<![A-Za-z]\.)\b"


def _kinds(kinds: tuple[tuple[str, str], ...]) -> str:
    return "|".join(f"(?P<k_{kind}>{pattern})" for kind, pattern in kinds)


_IT_ACT_RE = re.compile(
    rf"{_IT_START}(?:{_kinds(_IT_READ_KINDS)})\s*(?:{_IT_NUMBERED})", re.IGNORECASE
)
_IT_OTHER_ACT_RE = re.compile(
    rf"{_IT_START}(?:{_kinds(_IT_OTHER_KINDS)})"
    # "legge regionale Lombardia", "decreto del Ministro della giustizia": who issued it.
    r"(?:\s+(?!n\.|del\s+\d|d\.|l\.|r\.|legge\b|decreto\b)[A-Za-zÀ-ÿ'’\-]+\.?){0,7}?\s*"
    rf"(?:{_IT_NUMBERED}{_IT_DATED})",
    re.IGNORECASE,
)
_IT_CIRCULAR_RE = re.compile(
    rf"\bcircolar[ei]\b[^.;\n]{{0,80}}?\bn\.?\s*\d+(?:/[A-Z0-9]+)?(?:\s+del\s+(?:{_IT_DATE}|\d{{4}}))?",
    re.IGNORECASE,
)
_IT_IMPLEMENTING_RE = re.compile(
    r"\bdisp(?:osizioni)?\.?\s+(?:di\s+)?att(?:uazione)?\.?(?:\s+e\s+trans(?:itorie)?\.?)?\s+"
    r"(?:del\s+)?(?:c\.\s?p\.\s?c\.|c\.\s?p\.\s?p\.|c\.\s?c\.|c\.\s?p\.|cod(?:ice|\.)[^,;.\n]{0,30})",
    re.IGNORECASE,
)
# An abbreviation of two or three letters means a code only next to an article
# ("art. 2043 c.c."), and never when more letters follow ("c.c.n.l.", "c.p.a.").
_NOT_LONGER = r"(?!\s?[A-Za-z]\.)"
_IT_NAMES: tuple[tuple[re.Pattern[str], str, bool], ...] = (
    # (pattern, act key, needs an article next to it)
    (
        re.compile(rf"\b[Cc]\.\s?[Pp]\.\s?[Cc]\.{_NOT_LONGER}|\b[Cc]od\.\s?proc\.\s?civ\."),
        "IT:cpc",
        True,
    ),
    (
        re.compile(rf"\b[Cc]\.\s?[Pp]\.\s?[Pp]\.{_NOT_LONGER}|\b[Cc]od\.\s?proc\.\s?pen\."),
        "IT:cpp",
        True,
    ),
    (re.compile(rf"\b[Cc]\.\s?[Cc]\.{_NOT_LONGER}|\b[Cc]od\.\s?civ\."), "IT:cc", True),
    (re.compile(rf"\b[Cc]\.\s?[Pp]\.{_NOT_LONGER}|\b[Cc]od\.\s?pen\."), "IT:cp", True),
    (re.compile(r"\bCost\."), "IT:cost", True),
    (re.compile(r"\b[Cc]odice\s+di\s+procedura\s+civile\b"), "IT:cpc", False),
    (re.compile(r"\b[Cc]odice\s+di\s+procedura\s+penale\b"), "IT:cpp", False),
    (re.compile(r"\b[Cc]odice\s+civile\b"), "IT:cc", False),
    (re.compile(r"\b[Cc]odice\s+penale\b(?!\s+militare)"), "IT:cp", False),
    (re.compile(r"\bCostituzione\b"), "IT:cost", False),
    (
        re.compile(
            r"\b[Cc]odice\s+(?:della\s+)?privacy\b|\b[Cc]odice\s+in\s+materia\s+di\s+protezione"
            r"\s+dei\s+dati\s+personali\b"
        ),
        "IT:dlgs:2003:196",
        False,
    ),
    (re.compile(r"\b[Ss]tatuto\s+dei\s+lavoratori\b"), "IT:legge:1970:300", False),
    (re.compile(r"\b[Cc]odice\s+del\s+consumo\b"), "IT:dlgs:2005:206", False),
    (
        re.compile(r"\b[Cc]odice\s+dell['’]\s?amministrazione\s+digitale\b"),
        "IT:dlgs:2005:82",
        False,
    ),
    (re.compile(r"\bCAD\b"), "IT:dlgs:2005:82", True),
    (
        re.compile(r"\b[Tt]esto\s+unico\s+delle\s+imposte\s+sui\s+redditi\b"),
        "IT:dpr:1986:917",
        False,
    ),
    (re.compile(r"\bT\.?U\.?I\.?R\b\.?"), "IT:dpr:1986:917", True),
    (re.compile(r"\b[Tt]esto\s+unico\s+della\s+finanza\b"), "IT:dlgs:1998:58", False),
    (re.compile(r"\bT\.?U\.?F\b\.?"), "IT:dlgs:1998:58", True),
    (re.compile(r"\b[Tt]esto\s+unico\s+bancario\b"), "IT:dlgs:1993:385", False),
    (re.compile(r"\bT\.?U\.?B\b\.?"), "IT:dlgs:1993:385", True),
    (
        re.compile(r"\b[Tt]esto\s+unico\s+(?:degli|sugli)\s+enti\s+locali\b"),
        "IT:dlgs:2000:267",
        False,
    ),
    (re.compile(r"\bT\.?U\.?E\.?L\b\.?"), "IT:dlgs:2000:267", True),
    (
        re.compile(
            r"\b[Cc]odice\s+della\s+crisi(?:\s+d['’]\s?impresa(?:\s+e\s+dell['’]\s?insolvenza)?)?"
        ),
        "IT:dlgs:2019:14",
        False,
    ),
    (
        re.compile(r"\b[Ss]tatuto\s+(?:dei\s+diritti\s+)?del\s+contribuente\b"),
        "IT:legge:2000:212",
        False,
    ),
    (re.compile(r"\b[Ll]egge\s+fallimentare\b"), "IT:rd:1942:267", False),
)
# "(di seguito «Regolamento» o «GDPR»)" right after an act: names the document defines.
_DEFINITION_RE = re.compile(r"\s*\((?P<body>[^()]{0,200})\)")
_DEFINED_NAME_RE = re.compile(r"[«“\"]\s*([^«»“”\"]{2,40}?)\s*[»”\"]")
# Where a defined name can start (not inside a word, not right after a quotation
# mark: the definition itself), and what may not follow it.
_NAME_START_RE = re.compile(r"(?<![\w«“\"])\w+")
_NAME_STOP_RE = re.compile(r"[\w»”\"]")

NORMATTIVA_RESOLVER = "https://www.normattiva.it/uri-res/N2Ls?"


@dataclass(frozen=True)
class Act:
    """An act a reference belongs to."""

    # CELEX of an EU act ("32024R1689"); for Italian law "IT:dlgs:2003:196" (kind,
    # year, number), "IT:cc" for a code, "IT:dm:..." for an act the check does not read.
    key: str
    label: str  # how the report names it
    date: str | None = None  # ISO date of an Italian act, when the document writes it

    @property
    def eu(self) -> bool:
        return not self.key.startswith("IT:")

    @property
    def source(self) -> str:
        """Where the act's text is read: "eurlex" or "normattiva"."""
        return "eurlex" if self.eu else "normattiva"

    @property
    def urn(self) -> str | None:
        """URN:NIR of an Italian act that Normattiva answers to; None for any other act."""
        if self.eu:
            return None
        if self.key in _IT_FIXED:
            return _IT_FIXED[self.key][1]
        parts = self.key.split(":")
        if len(parts) == 4 and parts[1] in _IT_URN_TYPES and parts[2].isdigit():
            annex = _IT_ANNEXES.get((parts[1], parts[2], parts[3]), "")
            return f"urn:nir:stato:{_IT_URN_TYPES[parts[1]]}:{parts[2]};{parts[3]}{annex}"
        return None

    @property
    def identifier(self) -> str:
        """What names the act at its source: the CELEX, or the URN of an Italian act."""
        return self.urn or self.key

    @property
    def not_read(self) -> str | None:
        """Why the check does not read this act; None when it does."""
        if self.eu or self.urn:
            return None
        kind = self.key.split(":")[1] if ":" in self.key else ""
        return _IT_NOT_READ.get(kind, "Questo tipo di atto non è tra quelli che il controllo legge")

    @property
    def normattiva_url(self) -> str | None:
        """Normattiva page of an Italian act; None when Normattiva is not asked for it."""
        return NORMATTIVA_RESOLVER + self.urn if self.urn else None


@dataclass(frozen=True)
class _Mention:
    act: Act
    start: int
    end: int


def eu_act(celex: str, written: str | None = None) -> Act:
    """The Act for a CELEX, labelled with its short name when NormaAI knows it."""
    name = ACT_NAMES.get(celex)
    written = re.sub(r"\s+", " ", written or "").strip()
    if written and name and name.lower() not in written.lower():
        return Act(celex, f"{written} ({name})")
    return Act(celex, written or name or celex)


def italian_act(kind: str, year: str, number: str, date: str | None = None) -> Act:
    """The Act for an Italian act of a kind ("dlgs", "legge", "dl", "dpr", ...)."""
    number = str(int(number))
    label = f"{_IT_KIND_LABELS.get(kind, 'Decreto')} {number}/{year}"
    name = _IT_COMMON_NAMES.get((kind, year, number))
    if name:
        label += f" ({name})"
    return Act(f"IT:{kind}:{year}:{number}", label, date)


def _named_act(key: str) -> Act:
    """The Act behind a name: a code ("IT:cc") or a numbered act ("IT:dlgs:2003:196")."""
    if key in _IT_FIXED:
        return Act(key, _IT_FIXED[key][0])
    _, kind, year, number = key.split(":")
    return italian_act(kind, year, number)


def _full_year(year: str, kind: str) -> str:
    """ "90" gives "1990", "08" gives "2008": the Republic's acts start in 1946."""
    if len(year) == 4:
        return year
    return f"19{year}" if kind == "rd" or int(year) >= 46 else f"20{year}"


def _italian_mention(m: re.Match[str], kinds: tuple[tuple[str, str], ...]) -> _Mention | None:
    """The act written as kind, date, number and year in a match of an act pattern."""
    groups = m.groupdict()
    kind = next(k for k, _ in kinds if groups.get(f"k_{k}"))
    number = groups.get("n1") or groups.get("n2") or groups.get("n3") or groups.get("n4")
    year = groups.get("y1") or groups.get("y2") or groups.get("y3") or groups.get("y4")
    day = groups.get("d1") or groups.get("d2") or groups.get("d3")
    month: int | str | None = groups.get("m1") or _IT_MONTH_NUMBERS.get(
        (groups.get("m2") or groups.get("m3") or "").lower()
    )
    if not number:  # a decree cited by its date alone
        day, year = groups.get("d5"), groups.get("y5")
        month = _IT_MONTH_NUMBERS.get((groups.get("m5") or "").lower())
    if not year:
        return None
    year = _full_year(year, kind)
    if not 1861 <= int(year) <= 2100:
        return None
    written: str | None = None
    if day and month and 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
        written = f"{year}-{int(month):02d}-{int(day):02d}"
    if number:
        act = italian_act(kind, year, number, written)
    else:
        label = (
            f"{_IT_KIND_LABELS.get(kind, 'Decreto')} del {int(day or 0)}/{int(month or 0)}/{year}"
        )
        act = Act(f"IT:{kind}:{written or year}", label, written)
    return _Mention(act, m.start(), m.end())


def _next_to_an_article(text: str, start: int, end: int) -> bool:
    """True when an abbreviation stands by an article: "art. 2043 c.c.", "c.c., art. 2043"."""
    before = text[max(0, start - 70) : start]
    if re.search(r"(?:\bartt?\.?|\barticol[oi])\s*\d[^;\n]{0,60}$", before, re.IGNORECASE):
        return True
    return bool(
        re.match(r"\s*,?\s*(?:artt?\.?|articol[oi])\s*\d", text[end : end + 16], re.IGNORECASE)
    )


def _settle_bare_decrees(mentions: list[_Mention]) -> list[_Mention]:
    """ "il decreto 138/2024" is the decree with that number the document names in full."""
    known: dict[tuple[str, str], set[str]] = {}
    for mention in mentions:
        parts = mention.act.key.split(":")
        if len(parts) == 4 and parts[1] in ("dlgs", "dl", "dpr"):
            known.setdefault((parts[2], parts[3]), set()).add(mention.act.key)
    settled: list[_Mention] = []
    for mention in mentions:
        parts = mention.act.key.split(":")
        same = known.get((parts[2], parts[3]), set()) if len(parts) == 4 else set()
        if len(parts) == 4 and parts[1] == "decreto" and len(same) == 1:
            _, kind, year, number = next(iter(same)).split(":")
            mention = _Mention(italian_act(kind, year, number), mention.start, mention.end)
        settled.append(mention)
    return settled


def _eu_celex(kind: str, a: str, b: str, number_first: bool) -> str | None:
    """CELEX of "Regolamento (UE) 2016/679" (year/number) or "(CE) n. 1907/2006"."""
    sector = _SECTOR[kind.lower()]
    if number_first:
        number, year = a, b
    elif len(a) == 4 and 1950 <= int(a) <= 2100:
        year, number = a, b
    elif len(b) == 4 and 1950 <= int(b) <= 2100:
        number, year = a, b
    else:
        return None
    return f"3{year}{sector}{int(number):04d}"


def _act_mentions(text: str) -> list[_Mention]:
    mentions: list[_Mention] = []
    for m in _EU_ACT_RE.finditer(text):
        celex = _eu_celex(m.group("kind"), m.group("a"), m.group("b"), bool(m.group("n")))
        if celex:
            mentions.append(_Mention(eu_act(celex, m.group(0)), m.start(), m.end()))
    for m in _EU_DIRECTIVE_RE.finditer(text):
        celex = _eu_celex(m.group("kind"), m.group("a"), m.group("b"), number_first=False)
        if celex:
            mentions.append(_Mention(eu_act(celex, m.group(0)), m.start(), m.end()))
    for pattern, kinds in ((_IT_ACT_RE, _IT_READ_KINDS), (_IT_OTHER_ACT_RE, _IT_OTHER_KINDS)):
        for m in pattern.finditer(text):
            mention = _italian_mention(m, kinds)
            if mention is not None:
                mentions.append(mention)
    for m in _IT_CIRCULAR_RE.finditer(text):
        mentions.append(_Mention(Act("IT:circ", "Circolare"), m.start(), m.end()))
    for m in _IT_IMPLEMENTING_RE.finditer(text):
        act = Act("IT:dispatt", "Disposizioni di attuazione")
        mentions.append(_Mention(act, m.start(), m.end()))
    for pattern, key, by_an_article in _IT_NAMES:
        for m in pattern.finditer(text):
            if not by_an_article or _next_to_an_article(text, m.start(), m.end()):
                mentions.append(_Mention(_named_act(key), m.start(), m.end()))
    for pattern, celex in _SHORT_NAMES:
        for m in pattern.finditer(text):
            mentions.append(_Mention(eu_act(celex), m.start(), m.end()))
    mentions = _settle_bare_decrees(_drop_overlaps(mentions))
    return _drop_overlaps(mentions + _defined_names(text, mentions))


def _drop_overlaps(mentions: list[_Mention]) -> list[_Mention]:
    """Keep the longest mention where two overlap ("Regolamento (UE) 2016/679" over "GDPR")."""
    kept: list[_Mention] = []
    for m in sorted(mentions, key=lambda x: (x.start, -(x.end - x.start))):
        if kept and m.start < kept[-1].end:
            continue
        kept.append(m)
    return kept


def _defined_names(text: str, mentions: list[_Mention]) -> list[_Mention]:
    """Mentions of the names the document defines for an act, after the definition.

    A name stands for the act of its latest definition before it. The text is
    read once, whatever the number of definitions: at each word that starts a
    defined name, the names starting with that word are tried, longest first (a
    name has at most 40 characters), and one mention is kept per place.
    """
    definitions: dict[str, tuple[list[int], list[Act]]] = {}
    for mention in mentions:
        d = _DEFINITION_RE.match(text, mention.end)
        if not d:
            continue
        for name in _DEFINED_NAME_RE.findall(d.group("body")):
            name = name.strip()
            if not name or not name[0].isupper():
                continue
            positions, acts = definitions.setdefault(name, ([], []))
            positions.append(d.end())
            acts.append(mention.act)
    if not definitions:
        return []
    # Names by the word they start with, longest first.
    by_word: dict[str, list[str]] = {}
    for name in definitions:
        word = _NAME_START_RE.match(name)
        if word:
            by_word.setdefault(word.group(), []).append(name)
    for names in by_word.values():
        names.sort(key=len, reverse=True)
    found: list[_Mention] = []
    start = min(positions[0] for positions, _ in definitions.values())
    for m in _NAME_START_RE.finditer(text, start):
        for name in by_word.get(m.group(), ()):
            end = m.start() + len(name)
            if not text.startswith(name, m.start()) or _NAME_STOP_RE.match(text, end):
                continue
            positions, acts = definitions[name]
            latest = bisect_right(positions, m.start()) - 1
            if latest >= 0:
                found.append(_Mention(acts[latest], m.start(), end))
                break
    return found


# ─── Provisions ──────────────────────────────────────────────────────

# Articles and commi inserted between two others take a Latin adverb: 2-bis,
# 2-ter, ... 2-quaterdecies, and past the twentieth "vicies semel", "vicies bis".
_LATIN_UNITS = {
    "semel": 1,
    "bis": 2,
    "ter": 3,
    "quater": 4,
    "quinquies": 5,
    "sexies": 6,
    "septies": 7,
    "octies": 8,
    "novies": 9,
    "nonies": 9,
}
_LATIN_TEENS = {
    "decies": 10,
    "undecies": 11,
    "duodecies": 12,
    "terdecies": 13,
    "quaterdecies": 14,
    "quinquiesdecies": 15,
    "quindecies": 15,
    "sexiesdecies": 16,
    "sedecies": 16,
    "septiesdecies": 17,
    "octiesdecies": 18,
    "duodevicies": 18,
    "noviesdecies": 19,
    "undevicies": 19,
}
_LATIN_TENS = {"vicies": 20, "tricies": 30, "quadragies": 40, "quinquagies": 50}
_LATIN = rf"(?:{'|'.join(_LATIN_TENS)})(?:[\s-]?(?:{'|'.join(_LATIN_UNITS)}))?|" + "|".join(
    sorted((w for w in (*_LATIN_TEENS, *_LATIN_UNITS) if w != "semel"), key=len, reverse=True)
)


def latin_ordinal(suffix: str) -> int | None:
    """Place of an inserted article: "bis" is 2, "quaterdecies" 14, "vicies semel" 21."""
    word = re.sub(r"[\s-]+", "", suffix.lower())
    if word in _LATIN_TEENS:
        return _LATIN_TEENS[word]
    if word in _LATIN_UNITS:
        return _LATIN_UNITS[word] if word != "semel" else None
    for tens, value in _LATIN_TENS.items():
        if word == tens:
            return value
        if word.startswith(tens) and word[len(tens) :] in _LATIN_UNITS:
            return value + _LATIN_UNITS[word[len(tens) :]]
    return None


_ORDINALS = (
    "primo secondo terzo quarto quinto sesto settimo ottavo nono decimo undicesimo dodicesimo"
).split()
_ORDINAL = "|".join(_ORDINALS)
# A number that is not the first half of an act number ("2016/679").
_NUM = rf"\d{{1,4}}(?!\d|\s*/)(?:[\s-]?(?:{_LATIN})\b|[a-z](?![a-z]))?"
_SUBDIV = r"(?:\s*\(\s*\d{1,3}\s*\))?(?:\s*\(\s*[a-z]{1,2}\s*\))*"
# A paragraph or comma: "1", "1-bis".
_PAR = rf"\d{{1,3}}(?:[\s-]?(?:{_LATIN})\b)?"
# A comma between spaces is "\s*(?:,\s*)?", never "\s*,?\s*": without a comma the
# second form can split a run of spaces in as many ways as it is long, and a
# document with a long run of spaces made the match take minutes.
_PARA = (
    r"(?:\s*(?:,\s*)?(?:"
    r"(?:paragrafi|paragrafo|parr\.|par\.|paragraphs|paragraph|para\.|commi|comma|co\.)"
    rf"\s*{_PAR}(?:\s*(?:,|e|ed|and|-|–)\s*{_PAR})*"
    # "primo comma", "commi primo e secondo": how the codes are cited.
    rf"|comm[ai]\s+(?:{_ORDINAL})\b(?:\s*(?:,|e|ed)\s*(?:{_ORDINAL})\b)*"
    rf"|(?:{_ORDINAL})(?:\s*(?:,|e|ed)\s*(?:{_ORDINAL}))*\s+comm[ai]\b"
    r"))?"
)
_POINT = r"(?:\s*(?:,\s*)?(?:lettera|lett\.|letter|point|punto)\s*[a-z0-9]{1,3}\)?)?"
_ITEM = rf"{_NUM}{_SUBDIV}{_PARA}{_POINT}"
_SEP = r"\s*(?:,|\be\b|\bed\b|\band\b|-|–)\s*"
_ARTICLE_RE = re.compile(
    rf"\b(?:artt?\.|art\b|articol[oi]|articles?)\s*(?P<items>{_ITEM}(?:{_SEP}{_ITEM})*)",
    re.IGNORECASE,
)
_ITEM_RE = re.compile(rf"(?P<num>{_NUM})(?P<sub>{_SUBDIV})(?P<para>{_PARA}){_POINT}", re.IGNORECASE)
_NUM_PARTS_RE = re.compile(rf"^(\d{{1,4}})(?:[\s-]?({_LATIN})|([a-z]))?$", re.IGNORECASE)
# "paragrafo 9 dell'articolo 50", "comma 1-bis dell'art. 13", "terzo comma
# dell'articolo 18": the paragraph first.
_PARAGRAPH_FIRST_RE = re.compile(
    rf"\b(?:(?:paragrafo|par\.|comma|co\.)\s*(?P<para>{_PAR})|(?P<word>{_ORDINAL})\s+comma)"
    rf"\s+dell['’]\s*(?:articolo|art\.?)\s*(?P<num>{_NUM})",
    re.IGNORECASE,
)
_PAR_TOKEN_RE = re.compile(
    rf"(\d{{1,3}})(?:[\s-]?({_LATIN})\b)?(?:\s*[-–]\s*(\d{{1,3}})(?![\s-]?(?:{_LATIN})\b))?"
    rf"|\b({_ORDINAL})\b",
    re.IGNORECASE,
)
_RECITAL_RE = re.compile(
    r"\b(?:considerand[oi]|recitals?)\s*(?:n\.\s*)?"
    r"(?P<items>\d{1,3}(?:\s*(?:,|\be\b|\band\b|-|–)\s*\d{1,3})*)",
    re.IGNORECASE,
)
_ANNEX_RE = re.compile(r"\b(?:[Aa]llegat[oi]|[Aa]nnex(?:es)?)\s+(?P<num>[IVXLC]{1,6}|\d{1,2})\b")


@dataclass(frozen=True)
class Provision:
    """One provision a reference names: an article, a recital or an annex."""

    key: str  # parse_article key: "art:13", "art:4bis", "recital:47", "annex:III"
    paragraphs: tuple[str, ...] = ()  # "1", "2", and for a comma also "1bis"
    commi: bool = False  # the document calls them commi, not paragraphs

    @property
    def label(self) -> str:
        kind, _, number = self.key.partition(":")
        if kind == "recital":
            return f"considerando {number}"
        if kind == "annex":
            return f"allegato {number}"
        m = re.match(rf"^(\d+)({_LATIN})$", number)
        base = f"art. {m.group(1)} {m.group(2)}" if m else f"art. {number}"
        if self.paragraphs:
            one = len(self.paragraphs) == 1
            word = ("comma" if one else "commi") if self.commi else ("par." if one else "parr.")
            return f"{base}, {word} {', '.join(paragraph_label(p) for p in self.paragraphs)}"
        return base


def paragraph_label(paragraph: str) -> str:
    """ "1bis" as it is written: "1-bis"."""
    m = re.match(r"^(\d+(?:\.\d+)?)([a-z]+)$", paragraph)
    return f"{m.group(1)}-{m.group(2)}" if m else paragraph


@dataclass
class Reference:
    """A reference to one or more provisions of an act, as written in the document."""

    start: int
    end: int
    provisions: list[Provision]
    act: Act | None = None
    act_inferred: bool = False
    quotes: list[str] = field(default_factory=list)
    raw: str = ""  # the reference with its act, as written: "art. 13 del GDPR"
    line: int = 0  # 1-based line (paragraph) of the document
    context: str = ""  # the text around the reference
    # The act named next to the reference that amends ``act``, when the article was
    # given to the act amended: "Article 50(2), as amended by Regulation (EU) 2026/1744".
    amended_by: Act | None = None


def _numbers(text: str) -> list[str]:
    """Paragraph numbers in "par. 1", "commi 1-3", "(2)"; ranges expanded."""
    found: list[str] = []
    for m in re.finditer(r"(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?", text):
        first, last = int(m.group(1)), int(m.group(2) or m.group(1))
        if last < first or last - first > 20:
            last = first
        found.extend(str(n) for n in range(first, last + 1))
    return found


def _paragraphs(text: str) -> list[str]:
    """Paragraphs or commi in "par. 1", "commi 1-3", "comma 1-bis", "primo e secondo comma"."""
    found: list[str] = []
    for m in _PAR_TOKEN_RE.finditer(text):
        if m.group(4):
            found.append(str(_ORDINALS.index(m.group(4).lower()) + 1))
        elif m.group(2):
            found.append(m.group(1) + re.sub(r"[\s-]+", "", m.group(2).lower()))
        else:
            first, last = int(m.group(1)), int(m.group(3) or m.group(1))
            if last < first or last - first > 20:
                last = first
            found.extend(str(n) for n in range(first, last + 1))
    return found


def _article_key(number: str) -> str | None:
    """Key of an article number as written: "13", "4 bis", "2-quaterdecies", "19a"."""
    m = _NUM_PARTS_RE.match(number.strip())
    if not m:
        return None
    suffix = re.sub(r"[\s-]+", "", (m.group(2) or m.group(3) or "").lower())
    return f"art:{m.group(1)}{suffix}"


def _article_provisions(items: str) -> list[Provision]:
    provisions: list[Provision] = []
    previous_end = 0
    for m in _ITEM_RE.finditer(items):
        sub = re.match(r"\s*\(\s*(\d{1,3})\s*\)", m.group("sub"))
        paragraphs = [sub.group(1)] if sub else _paragraphs(m.group("para"))
        commi = not sub and bool(re.search(r"comm|co\.", m.group("para"), re.IGNORECASE))
        key = _article_key(m.group("num"))
        if key is None:
            continue
        # "artt. 15-22": a range between two plain article numbers.
        between = items[previous_end : m.start()]
        if provisions and re.search(r"[-–]", between):
            first = re.fullmatch(r"art:(\d+)", provisions[-1].key)
            last = re.fullmatch(r"art:(\d+)", key)
            if first and last and 0 < int(last.group(1)) - int(first.group(1)) <= 30:
                for n in range(int(first.group(1)) + 1, int(last.group(1))):
                    provisions.append(Provision(f"art:{n}"))
        provisions.append(Provision(key, tuple(dict.fromkeys(paragraphs)), commi))
        previous_end = m.end()
    return provisions


def _references(text: str) -> list[Reference]:
    refs: list[Reference] = []
    for m in _PARAGRAPH_FIRST_RE.finditer(text):
        key = _article_key(m.group("num"))
        paragraphs = _paragraphs(m.group("para") or m.group("word"))
        if key is not None and paragraphs:
            commi = bool(m.group("word")) or m.group(0).lower().startswith("co")
            refs.append(Reference(m.start(), m.end(), [Provision(key, (paragraphs[0],), commi)]))
    taken = [(r.start, r.end) for r in refs]
    for m in _ARTICLE_RE.finditer(text):
        if _within(m.start(), taken):
            continue
        provisions = _article_provisions(m.group("items"))
        if provisions:
            refs.append(Reference(m.start(), m.end(), provisions))
    for m in _RECITAL_RE.finditer(text):
        provisions = [Provision(f"recital:{n}") for n in dict.fromkeys(_numbers(m.group("items")))]
        refs.append(Reference(m.start(), m.end(), provisions))
    for m in _ANNEX_RE.finditer(text):
        refs.append(Reference(m.start(), m.end(), [Provision(f"annex:{m.group('num').upper()}")]))
    return sorted(refs, key=lambda r: r.start)


# ─── Linking references, acts and quotes ─────────────────────────────

_ABBREVIATIONS = re.compile(
    r"\b(?:artt?|parr?|n|lett|co|cfr|es|ecc|d\.lgs|lgs|l|reg|dir|no|para)\.", re.IGNORECASE
)
# The spaces just inside the marks are part of the quote, stripped where it is
# used: "«\s*...\s*»" could split a run of spaces in too many ways.
_QUOTE_RE = re.compile(
    r"«(?P<a>[^«»\n]{20,1500}?)»|“(?P<b>[^“”\n]{20,1500}?)”|\"(?P<c>[^\"\n]{20,1500}?)\""
)
_AFTER_WINDOW = 90
_BEFORE_WINDOW = 40

# Words before an act that say it amends another: "as amended by", "following the
# amendment by", "(inserted by", "the amending act,", "come modificato dal", "le
# modifiche introdotte dal", "inserito dal"; the act's name may stand in between:
# "as amended by the Digital Omnibus on AI (Regulation (EU) 2026/1744".
_DA = r"(?:da|dal|dalla|dallo|dai|dagli|dalle|dall['’]|con)"
_AMENDING_BEFORE_RE = re.compile(
    r"(?:\bamended\s+by|\bamendments?\s+(?:(?:introduced|made)\s+)?by|\b(?:inserted|added)\s+by"
    r"|\b(?:the|an?|this)\s+amending(?:\s+(?:act|regulation|directive))?"
    rf"|\bmodificat[oaie]\s+{_DA}|\bmodifich?[ea]\s+(?:introdott|apportat)[ae]\s+{_DA}"
    rf"|\b(?:inserit|aggiunt)[oaie]\s+{_DA}"
    r"|\b(?:atto|regolamento|direttiva)\s+(?:modificativ[oa]|di\s+modifica))"
    r"(?:\s*[^\s.,;:()]+(?:\s+[^\s.,;:()]+){0,6}\s*[(,])?[\s(]*$",
    re.IGNORECASE,
)
# Words right after an act that say it amends another: "Regulation (EU) 2026/1744
# amending", "(the Digital Omnibus on AI), which amended", "che modifica".
_AMENDING_AFTER_RE = re.compile(
    r"\s*(?:\([^()\n]{0,80}\)\s*)?(?:,\s*)?(?:(?:which|that)\s+(?:has\s+)?(?:amended|amends)\b"
    r"|amending\b|amends\b|che\s+(?:ha\s+)?modific|recante\s+modific|di\s+modifica\b)",
    re.IGNORECASE,
)
# What stands between acts named side by side: "Regulation (EU) 2016/679 [GDPR],
# Regulation (EU) 2018/1725, or Directive (EU) 2016/680", "al GDPR e alla Direttiva".
_LIST_GAP_RE = re.compile(
    r"[^\S\n]*(?:[\[\]()][^\S\n]*)*(?:[,;/][^\S\n]*)?"
    r"(?:(?:and/or|e/o|and|or|e|ed|o|od|nonché|as\s+well\s+as)[^\S\n]+)?"
    r"(?:(?:the|il|lo|la|i|gli|le|l['’]|(?:a|da|de|ne|su)(?:l|llo|lla|i|gli|lle|ll['’]))"
    r"[^\S\n]*)?",
    re.IGNORECASE,
)


def _crosses_sentence(gap: str) -> bool:
    gap = _ABBREVIATIONS.sub(" ", gap)
    return bool(re.search(r"[\n;]|[.!?]\s+[A-ZÀ-Ý«“\"]", gap))


def _line_bounds(text: str, position: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return start, len(text) if end == -1 else end


class _Lines:
    """The lines of a text: which line a position is on, and where that line starts and ends.

    Found by bisection on the line breaks, so that asking for every reference
    of a long text costs a logarithm each, not a scan of the text.
    """

    def __init__(self, text: str) -> None:
        self.breaks = [m.start() for m in re.finditer("\n", text)]
        self.size = len(text)

    def index(self, position: int) -> int:
        """0-based line of ``position``."""
        return bisect_left(self.breaks, position)

    def bounds(self, position: int) -> tuple[int, int]:
        """Like ``_line_bounds``: start of the line of ``position`` and its line break."""
        i = bisect_left(self.breaks, position)
        start = self.breaks[i - 1] + 1 if i else 0
        return start, self.breaks[i] if i < len(self.breaks) else self.size


def _context(text: str, start: int, end: int, width: int = 160, lines: _Lines | None = None) -> str:
    line_start, line_end = lines.bounds(start) if lines else _line_bounds(text, start)
    left = max(line_start, start - width)
    right = min(line_end, end + width)
    snippet = text[left:right].strip()
    return ("… " if left > line_start else "") + snippet + (" …" if right < line_end else "")


def _listed(text: str, mentions: list[_Mention], stands_for: dict[str, str]) -> set[_Mention]:
    """The mentions of acts named side by side with another act."""
    groups: list[list[_Mention]] = []
    for m in mentions:
        if groups and _LIST_GAP_RE.fullmatch(text, groups[-1][-1].end, m.start):
            groups[-1].append(m)
        else:
            groups.append([m])
    return {m for g in groups if len({stands_for[x.act.key] for x in g}) > 1 for m in g}


def _last_before(flags: list[bool]) -> list[int]:
    """For each index, the last index up to it whose flag is set (-1 when none)."""
    out: list[int] = []
    last = -1
    for i, flag in enumerate(flags):
        if flag:
            last = i
        out.append(last)
    return out


def _link_acts(
    text: str, refs: list[Reference], mentions: list[_Mention], lines: _Lines | None = None
) -> None:
    """Give each reference its act.

    ``mentions`` are in the document's order and do not overlap, so their ends
    are in order too: the acts next to a reference are found by bisection, and
    the act named earlier on its line through indexes built once (the last
    mention up to each point that is not an amending act, and the last one an
    amending act can stop at). The work grows with the references and the
    mentions, not with their product.
    """
    lines = lines or _Lines(text)
    first: dict[str, Act] = {}
    for mention in mentions:
        first.setdefault(mention.act.key, mention.act)

    def amended(act: Act) -> Act | None:
        """The act an article cited next to ``act`` belongs to, when ``act`` amends others."""
        targets = AMENDS.get(act.key, ())
        named = [t for t in targets if t in first]
        target = named[0] if len(named) == 1 else next(iter(targets), None)
        return (first.get(target) or eu_act(target)) if target else None

    stands_for = {key: (amended(act) or act).key for key, act in first.items()}
    # Acts the words before them say amend another ("as amended by Regulation (EU)
    # 2026/1744"); with the words after them ("amending") and AMENDS, all acts that amend.
    worded = {
        m for m in mentions if _AMENDING_BEFORE_RE.search(text, max(0, m.start - 120), m.start)
    }
    amending = worded | {
        m for m in mentions if m.act.key in AMENDS or _AMENDING_AFTER_RE.match(text, m.end)
    }
    listed = _listed(text, mentions, stands_for)
    # An article with no act near it belongs to the only act the document names:
    # one act that the check reads, and no other (with two, nothing is guessed).
    # An act that amends others stands for the act it amends.
    named = {stands_for[m.act.key] for m in mentions if not m.act.not_read}
    only_act: Act | None = None
    only_by: Act | None = None  # the amending act that only_act stands in for
    if len(named) == 1:
        key = next(iter(named))
        only_act = first.get(key)
        if only_act is None:
            only_by = next(m.act for m in mentions if stands_for[m.act.key] == key)
            only_act = amended(only_by)
    starts = [m.start for m in mentions]
    ends = [m.end for m in mentions]
    # Walking back from a reference, amending acts are passed over; the walk stops
    # at the first other act, unless an amending act was passed: then it stops
    # only at an act of a list or at one of the acts that one amends.
    plain = _last_before([m not in amending for m in mentions])
    stops = {
        key: _last_before(
            [m not in amending and (m in listed or m.act.key in targets) for m in mentions]
        )
        for key, targets in AMENDS.items()
    }
    for ref in refs:
        line_start, _ = lines.bounds(ref.start)
        after: _Mention | None = None
        k = bisect_left(starts, ref.end)
        while k < len(mentions) and starts[k] <= ref.end + _AFTER_WINDOW:
            if not _crosses_sentence(text[ref.end : starts[k]]):
                after = mentions[k]
                break
            k += 1
        before: _Mention | None = None
        k = bisect_right(ends, ref.start) - 1
        while k >= 0 and ends[k] >= ref.start - _BEFORE_WINDOW:
            if re.fullmatch(r"[\s,(:\-–]*", text[ends[k] : ref.start]):
                before = mentions[k]
                break
            k -= 1
        # "Article 50(2), as amended by Regulation (EU) 2026/1744": the words say that
        # act amends the one the article belongs to.
        by = next((m.act for m in (after, before) if m in worded), None)
        after = None if after in worded else after
        before = None if before in worded else before
        earlier: _Mention | None = None
        side_by_side = False
        last = bisect_right(ends, ref.start) - 1  # the last mention that ends before the reference
        stop = plain[last] if last >= 0 else -1
        if by is None and last >= 0 and stop < last and ends[last] >= line_start:
            by = mentions[last].act  # the amending act nearest the reference
        if stop >= 0 and by is not None and by.key in AMENDS:
            m = mentions[stop]
            if m not in listed and m.act.key not in AMENDS[by.key]:
                stop = stops[by.key][stop]
        if stop >= 0 and ends[stop] >= line_start:
            if mentions[stop] in listed:
                side_by_side = True
            else:
                earlier = mentions[stop]
        # "Codice privacy, art. 2-ter, e la Direttiva ...": the closer act wins.
        if after and before and ref.start - before.end < after.start - ref.end:
            after = None
        if after:
            ref.act, ref.raw = after.act, text[ref.start : after.end]
        elif before:
            ref.act, ref.raw = before.act, text[before.start : ref.end]
        elif earlier:
            ref.act, ref.act_inferred = earlier.act, True
        elif by and amended(by):
            ref.act, ref.act_inferred = amended(by), True
        elif only_act and not side_by_side and not (by and by.key == only_act.key):
            ref.act, ref.act_inferred = only_act, True
            by = by or only_by
        if ref.act_inferred:
            ref.amended_by = by
        if not ref.raw:
            ref.raw = text[ref.start : ref.end]
        ref.raw = re.sub(r"\s+", " ", ref.raw).strip()


def _link_quotes(
    text: str, refs: list[Reference], lines: _Lines | None = None
) -> list[tuple[int, int]]:
    """Give each quote to the nearest reference of its line; the spans of the quotes given.

    A reference counts when it ends at most 300 characters before the quote or
    starts at most 150 after it (twice as far: the reference before is
    preferred); on a tie, the first in the document. Only the references in
    those two windows are looked at, found by bisection.
    """
    lines = lines or _Lines(text)
    order = sorted(range(len(refs)), key=lambda i: refs[i].start)
    starts = [refs[i].start for i in order]
    by_end = sorted(range(len(refs)), key=lambda i: refs[i].end)
    ends = [refs[i].end for i in by_end]
    given: list[tuple[int, int]] = []
    for q in _QUOTE_RE.finditer(text):
        quote = next(g for g in q.groups() if g)
        line = lines.index(q.start())
        candidates: list[tuple[int, int]] = []  # (distance, position in refs)
        for k in range(bisect_left(ends, q.start() - 300), bisect_right(ends, q.start())):
            candidates.append((q.start() - ends[k], by_end[k]))
        for k in range(bisect_left(starts, q.end()), bisect_right(starts, q.end() + 150)):
            candidates.append((2 * (starts[k] - q.end()), order[k]))
        best = min((c for c in candidates if lines.index(refs[c[1]].start) == line), default=None)
        if best is not None:
            refs[best[1]].quotes.append(quote.strip())
            given.append((q.start(), q.end()))
    return given


def _within(position: int, spans: list[tuple[int, int]]) -> bool:
    """True when ``position`` is inside one of ``spans`` (in order, not overlapping)."""
    i = bisect_right(spans, (position, math.inf)) - 1
    return i >= 0 and position < spans[i][1]


def extract_references(text: str) -> list[Reference]:
    """Every reference to a provision in ``text``, with its act and quotes.

    What stands inside a quoted passage of law is the law's own wording: an
    article it refers to ("a norma dell'articolo 55") is not a reference of the
    document, and an act it names is not the act of the references around it.
    A quote that no reference outside it claims is read as the document's text.
    """
    mentions = _act_mentions(text)
    lines = _Lines(text)
    named = [(m.start, m.end) for m in mentions]
    refs = [r for r in _references(text) if not _within(r.start, named)]
    quotes = [(q.start(), q.end()) for q in _QUOTE_RE.finditer(text)]
    outside = [r for r in refs if not _within(r.start, quotes)]
    given = _link_quotes(text, outside, lines)
    refs = [r for r in refs if not _within(r.start, given)]
    _link_acts(text, refs, [m for m in mentions if not _within(m.start, given)], lines)
    for ref in refs:
        ref.line = lines.index(ref.start) + 1
        ref.context = _context(text, ref.start, ref.end, lines=lines)
    return refs


def mentioned_acts(text: str) -> list[Act]:
    """The acts a document names, in order of first mention."""
    seen: dict[str, Act] = {}
    for m in _act_mentions(text):
        seen.setdefault(m.act.key, m.act)
    return list(seen.values())


# ─── Documents ───────────────────────────────────────────────────────

_IT_WORDS = frozenset(
    "il lo la gli le di del della dei delle che per con non sono è ai sensi articolo dati".split()
)
_EN_WORDS = frozenset("the of and to in is are that for with by article data shall".split())


def detect_language(text: str) -> str:
    """Return "IT" or "EN", by counting common words (Italian when in doubt).

    The words of the quotes count only when the rest has none: an English
    policy that quotes the law in Italian is in English.
    """
    italian = english = 0
    for part in (_QUOTE_RE.sub(" ", text), text):
        words = re.findall(r"[a-zàèéìòù]+", part.lower())
        italian = sum(w in _IT_WORDS for w in words)
        english = sum(w in _EN_WORDS for w in words)
        if italian or english:
            break
    return "EN" if english > italian else "IT"


# Short words that only one of the two languages has ("non", "per", "in", "a"
# and "no" are in both): a quote of a line or two has enough of them.
_IT_QUOTE_WORDS = frozenset(
    "il lo la i gli le un uno una di del dello della dei degli delle da dal dallo dalla dai dagli "
    "dalle nel nello nella nei negli nelle sul sullo sulla sui sugli sulle l dell nell dall sull "
    "con tra fra che chi cui è e ed o od ma se ai al allo alla alle agli ad ove qualora sono deve "
    "devono può possono essere suo sua suoi sue loro questo questa questi queste tale tali ogni "
    "nonché ovvero oppure entro senza".split()
)
_EN_QUOTE_WORDS = frozenset(
    "the an of and or to on at by for with from that which who whom whose this these those is are "
    "be been being was were has have had shall may must should would not any each such where when "
    "if as its their it than into under within without upon whether".split()
)


def quote_language(quote: str) -> str | None:
    """ "IT" or "EN" by the short words only one of the two has; None when they do not tell."""
    words = re.findall(r"[^\W\d_]+", quote.lower())
    italian = sum(w in _IT_QUOTE_WORDS for w in words)
    english = sum(w in _EN_QUOTE_WORDS for w in words)
    if italian == english:
        return None
    return "IT" if italian > english else "EN"


def load_text(path: Path) -> str:
    """Plain text of a .txt, .md, .html, .docx or .pdf document."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".text"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    if suffix == ".docx":
        import docx

        document = docx.Document(str(path))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if suffix == ".pdf":
        from pypdf import PdfReader

        raw = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        # PDF lines break mid-sentence: rejoin hyphenated words and wrapped lines.
        raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)
        return re.sub(r"(?<![.:;])\n(?!\n)", " ", raw)
    raise ValueError(f"Formato non supportato: {suffix or 'senza estensione'}")
