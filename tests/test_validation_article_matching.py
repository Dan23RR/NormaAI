"""Golden-set article matching across languages.

Found on 2026-10-24: Italian answers cited "Art. 19 bis" and "Art. 29 bis",
the right provisions, but the golden metric expected "Art. 19a(1)" and
"Art. 29a(1)" and counted them as misses. EU acts number inserted articles
with letters in English and Latin adverbs in Italian.
"""

import pytest

from tests.validation.metrics import articles_match, normalize_article


@pytest.mark.parametrize(
    ("italian", "english"),
    [
        ("Art. 19 bis", "Art. 19a"),
        ("Art. 29 bis(8)", "Art. 29a(8)"),
        ("Art. 29 ter", "Art. 29b"),
        ("Art. 29-quinquies", "Art. 29d"),
        ("Art. 48 decies(1)", "Art. 48i(1)"),
    ],
)
def test_latin_adverbs_normalise_to_letters(italian, english):
    assert normalize_article(italian) == normalize_article(english)


def test_italian_citation_matches_the_expected_english_article():
    assert articles_match("Art. 19a(1)", "Art. 19 bis")
    assert articles_match("Art. 29a", "Art. 29 bis(8)")
    # Different paragraphs of the same article stay different.
    assert not articles_match("Art. 29a(1)", "Art. 29 bis(8)")


def test_different_insertions_do_not_match():
    assert not articles_match("Art. 19a", "Art. 19 ter")
    assert normalize_article("Art. 50") == normalize_article("Article 50")
