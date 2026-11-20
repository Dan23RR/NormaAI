"""The parsed articles that CellarTextSource keeps on disk next to each XHTML.

Parsing the XHTML of a large act takes seconds, and a document check meets
several acts: the articles are kept in ``<celex>.<lang>.articles-v<N>.json``,
where N is ``official.PARSER_VERSION``. A new parser, a new download of the
XHTML or a file that cannot be read makes the source parse again.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from src.document_check import official
from src.document_check.official import ArticleText, CellarTextSource, Version
from tests.test_document_check import FakeClient

VERSION = Version("02024R1689-20260727", "2026-07-27")
XHTML = "02024R1689-20260727.IT.xhtml"


def _parsed_file(tmp_path):
    return tmp_path / f"02024R1689-20260727.IT.articles-v{official.PARSER_VERSION}.json"


def _count_parses():
    """Patch the chunker so that every parse is counted."""
    calls: list[str] = []
    real = official.EURLexHTMLChunker.chunk_html

    def counting(self, html):
        calls.append(self.celex if hasattr(self, "celex") else "?")
        return real(self, html)

    return calls, patch.object(official.EURLexHTMLChunker, "chunk_html", counting)


def test_a_second_source_reads_the_parsed_articles_instead_of_parsing(tmp_path):
    client = FakeClient()
    calls, counted = _count_parses()
    with counted:
        first = CellarTextSource(tmp_path, client).articles(VERSION, "it")
        assert _parsed_file(tmp_path).exists()
        second = CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    assert len(calls) == 1
    assert second == first
    assert all(isinstance(article, ArticleText) for article in second)
    assert second[0].paragraphs == ("1", "2")
    assert client.downloaded == ["02024R1689-20260727"]


def test_the_file_carries_the_parser_version(tmp_path):
    CellarTextSource(tmp_path, FakeClient()).articles(VERSION, "IT")
    data = json.loads(_parsed_file(tmp_path).read_text(encoding="utf-8"))
    assert data["parser"] == official.PARSER_VERSION
    assert data["xhtml_bytes"] == (tmp_path / XHTML).stat().st_size
    assert data["articles"][0]["key"] == "art:4"


def test_a_new_parser_parses_again(tmp_path):
    client = FakeClient()
    CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    calls, counted = _count_parses()
    with counted, patch.object(official, "PARSER_VERSION", official.PARSER_VERSION + 1):
        articles = CellarTextSource(tmp_path, client).articles(VERSION, "IT")
        assert _parsed_file(tmp_path).exists()  # written by the new parser
    assert len(calls) == 1 and articles[0].label == "Art. 4"
    # An old file with the right name but another parser inside is not trusted either.
    path = _parsed_file(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["parser"] = -1
    path.write_text(json.dumps(data), encoding="utf-8")
    calls, counted = _count_parses()
    with counted:
        CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    assert len(calls) == 1


def test_a_new_download_of_the_xhtml_parses_again(tmp_path):
    client = FakeClient()
    CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    xhtml = tmp_path / XHTML
    xhtml.write_text(
        xhtml.read_text(encoding="utf-8").replace("del loro personale", "del personale"),
        encoding="utf-8",
    )
    calls, counted = _count_parses()
    with counted:
        [art4] = CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    assert len(calls) == 1 and "del personale" in art4.text


def test_a_corrupt_file_is_ignored_and_rebuilt(tmp_path):
    client = FakeClient()
    expected = CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    path = _parsed_file(tmp_path)
    for broken in ("{not json", json.dumps({"parser": official.PARSER_VERSION}), "[]", ""):
        path.write_text(broken, encoding="utf-8")
        calls, counted = _count_parses()
        with counted:
            assert CellarTextSource(tmp_path, client).articles(VERSION, "IT") == expected
        assert len(calls) == 1
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["parser"] == official.PARSER_VERSION and data["articles"]
    assert client.downloaded == ["02024R1689-20260727"]
    assert not list(tmp_path.glob("*.tmp"))


def test_a_cache_that_cannot_be_written_still_gives_the_articles(tmp_path):
    client = FakeClient()
    with patch.object(official.os, "replace", side_effect=PermissionError("read-only")):
        [art4] = CellarTextSource(tmp_path, client).articles(VERSION, "IT")
    assert art4.label == "Art. 4"
    assert not _parsed_file(tmp_path).exists()
    assert not list(tmp_path.glob("*.tmp"))
