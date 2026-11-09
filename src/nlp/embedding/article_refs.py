"""
Article references written in a question.

"art. 8 del regolamento (UE) 2020/852", "Article 19a(1) of Directive 2013/34/EU",
"art. 35, paragrafo 7, del GDPR": a question that names an article should get
that article, but neither search reliably finds it. Among the golden v2
questions (docs/MODELS.md, section 3.1) the dense search ranked Art. 8 of the
Taxonomy Regulation 81st for a question naming it, and the chunks of Art. 19a
of Directive 2013/34/EU lost to the recitals of the act amending it.
hybrid_search looks the named articles up (HybridIndexer._named_article_points)
and fuses them as a third ranking.

Labels follow the corpus: the Italian texts write inserted articles with the
Latin suffix ("Art. 19 bis"), the English ones with a letter ("Art. 19a"), so a
reference to either matches both. The act is read from its number (CELEX
3<year><L|R><number>); an act named only by its short name ("del GDPR") is
left to the framework filter of the search.
"""

import re
from dataclasses import dataclass

# Suffixes of inserted articles, in order: "19 bis" = "19a", "29 ter" = "29b".
LATIN_SUFFIXES = (
    "bis",
    "ter",
    "quater",
    "quinquies",
    "sexies",
    "septies",
    "octies",
    "novies",
    "decies",
)
_LETTERS = "abcdefghi"
# "nonies" is an older spelling of "novies".
_LATIN_TO_LETTER = {**dict(zip(LATIN_SUFFIXES, _LETTERS, strict=True)), "nonies": "h"}

_ARTICLE_RE = re.compile(
    r"\b(?:articol[oi]|articles?|artt?\.|art)\s*"
    r"(?P<number>\d{1,3})"
    rf"(?:\s*(?P<latin>{'|'.join(_LATIN_TO_LETTER)})\b|(?P<letter>[a-i])(?![a-z]))?"
    # "19a(1)" or "art. 35, paragrafo 7" / "par. 7" / "comma 7" / "paragraph 7"
    r"(?:\s*\((?P<paren>\d{1,2})\)|,?\s*(?:paragrafo|paragraph|par\.|comma)\s*(?P<word>\d{1,2}))?",
    re.IGNORECASE,
)
# "della direttiva 2013/34/UE", "del regolamento (UE) 2020/852", "of Regulation
# (EU) No 575/2013", "regolamento delegato (UE) 2023/2486".
_ACT_RE = re.compile(
    r"\b(?P<kind>direttiva|directive|regolamento|regulation)"
    r"(?:\s+(?:delegato|di esecuzione|delegated|implementing))?"
    r"(?:\s*\((?:UE|EU|CE|EC|CEE|EEC)\))?"
    r"(?:\s*(?:n\.|no\.?|nr\.?))?\s*"
    r"(?P<first>\d{2,4})/(?P<second>\d{1,4})"
    r"(?:/(?:UE|EU|CE|EC|CEE|EEC))?",
    re.IGNORECASE,
)
# How far after the article the act may start: " della direttiva", " of Regulation (EU)".
_ACT_WINDOW = 25
_ACT_SEARCH = 60


@dataclass(frozen=True)
class ArticleRef:
    """An article named in a question: number with its letter ("19a"), paragraph, act."""

    number: str
    paragraph: int | None = None
    celex: str | None = None

    def labels(self) -> list[str]:
        """The ``article`` payload labels of this article in every language."""
        digits = self.number.rstrip(_LETTERS)
        letter = self.number[len(digits) :]
        if not letter:
            return [f"Art. {digits}"]
        return [f"Art. {digits}{letter}", f"Art. {digits} {LATIN_SUFFIXES[_LETTERS.index(letter)]}"]


def _celex(kind: str, first: str, second: str) -> str:
    """CELEX of a directive or regulation from its number.

    Directives and recent regulations are numbered year/number ("2013/34",
    "2020/852"), regulations before 2015 number/year ("575/2013").
    """
    if (
        len(second) == 4
        and second[:2] in ("19", "20")
        and not (len(first) == 4 and first[:2] in ("19", "20"))
    ):
        year, number = second, first
    elif len(first) == 2:  # 95/46/CE
        year, number = ("19" if int(first) > 50 else "20") + first, second
    else:
        year, number = first, second
    sector_type = "L" if kind.lower().startswith("dir") else "R"
    return f"3{year}{sector_type}{int(number):04d}"


def article_refs(text: str, limit: int = 3) -> list[ArticleRef]:
    """The articles ``text`` names, in order of mention, at most ``limit``."""
    refs: list[ArticleRef] = []
    for m in _ARTICLE_RE.finditer(text or ""):
        number = m.group("number")
        if m.group("latin"):
            number += _LATIN_TO_LETTER[m.group("latin").lower()]
        elif m.group("letter"):
            number += m.group("letter").lower()
        paragraph = m.group("paren") or m.group("word")
        act = _ACT_RE.search(text, m.end(), m.end() + _ACT_SEARCH)
        celex = None
        if act and act.start() - m.end() <= _ACT_WINDOW:
            celex = _celex(act.group("kind"), act.group("first"), act.group("second"))
        ref = ArticleRef(number, int(paragraph) if paragraph else None, celex)
        if ref not in refs:
            refs.append(ref)
        if len(refs) == limit:
            break
    return refs


def paragraph_range(value: object) -> range | None:
    """Paragraphs a chunk holds, from its ``paragraph`` payload ("7", "6-9"); None if unknown."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", str(value or ""))
    if not m:
        return None
    first = int(m.group(1))
    return range(first, int(m.group(2) or first) + 1)
