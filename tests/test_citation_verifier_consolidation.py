"""Two things the live golden run of 2026-11-19 showed the verifier must tolerate.

- EUR-Lex writes markers inside a consolidated text (a down triangle with "B" or
  "M6" before the original wording and each amendment, a right triangle before
  an inserted passage, a left triangle after it). They are not part of the law
  and the model quotes the wording without them: three quotes of the Accounting
  Directive and the CSRD were left unverified because of them.
- The model sometimes writes the label's "CELEX 32024R2847" as the framework of
  a citation: six correct quotes of the CRA were then found only "in another
  act" and not verified.

The markers are built with chr() so that no tool turns an escape into them.
"""

from __future__ import annotations

from src.agents.citation_verifier import (
    annotate_citations,
    normalize,
    normalize_framework,
    verify_citation,
)

DOWN = chr(0x25BC)
RIGHT = chr(0x25BA)
LEFT = chr(0x25C4)

ART_3_4 = (
    "4. Large undertakings shall be undertakings which on their balance sheet dates exceed "
    "at least two of the three following criteria:\n"
    f"{DOWN}M6\n"
    "(a) balance sheet total: EUR 25 000 000;\n"
    "(b) net turnover: EUR 50 000 000;\n"
    f"{DOWN}B\n"
    "(c) average number of employees during the financial year: 250."
)
ACCOUNTING_CHUNK = {
    "id": "acc-3",
    "text": ART_3_4,
    "framework": "CSRD",
    "celex": "32013L0034",
    "article": "Art. 3",
    "lang": "en",
}

CRA_14 = (
    "2. For the purposes of the notification referred to in paragraph 1, the manufacturer "
    "shall submit: (a) an early warning notification of an actively exploited vulnerability, "
    "without undue delay and in any event within 24 hours of the manufacturer becoming aware "
    "of it, indicating, where applicable, the Member States on the territory of which the "
    "manufacturer is aware that their product with digital elements has been made available;"
)
CRA_CHUNK = {
    "id": "cra-14",
    "text": CRA_14,
    "framework": "CRA",
    "celex": "32024R2847",
    "article": "Art. 14",
    "lang": "en",
}


def test_consolidation_markers_read_as_a_space() -> None:
    assert normalize(f"criteria:\n{DOWN}M6\n(a) balance") == "criteria: (a) balance"
    assert (
        normalize(f"successiva: {LEFT}\n{DOWN}M2\ni) alle imprese") == "successiva: i) alle imprese"
    )
    assert normalize(f"a {RIGHT}M2 inserted {LEFT} text") == "a inserted text"


def test_a_word_after_a_bare_marker_is_kept() -> None:
    assert normalize(f"{DOWN}Balance sheet") == "balance sheet"


def test_a_quote_without_the_markers_is_verified_and_shown_without_them() -> None:
    citation = {
        "framework": "32013L0034",
        "reference": "Art. 3(4)",
        "quote_snippet": (
            "Large undertakings shall be undertakings which on their balance sheet dates "
            "exceed at least two of the three following criteria: (a) balance sheet total: "
            "EUR 25 000 000; (b) net turnover: EUR 50 000 000; (c) average number of "
            "employees during the financial year: 250"
        ),
    }
    result = verify_citation(citation, [ACCOUNTING_CHUNK])
    assert result.verified is True
    assert result.match == "exact"
    assert result.level == "article"
    assert DOWN not in (result.official_quote or "")
    assert "EUR 25 000 000" in (result.official_quote or "")


def test_a_different_threshold_is_still_a_difference() -> None:
    citation = {
        "framework": "32013L0034",
        "reference": "Art. 3(4)",
        "quote_snippet": (
            "exceed at least two of the three following criteria: (a) balance sheet total: "
            "EUR 20 000 000; (b) net turnover: EUR 40 000 000"
        ),
    }
    assert verify_citation(citation, [ACCOUNTING_CHUNK]).verified is False


def test_celex_prefix_in_the_framework_is_the_celex() -> None:
    for written in (
        "CELEX 32024R2847",
        "CELEX:32024R2847",
        "celex 32024r2847",
        " CELEX  32024R2847 ",
    ):
        assert normalize_framework(written) == "32024R2847", written
    assert normalize_framework("CELEX") == "CELEX"


def test_a_citation_with_the_celex_label_as_framework_is_verified_in_chiedi() -> None:
    citation = {
        "framework": "CELEX 32024R2847",
        "reference": "Art. 14(2)(a)",
        "quote_snippet": (
            "an early warning notification of an actively exploited vulnerability, without "
            "undue delay and in any event within 24 hours of the manufacturer becoming aware of it"
        ),
    }
    assert verify_citation(citation, [CRA_CHUNK]).level == "article"
    result = annotate_citations({"answer": "x", "citations": [citation]}, [CRA_CHUNK])
    assert result["verified_citations"] == 1
    assert result["citations"][0]["verified"] is True
    assert not result["citations"][0].get("found_elsewhere")
