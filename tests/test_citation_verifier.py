"""Deterministic citation verification (src/agents/citation_verifier.py).

A citation is "Verificata" only when its quote is found word for word in a
chunk the pipeline retrieved. These tests pin the rule: normalization, the
article -> framework -> any fallback, omissions, the too-generic threshold,
the tolerant (fuzzy) match, the provenance fields built server-side, the
annotation on copies and the flag / strict policy.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.citation_verifier import (
    CITATION_FIELDS,
    UNVERIFIED_ABSTENTION_EN,
    UNVERIFIED_ABSTENTION_IT,
    UNVERIFIED_ABSTENTION_REASON,
    UNVERIFIED_CAVEAT_EN,
    UNVERIFIED_CAVEAT_IT,
    VerificationResult,
    annotate_citations,
    apply_unverified_policy,
    article_label,
    base_celex,
    citation_counters,
    count_verified,
    eurlex_url,
    normalize,
    normalize_framework,
    parse_article,
    policy_mode,
    unverified_policy_applies,
    verify_citation,
    verify_citations,
)

RSQUO = "\N{RIGHT SINGLE QUOTATION MARK}"
NBSP = "\N{NO-BREAK SPACE}"

ART_50_IT = (
    "Articolo 50\n"
    "Obblighi di trasparenza per i fornitori e i deployer di determinati sistemi di IA\n"
    "1. I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente "
    "con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche\n"
    "interessate siano informate del fatto di stare interagendo con un sistema di IA.\n"
    "2. I fornitori di sistemi di IA che generano contenuti audio, immagine, video o testuali "
    "sintetici garantiscono che gli output del sistema di IA siano marcati in un formato "
    "leggibile meccanicamente e rilevabili come generati o manipolati artificialmente.\n"
    f"3. Gli obblighi di cui ai paragrafi 1 e 2 lasciano impregiudicati gli obblighi di "
    f"trasparenza stabiliti dal diritto dell{RSQUO}Unione o nazionale."
)
ART_52_IT = (
    "Articolo 52\n"
    "Procedura\n"
    "1. Il fornitore informa la Commissione senza ritardo e in ogni caso entro due settimane."
)
GDPR_5_EN = (
    "Article 5\n"
    "Principles relating to processing of personal data\n"
    "1. Personal data shall be:\n"
    "(a) processed lawfully, fairly and in a transparent manner in relation to the data subject;"
)


def _chunk(text, *, chunk_id="pt-ai-50", article="Art. 50", **overrides):
    chunk = {
        "id": chunk_id,
        "text": text,
        "framework": "AI_ACT",
        "article": article,
        "celex": "32024R1689",
        "source_celex": "02024R1689-20260727",
        "lang": "IT",
        "consolidated_as_of": "2026-07-27",
    }
    chunk.update(overrides)
    return chunk


def _corpus():
    return [
        _chunk(ART_50_IT),
        _chunk(ART_52_IT, chunk_id="pt-ai-52", article="Art. 52"),
        _chunk(
            GDPR_5_EN,
            chunk_id="pt-gdpr-5",
            article="Art. 5",
            framework="GDPR",
            celex="32016R0679",
            source_celex="32016R0679",
            lang="EN",
            consolidated_as_of=None,
        ),
    ]


def _cite(quote, *, framework="AI_ACT", reference="Art. 50"):
    return {"framework": framework, "reference": reference, "quote_snippet": quote}


# ─── normalize ───────────────────────────────────────────────────────


class TestNormalize:
    def test_nfkc_and_casefold(self):
        assert normalize("\N{LATIN SMALL LIGATURE FI}nalit\N{LATIN SMALL LETTER A WITH GRAVE}") == (
            "finalit\N{LATIN SMALL LETTER A WITH GRAVE}"
        )
        assert normalize("\N{FULLWIDTH LATIN CAPITAL LETTER A}BC") == "abc"
        assert normalize("STRASSE") == normalize("Stra\N{LATIN SMALL LETTER SHARP S}e")

    def test_typographic_quotes_and_apostrophes_become_ascii(self):
        assert normalize(f"dell{RSQUO}articolo") == "dell'articolo"
        assert normalize("l\N{LEFT SINGLE QUOTATION MARK}atto") == "l'atto"
        assert normalize(
            "il \N{LEFT DOUBLE QUOTATION MARK}fornitore\N{RIGHT DOUBLE QUOTATION MARK} e"
        ) == ('il "fornitore" e')
        assert normalize(
            "il \N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}fornitore"
            "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK} e"
        ) == ('il "fornitore" e')

    def test_every_dash_becomes_a_hyphen(self):
        for dash in (
            "\N{EN DASH}",
            "\N{EM DASH}",
            "\N{MINUS SIGN}",
            "\N{NON-BREAKING HYPHEN}",
            "\N{HYPHEN}",
            "\N{FIGURE DASH}",
        ):
            assert normalize(f"2026{dash}2027 periodo") == "2026-2027 periodo", repr(dash)

    def test_unicode_spaces_soft_hyphens_and_zero_width_characters(self):
        assert normalize(f"articolo{NBSP}50") == "articolo 50"
        assert normalize("articolo\N{NARROW NO-BREAK SPACE}50") == "articolo 50"
        assert normalize("articolo\N{THIN SPACE}50") == "articolo 50"
        assert normalize("regola\N{SOFT HYPHEN}mento") == "regolamento"
        assert normalize("regola\N{ZERO WIDTH SPACE}mento") == "regolamento"

    def test_whitespace_is_collapsed(self):
        assert normalize("  sono \n\t progettati\r\n  e   sviluppati ") == (
            "sono progettati e sviluppati"
        )

    def test_surrounding_quotes_punctuation_and_ellipses_are_stripped(self):
        quote = (
            "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}\N{HORIZONTAL ELLIPSIS}"
            "I fornitori garantiscono che\N{HORIZONTAL ELLIPSIS}"
            "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}"
        )
        assert normalize(quote) == "i fornitori garantiscono che"
        assert normalize('"[...] i fornitori garantiscono [...]".') == "i fornitori garantiscono"
        assert normalize("(...) garantiscono che;") == "garantiscono che"

    def test_decomposed_accents_equal_composed_ones(self):
        assert normalize("perch\N{LATIN SMALL LETTER E}\N{COMBINING ACUTE ACCENT}") == normalize(
            "perch\N{LATIN SMALL LETTER E WITH ACUTE}"
        )

    def test_empty_and_none(self):
        assert normalize("") == ""
        assert normalize(None) == ""


# ─── References ──────────────────────────────────────────────────────


class TestParseArticle:
    @pytest.mark.parametrize(
        "reference",
        ["Art. 50", "articolo 50", "50", "50(1)", "art. 50, par. 1", "Article 50", "ART.50"],
    )
    def test_every_form_of_article_50(self, reference):
        assert parse_article(reference) == "art:50"

    def test_letter_and_latin_suffixes(self):
        assert parse_article("Art. 19a(1)") == "art:19a"
        assert parse_article("Art. 12 bis") == "art:12bis"
        assert parse_article("articolo 12-bis, comma 2") == "art:12bis"
        # A word after the number is not a suffix.
        assert parse_article("Art. 50 paragraph 2") == "art:50"

    def test_recitals_and_annexes(self):
        assert parse_article("Recital 45") == "recital:45"
        assert parse_article("considerando (45)") == "recital:45"
        assert parse_article("Annex III") == "annex:III"
        assert parse_article("Allegato III, punto 4") == "annex:III"

    def test_first_article_of_a_list(self):
        assert parse_article("Articles 13 and 14") == "art:13"

    @pytest.mark.parametrize("reference", ["", None, "Regulation (EU) 2024/1689", "Preamble"])
    def test_no_article(self, reference):
        assert parse_article(reference) is None

    def test_labels(self):
        assert article_label("art:50") == "Art. 50"
        assert article_label("art:19a") == "Art. 19a"
        assert article_label("art:12bis") == "Art. 12 bis"
        assert article_label("recital:45") == "Recital 45"
        assert article_label("annex:III") == "Annex III"
        assert article_label(None) is None


class TestNormalizeFramework:
    @pytest.mark.parametrize(
        "name, key",
        [
            ("AI_ACT", "AI_ACT"),
            ("AI Act", "AI_ACT"),
            ("ai-act", "AI_ACT"),
            ("EU AI Act", "AI_ACT"),
            ("nis 2", "NIS2"),
            ("EU Taxonomy", "TAXONOMY"),
            ("ESRS", "CSRD"),
            ("CSRD Directive", "CSRD"),
            ("02024R1689-20260727", "32024R1689"),
            ("Some Other Act", "SOME_OTHER_ACT"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_canonical_keys(self, name, key):
        assert normalize_framework(name) == key


class TestCelexAndUrl:
    def test_base_act_from_consolidated_ids(self):
        assert base_celex({"celex": "02024R1689-20260727"}) == "32024R1689"
        assert base_celex({"source_celex": "02024R1689-20260727"}) == "32024R1689"
        assert base_celex({"celex": "32024R1689", "source_celex": "02024R1689-20260727"}) == (
            "32024R1689"
        )

    def test_non_celex_identifier_is_kept_and_has_no_url(self):
        assert base_celex({"celex": "DOC_acme_policy"}) == "DOC_acme_policy"
        assert eurlex_url("DOC_acme_policy", "IT") is None
        assert base_celex({}) is None

    def test_url_in_the_chunk_language(self):
        assert eurlex_url("32024R1689", "it") == (
            "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689"
        )
        assert eurlex_url("32024R1689", None) == (
            "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689"
        )

    def test_verified_citation_from_a_consolidated_chunk(self):
        # The chunk only knows the consolidated id: the citation names the base
        # act, links to it in the chunk's language and keeps the version date.
        chunk = {
            "id": 7,
            "framework": "AI_ACT",
            "article": "Art. 50",
            "celex": "02024R1689-20260727",
            "lang": "IT",
            "text": ART_50_IT,
        }
        out = verify_citation(
            _cite("garantiscono che gli output del sistema di IA siano marcati"), [chunk]
        )
        assert out.verified is True
        assert out.celex == "32024R1689"
        assert out.url == "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689"
        assert out.consolidated_as_of == "2026-07-27"
        assert out.chunk_id == "7"


# ─── verify_citation ─────────────────────────────────────────────────


class TestExactMatch:
    def test_exact_quote_in_the_cited_article(self):
        quote = (
            "garantiscono che gli output del sistema di IA siano marcati in un formato leggibile"
        )
        out = verify_citation(_cite(quote, reference="Art. 50(2)"), _corpus())
        assert out == VerificationResult(
            verified=True,
            match="exact",
            level="article",
            chunk_id="pt-ai-50",
            celex="32024R1689",
            article="Art. 50",
            paragraph="2",
            lang="IT",
            consolidated_as_of="2026-07-27",
            url="https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689",
            official_quote=quote,
        )

    def test_match_is_case_insensitive_and_returns_the_official_wording(self):
        out = verify_citation(_cite("I FORNITORI GARANTISCONO CHE I SISTEMI DI IA"), _corpus())
        assert out.verified and out.match == "exact"
        assert out.official_quote == "I fornitori garantiscono che i sistemi di IA"
        assert out.paragraph == "1"

    def test_whitespace_and_line_breaks(self):
        # The official text breaks the line after "persone fisiche"; the model's
        # quote has single spaces (and the reverse also holds).
        quote = "progettati e sviluppati in modo tale che le persone fisiche interessate siano informate"
        out = verify_citation(_cite(quote), _corpus())
        assert out.verified and out.match == "exact"
        assert out.official_quote == (
            "progettati e sviluppati in modo tale che le persone fisiche\n"
            "interessate siano informate"
        )
        spaced = "sono   progettati\n\ne sviluppati  in modo tale"
        assert verify_citation(_cite(spaced), _corpus()).verified

    def test_curly_official_apostrophe_vs_straight_quote(self):
        out = verify_citation(_cite("stabiliti dal diritto dell'Unione o nazionale"), _corpus())
        assert out.verified and out.match == "exact"
        # The interface shows the official typography, not the model's.
        assert out.official_quote == f"stabiliti dal diritto dell{RSQUO}Unione o nazionale"

    def test_straight_official_apostrophe_vs_curly_quote(self):
        chunk = _chunk("Si applica l'articolo 6 del presente regolamento a tutti i fornitori.")
        out = verify_citation(
            _cite(f"Si applica l{RSQUO}articolo 6 del presente regolamento"), [chunk]
        )
        assert out.verified and out.match == "exact"
        assert out.official_quote == "Si applica l'articolo 6 del presente regolamento"

    def test_non_breaking_spaces_and_typographic_dashes_in_the_official_text(self):
        chunk = _chunk(f"Il periodo 2026\N{EN DASH}2027 si applica a decorrere dal{NBSP}2 agosto.")
        out = verify_citation(
            _cite("il periodo 2026-2027 si applica a decorrere dal 2 agosto"), [chunk]
        )
        assert out.verified and out.match == "exact"


class TestOmissions:
    @pytest.mark.parametrize("marker", ["[...]", "...", "\N{HORIZONTAL ELLIPSIS}", "(...)"])
    def test_segments_found_in_order(self, marker):
        quote = (
            f"I fornitori garantiscono che i sistemi di IA {marker} "
            "siano informate del fatto di stare interagendo con un sistema di IA"
        )
        out = verify_citation(_cite(quote, reference="art. 50, par. 1"), _corpus())
        assert out.verified and out.match == "exact" and out.level == "article"
        assert out.official_quote == (
            "I fornitori garantiscono che i sistemi di IA [...] "
            "siano informate del fatto di stare interagendo con un sistema di IA"
        )

    def test_segments_out_of_order_are_not_verified(self):
        quote = (
            "siano informate del fatto di stare interagendo [...] "
            "I fornitori garantiscono che i sistemi di IA"
        )
        assert verify_citation(_cite(quote), _corpus()).verified is False

    def test_segments_must_be_in_the_same_chunk(self):
        quote = (
            "I fornitori garantiscono che i sistemi di IA [...] "
            "informa la Commissione senza ritardo"
        )
        assert verify_citation(_cite(quote), _corpus()).verified is False

    def test_segments_shorter_than_12_characters_are_not_required(self):
        # "di IA xyz" (9 chars) is not in the text, but it is too short to check.
        quote = (
            "I fornitori garantiscono che i sistemi [...] di IA xyz [...] "
            "stare interagendo con un sistema di IA"
        )
        assert verify_citation(_cite(quote), _corpus()).verified is True

    def test_only_short_segments_is_too_generic(self):
        assert (
            verify_citation(_cite("I fornitori [...] di IA [...] sono"), _corpus()).verified
            is False
        )


class TestLevels:
    def test_wrong_article_falls_back_to_the_framework(self):
        quote = "garantiscono che gli output del sistema di IA siano marcati"
        out = verify_citation(_cite(quote, reference="Art. 52"), _corpus())
        assert out.verified and out.level == "framework"
        # The provenance is the article where the passage really is.
        assert out.article == "Art. 50" and out.chunk_id == "pt-ai-50"

    def test_wrong_framework_falls_back_to_any_chunk(self):
        quote = "garantiscono che gli output del sistema di IA siano marcati"
        out = verify_citation(_cite(quote, framework="GDPR", reference="Art. 5"), _corpus())
        assert out.verified and out.level == "any"
        assert out.celex == "32024R1689" and out.article == "Art. 50"

    def test_quote_from_another_act_in_the_evidence(self):
        out = verify_citation(
            _cite("processed lawfully, fairly and in a transparent manner"), _corpus()
        )
        assert out.verified and out.level == "any"
        assert out.celex == "32016R0679" and out.lang == "EN" and out.article == "Art. 5"
        assert out.url == "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679"
        assert out.consolidated_as_of is None

    def test_quote_from_an_act_that_was_not_retrieved(self):
        out = verify_citation(
            _cite(
                "the controller shall be responsible for, and be able to demonstrate compliance",
                framework="GDPR",
                reference="Art. 5(2)",
            ),
            _corpus(),
        )
        assert out == VerificationResult()

    def test_no_framework_named_searches_everything(self):
        out = verify_citation(
            {"quote_snippet": "garantiscono che gli output del sistema di IA siano marcati"},
            _corpus(),
        )
        assert out.verified and out.level == "any"

    def test_framework_alias_matches_at_article_level(self):
        out = verify_citation(
            _cite(
                "informa la Commissione senza ritardo", framework="AI Act", reference="articolo 52"
            ),
            _corpus(),
        )
        assert out.verified and out.level == "article" and out.chunk_id == "pt-ai-52"

    def test_legacy_chunk_with_article_number_only(self):
        chunk = {"id": "old", "framework": "GDPR", "article_number": "5", "text": GDPR_5_EN}
        out = verify_citation(
            _cite(
                "Personal data shall be: (a) processed lawfully",
                framework="GDPR",
                reference="Art. 5(1)(a)",
            ),
            [chunk],
        )
        assert out.verified and out.level == "article" and out.article == "Art. 5"
        assert out.celex is None and out.url is None and out.lang is None

    def test_act_listed_under_several_frameworks(self):
        chunk = _chunk(
            "Gli Stati membri recepiscono la presente direttiva entro il termine stabilito.",
            framework="CSRD",
            frameworks=["CSRD", "CSDDD"],
            article="Art. 4",
            celex="32026L0470",
            source_celex="32026L0470",
        )
        out = verify_citation(
            _cite(
                "recepiscono la presente direttiva entro il termine",
                framework="CSDDD",
                reference="Art. 4",
            ),
            [chunk],
        )
        assert out.verified and out.level == "article"

    def test_article_level_is_preferred_to_another_article(self):
        # The same sentence in two articles: the cited one wins.
        sentence = "Il fornitore conserva la documentazione tecnica per dieci anni."
        chunks = [
            _chunk(f"Articolo 18\n1. {sentence}", chunk_id="a18", article="Art. 18"),
            _chunk(f"Articolo 19\n1. {sentence}", chunk_id="a19", article="Art. 19"),
        ]
        out = verify_citation(_cite(sentence, reference="Art. 19"), chunks)
        assert out.chunk_id == "a19" and out.level == "article"


class TestTooGenericOrMissing:
    def test_quote_under_20_characters(self):
        assert verify_citation(_cite("I fornitori"), _corpus()).verified is False

    def test_quote_under_4_words(self):
        assert len(normalize("garantiscono rilevabili artificialmente")) >= 20
        assert (
            verify_citation(_cite("garantiscono rilevabili artificialmente"), _corpus()).verified
            is False
        )

    def test_fabricated_quote(self):
        out = verify_citation(
            _cite("i deployer pagano una sanzione di dieci milioni di euro entro trenta giorni"),
            _corpus(),
        )
        assert out == VerificationResult()

    def test_no_quote(self):
        assert verify_citation({"framework": "AI_ACT", "reference": "Art. 50"}, _corpus()) == (
            VerificationResult()
        )

    def test_no_chunks(self):
        quote = "garantiscono che gli output del sistema di IA siano marcati"
        assert verify_citation(_cite(quote), []) == VerificationResult()
        assert verify_citation(_cite(quote), [{"text": ""}, {"framework": "AI_ACT"}]) == (
            VerificationResult()
        )

    def test_not_a_dict(self):
        assert verify_citation("AI Act, Art. 50", _corpus()) == VerificationResult()


class TestFuzzyMatch:
    def test_one_character_difference(self):
        # "meccanicamante": a one-letter slip of the model.
        quote = "siano marcati in un formato leggibile meccanicamante e rilevabili"
        out = verify_citation(_cite(quote), _corpus())
        assert out.verified and out.match == "fuzzy" and out.level == "article"
        assert (
            out.official_quote
            == "siano marcati in un formato leggibile meccanicamente e rilevabili"
        )

    def test_missing_comma(self):
        quote = "contenuti audio immagine, video o testuali sintetici garantiscono"
        out = verify_citation(_cite(quote), _corpus())
        assert out.verified and out.match == "fuzzy"
        assert (
            out.official_quote
            == "contenuti audio, immagine, video o testuali sintetici garantiscono"
        )

    def test_fuzzy_inside_an_omission_segment(self):
        quote = (
            "I fornitori garantiscono che i sistemi di IA [...] "
            "stare interagendo con un sistemma di IA"
        )
        out = verify_citation(_cite(quote), _corpus())
        assert out.verified and out.match == "fuzzy"

    def test_paraphrase_is_not_accepted(self):
        quote = (
            "gli output dei sistemi di IA devono essere marcati in formato leggibile da macchina"
        )
        assert verify_citation(_cite(quote), _corpus()).verified is False

    def test_exact_in_the_article_beats_fuzzy_elsewhere(self):
        out = verify_citation(_cite("Il fornitore informa la Commissione senza ritardo"), _corpus())
        assert out.match == "exact"


class TestParagraph:
    def test_paragraph_from_the_numbered_line(self):
        out = verify_citation(_cite("Gli obblighi di cui ai paragrafi 1 e 2 lasciano"), _corpus())
        assert out.paragraph == "3"

    def test_paragraph_field_when_the_text_has_no_numbers(self):
        chunk = _chunk("Il fornitore conserva la documentazione tecnica.", paragraph="3-4")
        out = verify_citation(_cite("Il fornitore conserva la documentazione tecnica"), [chunk])
        assert out.paragraph == "3-4"

    def test_no_paragraph_for_a_recital(self):
        chunk = _chunk(
            "(45) Le pratiche vietate dal diritto dell'Unione non dovrebbero essere pregiudicate.",
            article="Recital 45",
        )
        out = verify_citation(
            _cite("Le pratiche vietate dal diritto dell'Unione", reference="Recital 45"), [chunk]
        )
        assert out.verified and out.level == "article"
        assert out.article == "Recital 45" and out.paragraph is None


class TestVerifyCitations:
    def test_one_result_per_citation_in_order(self):
        citations = [
            _cite("I fornitori garantiscono che i sistemi di IA"),
            "loose text",
            _cite("frase inventata dal modello senza alcun riscontro"),
        ]
        out = verify_citations(citations, _corpus())
        assert [r.verified for r in out] == [True, False, False]

    def test_empty(self):
        assert verify_citations([], _corpus()) == []
        assert verify_citations(None, _corpus()) == []

    def test_fields_tuple_matches_the_result(self):
        assert set(CITATION_FIELDS) == set(VerificationResult().as_fields())
        assert set(CITATION_FIELDS) == {
            "verified",
            "match",
            "level",
            "chunk_id",
            "celex",
            "article",
            "paragraph",
            "lang",
            "consolidated_as_of",
            "url",
            "official_quote",
        }


# ─── Real EUR-Lex passages (golden set v2) ───────────────────────────


def _golden_quotes():
    from tests.validation.golden_v2 import GOLDEN_V2_PATH

    records = [
        json.loads(line)
        for line in GOLDEN_V2_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [r for r in records if len(r["expected"]["quote"].strip()) >= 30]


class TestGoldenSetPassages:
    """The 101 verified golden records quote the official texts (IT and EN):
    a model copy with ASCII typography is still verified, and the span the
    verifier returns is the official wording."""

    def test_typographic_variants_of_real_passages_are_verified(self):
        records = _golden_quotes()
        assert len(records) >= 80
        for rec in records:
            exp = rec["expected"]
            official = exp["quote"]
            # The chunk: the passage inside its article, lines broken as in EUR-Lex.
            text = f"Articolo {exp['article']}\nTitolo\n" + official.replace(". ", ".\n", 1)
            chunk = {
                "id": rec["id"],
                "framework": rec["framework"],
                "article": f"Art. {exp['article']}",
                "celex": exp.get("quote_celex") or exp["celex"],
                "lang": rec["lang"].upper(),
                "text": text,
            }
            model_quote = (
                official.replace(RSQUO, "'")
                .replace("\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}", '"')
                .replace("\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}", '"')
                .replace("\N{EM DASH}", "-")
            )
            citation = {
                "framework": rec["framework"],
                "reference": f"Art. {exp['article']}",
                "quote_snippet": model_quote,
            }
            out = verify_citation(citation, [chunk])
            assert out.verified, rec["id"]
            assert out.match == "exact" and out.level == "article", rec["id"]
            assert out.official_quote in text, rec["id"]
            assert normalize(out.official_quote) == normalize(model_quote), rec["id"]

    def test_real_passages_shortened_with_an_omission(self):
        for rec in _golden_quotes():
            words = rec["expected"]["quote"].split()
            if len(words) < 16:
                continue
            head, tail = " ".join(words[:6]), " ".join(words[-6:])
            chunk = {"framework": rec["framework"], "text": rec["expected"]["quote"]}
            out = verify_citation(
                {"framework": rec["framework"], "quote_snippet": f"{head} [...] {tail}"}, [chunk]
            )
            assert out.verified and out.official_quote.count("[...]") == 1, rec["id"]


# ─── annotate_citations ──────────────────────────────────────────────


class TestAnnotateCitations:
    def test_fields_written_on_copies_with_counters(self):
        verified = _cite("I fornitori garantiscono che i sistemi di IA")
        invented = _cite("una frase che non compare in nessun testo ufficiale")
        result = {"answer": "x", "citations": [verified, invented, "loose text"]}
        before = [dict(verified), dict(invented)]

        out = annotate_citations(result, _corpus())

        assert out is result
        assert [verified, invented] == before  # the model's dicts are untouched
        assert out["citations"][0] is not verified
        assert set(CITATION_FIELDS) <= set(out["citations"][0])
        assert out["citations"][0]["verified"] is True
        assert out["citations"][0]["quote_snippet"] == verified["quote_snippet"]
        assert out["citations"][1]["verified"] is False
        assert all(out["citations"][1][f] is None for f in CITATION_FIELDS if f != "verified")
        assert out["citations"][2] == "loose text"
        assert out["verified_citations"] == 1
        assert out["citations_total"] == 3

    def test_model_supplied_provenance_is_overwritten(self):
        # The LLM may emit its own "verified"/"url"/"celex"/"official_quote":
        # only the verifier's verdict, built server-side, reaches the client.
        forged = {
            **_cite("una frase che non compare in nessun testo ufficiale"),
            "verified": True,
            "match": "exact",
            "url": "https://example.com/fake",
            "celex": "32099R9999",
            "official_quote": "testo inventato",
        }
        out = annotate_citations({"citations": [forged]}, _corpus())
        cit = out["citations"][0]
        assert cit["verified"] is False
        assert cit["url"] is None and cit["celex"] is None and cit["official_quote"] is None
        assert out["verified_citations"] == 0

    def test_answer_without_citations(self):
        out = annotate_citations({"answer": "x"}, _corpus())
        assert "citations" not in out
        assert (out["verified_citations"], out["citations_total"]) == (0, 0)

    def test_no_evidence(self):
        out = annotate_citations({"citations": [_cite("I fornitori garantiscono che")]}, None)
        assert out["citations"][0]["verified"] is False
        assert (out["verified_citations"], out["citations_total"]) == (0, 1)


# ─── Policy ──────────────────────────────────────────────────────────


def _unverified_answer(**extra):
    answer = {
        "answer": "Risposta del modello.",
        "citations": [{**_cite("frase inventata"), "verified": False}],
        "verified_citations": 0,
        "citations_total": 1,
        "confidence_score": 0.9,
        "requires_expert_review": False,
        "related_frameworks": ["GDPR"],
        "caveats": ["Nota del modello."],
    }
    answer.update(extra)
    return answer


class TestFlagPolicy:
    def test_flags_caps_and_adds_the_italian_caveat(self):
        out = apply_unverified_policy(_unverified_answer(), mode="flag")
        assert out["requires_expert_review"] is True
        assert out["confidence_score"] == 0.6
        assert out["caveats"] == ["Nota del modello.", UNVERIFIED_CAVEAT_IT]
        assert out["answer"] == "Risposta del modello."
        assert "abstention_reason" not in out
        assert UNVERIFIED_CAVEAT_IT == (
            "Nessuno dei passaggi citati è stato ritrovato testualmente nei testi del corpus: "
            "verifica le fonti prima di usarla."
        )

    def test_english_request_gets_the_english_twin(self):
        out = apply_unverified_policy(_unverified_answer(), mode="flag", language="en")
        assert out["caveats"] == ["Nota del modello.", UNVERIFIED_CAVEAT_EN]

    def test_idempotent_and_language_switch(self):
        out = apply_unverified_policy(_unverified_answer(), mode="flag", language="it")
        out = apply_unverified_policy(out, mode="flag", language="it")
        assert out["caveats"].count(UNVERIFIED_CAVEAT_IT) == 1
        out = apply_unverified_policy(out, mode="flag", language="en")
        assert out["caveats"] == ["Nota del modello.", UNVERIFIED_CAVEAT_EN]

    def test_lower_confidence_is_kept_and_none_is_not_invented(self):
        assert (
            apply_unverified_policy(_unverified_answer(confidence_score=0.4))["confidence_score"]
            == 0.4
        )
        no_score = _unverified_answer()
        del no_score["confidence_score"]
        assert "confidence_score" not in apply_unverified_policy(no_score)
        assert (
            apply_unverified_policy(_unverified_answer(confidence_score="alta"))["confidence_score"]
            == 0.6
        )

    def test_caveats_that_are_not_a_list(self):
        assert apply_unverified_policy(_unverified_answer(caveats="Una nota."))["caveats"] == [
            "Una nota.",
            UNVERIFIED_CAVEAT_IT,
        ]
        assert apply_unverified_policy(_unverified_answer(caveats=None))["caveats"] == [
            UNVERIFIED_CAVEAT_IT
        ]

    def test_one_verified_citation_is_enough(self):
        answer = _unverified_answer(
            citations=[{"verified": True}, {"verified": False}],
            verified_citations=1,
            citations_total=2,
        )
        out = apply_unverified_policy(json.loads(json.dumps(answer)), mode="strict")
        assert out == answer

    def test_no_citations_no_flag(self):
        answer = {"answer": "Nessuna citazione.", "citations": [], "confidence_score": 0.8}
        out = apply_unverified_policy(dict(answer))
        assert out == {**answer, "verified_citations": 0, "citations_total": 0}

    def test_abstention_is_left_alone(self):
        answer = _unverified_answer(abstention_reason="snc_low_trust")
        out = apply_unverified_policy(dict(answer), mode="strict")
        assert out == answer

    def test_errors_are_left_alone(self):
        error = {"error": "LLM timed out", "error_code": "llm_timeout", "citations": [{}]}
        assert apply_unverified_policy(dict(error)) == error
        assert apply_unverified_policy("not a dict") == "not a dict"

    def test_answer_without_counters_is_counted_from_its_flags(self):
        # e.g. an answer cached before the verifier existed: nothing verified it.
        legacy = {"answer": "x", "citations": [{"framework": "GDPR"}], "confidence_score": 0.9}
        out = apply_unverified_policy(legacy)
        assert (out["verified_citations"], out["citations_total"]) == (0, 1)
        assert out["requires_expert_review"] is True


class TestStrictPolicy:
    def test_becomes_an_abstention(self):
        out = apply_unverified_policy(_unverified_answer(), mode="strict")
        assert out["abstention_reason"] == UNVERIFIED_ABSTENTION_REASON == "unverified_citations"
        assert out["answer"] == UNVERIFIED_ABSTENTION_IT
        assert out["citations"] == [] and out["caveats"] == []
        assert out["requires_expert_review"] is True
        assert out["confidence_score"] == 0.6
        # The counters keep what was rejected; related frameworks stay as pointers.
        assert (out["verified_citations"], out["citations_total"]) == (0, 1)
        assert out["related_frameworks"] == ["GDPR"]

    def test_english_and_idempotent(self):
        out = apply_unverified_policy(_unverified_answer(), mode="strict", language="EN")
        assert out["answer"] == UNVERIFIED_ABSTENTION_EN
        again = apply_unverified_policy(json.loads(json.dumps(out)), mode="strict", language="en")
        assert again == out
        italian = apply_unverified_policy(json.loads(json.dumps(out)), mode="strict", language="it")
        assert italian["answer"] == UNVERIFIED_ABSTENTION_IT

    def test_flagged_answer_cached_under_flag_becomes_an_abstention(self):
        flagged = apply_unverified_policy(_unverified_answer(), mode="flag")
        out = apply_unverified_policy(json.loads(json.dumps(flagged)), mode="strict")
        assert out["abstention_reason"] == "unverified_citations"
        assert out["caveats"] == []


class TestPolicyHelpers:
    def test_unverified_policy_applies(self):
        assert unverified_policy_applies(_unverified_answer()) is True
        assert unverified_policy_applies(_unverified_answer(verified_citations=1)) is False
        assert unverified_policy_applies(_unverified_answer(citations_total=0)) is False
        assert unverified_policy_applies(_unverified_answer(abstention_reason="x")) is False
        assert unverified_policy_applies(_unverified_answer(error="boom")) is False
        assert unverified_policy_applies(None) is False

    def test_counters(self):
        assert count_verified([{"verified": True}, {"verified": False}, "x"]) == (1, 3)
        assert count_verified(None) == (0, 0)
        assert citation_counters({"verified_citations": 2, "citations_total": 5}) == (2, 5)
        # Booleans are not counters: fall back to the flags.
        assert citation_counters(
            {"verified_citations": True, "citations_total": True, "citations": [{"verified": True}]}
        ) == (1, 1)

    @pytest.mark.parametrize(
        "settings, mode",
        [
            (SimpleNamespace(citation_verification="strict"), "strict"),
            (SimpleNamespace(citation_verification="flag"), "flag"),
            (SimpleNamespace(citation_verification="lenient"), "flag"),
            (SimpleNamespace(), "flag"),
            (MagicMock(), "flag"),
        ],
    )
    def test_policy_mode(self, settings, mode):
        assert policy_mode(settings) == mode
