"""Article references written in a question (src/nlp/embedding/article_refs.py)."""

import pytest

from src.nlp.embedding.article_refs import ArticleRef, article_refs, paragraph_range


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "Quali imprese devono comunicare in che misura le loro attività sono allineate alla "
            "Tassonomia ai sensi dell'art. 8 del regolamento (UE) 2020/852?",
            [ArticleRef("8", None, "32020R0852")],
            id="it-regulation",
        ),
        pytest.param(
            "Quali imprese sono tenute alla rendicontazione di sostenibilità ai sensi "
            "dell'art. 19 bis della direttiva 2013/34/UE?",
            [ArticleRef("19a", None, "32013L0034")],
            id="it-latin-suffix-directive",
        ),
        pytest.param(
            "What are the criteria for a 'large undertaking' under Article 3(4) of "
            "Directive 2013/34/EU?",
            [ArticleRef("3", 4, "32013L0034")],
            id="en-paragraph-directive",
        ),
        pytest.param(
            "Quali elementi deve contenere come minimo una DPIA ai sensi dell'art. 35, "
            "paragrafo 7, del GDPR?",
            [ArticleRef("35", 7, None)],
            id="it-paragraph-act-by-name",
        ),
        pytest.param(
            "Which size thresholds trigger individual sustainability reporting under "
            "Article 19a(1) of the Accounting Directive?",
            [ArticleRef("19a", 1, None)],
            id="en-letter-suffix",
        ),
        pytest.param(
            "Does Article 92 of Regulation (EU) No 575/2013 set the own funds requirements?",
            [ArticleRef("92", None, "32013R0575")],
            id="regulation-number-before-year",
        ),
        pytest.param(
            "Cosa prevede l'articolo 2 della direttiva 95/46/CE?",
            [ArticleRef("2", None, "31995L0046")],
            id="two-digit-year",
        ),
        pytest.param(
            "Che cosa chiede l'art. 5 del regolamento delegato (UE) 2023/2486?",
            [ArticleRef("5", None, "32023R2486")],
            id="delegated-regulation",
        ),
        pytest.param(
            "Cosa dice l'art. 48 nonies, comma 2?",
            [ArticleRef("48h", 2, None)],
            id="nonies-and-comma",
        ),
        pytest.param(
            "Secondo gli artt. 5 e 6 del GDPR quali principi valgono?",
            [ArticleRef("5")],
            id="plural-first-number-only",
        ),
        pytest.param(
            "Il chatbot sul sito deve dichiarare di essere un'intelligenza artificiale?",
            [],
            id="no-article",
        ),
        pytest.param(
            "Part 2 of the smart contract and the artificial intelligence of 2024",
            [],
            id="no-false-match-inside-words",
        ),
    ],
)
def test_article_refs(question, expected):
    assert article_refs(question) == expected


def test_an_act_far_from_the_article_is_not_its_act():
    question = (
        "Secondo l'art. 8, che cosa devono pubblicare le imprese grandi e quotate, "
        "e come cambia con il regolamento (UE) 2020/852?"
    )
    assert article_refs(question) == [ArticleRef("8", None, None)]


def test_references_are_listed_once_and_at_most_limit():
    question = "art. 6 GDPR, art. 6 GDPR, art. 7, art. 9, art. 13"
    assert [r.number for r in article_refs(question)] == ["6", "7", "9"]
    assert [r.number for r in article_refs(question, limit=5)] == ["6", "7", "9", "13"]


@pytest.mark.parametrize(
    ("ref", "labels"),
    [
        (ArticleRef("8"), ["Art. 8"]),
        (ArticleRef("19a"), ["Art. 19a", "Art. 19 bis"]),
        (ArticleRef("29b"), ["Art. 29b", "Art. 29 ter"]),
        (ArticleRef("48h"), ["Art. 48h", "Art. 48 novies"]),
    ],
)
def test_labels_cover_both_languages(ref, labels):
    # The corpus labels inserted articles "Art. 19a" in English, "Art. 19 bis" in Italian.
    assert ref.labels() == labels


@pytest.mark.parametrize(
    ("value", "paragraphs"),
    [
        ("7", [7]),
        ("6-9", [6, 7, 8, 9]),
        (" 10 - 11 ", [10, 11]),
        (None, None),
        ("", None),
        ("1(a)", None),
    ],
)
def test_paragraph_range(value, paragraphs):
    found = paragraph_range(value)
    assert (list(found) if found is not None else None) == paragraphs
