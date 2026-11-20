"""The answer language of /qa when the request names none.

``QARequest.language`` is optional: an omitted language means the language of
the question (Italian or English), not English for everyone, so an API client
that asks in Italian keeps getting Italian answers and Italian caveats.
"""

from __future__ import annotations

import pytest

from src.api.routers.intelligence import LanguageEnum, QARequest, _answer_language


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Entro quanto tempo il titolare deve notificare una violazione dei dati?", "it"),
        ("Quali sono gli obblighi del deployer secondo l'AI Act?", "it"),
        ("Within how many hours must a controller notify a personal data breach?", "en"),
        ("What are the obligations of a deployer under the AI Act?", "en"),
        ("GDPR art. 33", "it"),  # tells neither: the language of the interface
    ],
)
def test_an_omitted_language_follows_the_question(question: str, expected: str) -> None:
    payload = QARequest(question=question)
    assert payload.language is None
    assert _answer_language(payload) == expected


@pytest.mark.parametrize("language", ["it", "en", "de", "fr"])
def test_a_language_the_request_names_wins(language: str) -> None:
    payload = QARequest(
        question="Within how many hours must a controller notify a personal data breach?",
        language=LanguageEnum(language),
    )
    assert _answer_language(payload) == language
