"""The official texts are read in parallel by the threads of a process, each text once.

Until 18 November 2026 one lock in src/document_check/service.py serialised
every read of an official text in the API process: a check waiting for the
download of the AI Act held up a check that only needed the GDPR, already in
memory. There is now one lock per text (a version of an act in a language,
an article of an Italian act): different texts are read at the same time, the
same text once. The lists of versions keep one lock (the EUR-Lex client asks
SPARQL through one SPARQLWrapper), and Normattiva's client one request at a
time. Offline, with slow stand-ins.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any

import httpx
import pytest

from src.document_check import service
from src.document_check.normattiva import NormattivaClient, NormattivaTextSource
from src.document_check.official import ArticleText, Version
from src.document_check.sources import OfficialSources
from tests.test_document_check_normattiva import RecordedApi

WAIT = 5.0  # seconds a barrier waits before saying the reads were not together


class SlowSource:
    """A stand-in for CELLAR whose texts take a while to read the first time.

    ``together`` makes the first reads of the texts it names wait for each
    other at a barrier: they can pass it only when read at the same time.
    """

    def __init__(self, together: int = 0) -> None:
        self.barrier = threading.Barrier(together, timeout=WAIT) if together else None
        self.read: Counter[tuple[str, str]] = Counter()
        self.inside: Counter[tuple[str, str]] = Counter()
        self.most_inside_one = 0
        self._memo: dict[tuple[str, str], list[ArticleText]] = {}
        self._guard = threading.Lock()

    def versions(self, celex: str) -> list[Version]:
        return [Version(celex, None)]

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        key = (version.celex, lang)
        with self._guard:
            self.inside[key] += 1
            self.most_inside_one = max(self.most_inside_one, self.inside[key])
        try:
            if key not in self._memo:
                if self.barrier is not None:
                    self.barrier.wait()
                else:
                    time.sleep(0.05)
                with self._guard:
                    self.read[key] += 1
                self._memo[key] = [ArticleText("art:1", "Art. 1", f"Articolo 1 di {key}", ())]
            return self._memo[key]
        finally:
            with self._guard:
                self.inside[key] -= 1


def _in_threads(target: Any, args: list[tuple[Any, ...]]) -> list[BaseException]:
    errors: list[BaseException] = []

    def run(*a: Any) -> None:
        try:
            target(*a)
        except BaseException as e:  # noqa: BLE001 - reported by the test
            errors.append(e)

    threads = [threading.Thread(target=run, args=a) for a in args]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def test_texts_of_different_acts_are_read_at_the_same_time():
    inner = SlowSource(together=3)
    locked = service._LockedSource(inner)
    acts = [Version("32016R0679", None), Version("32024R1689", None), Version("32022L2555", None)]
    errors = _in_threads(locked.articles, [(act, "IT") for act in acts])
    assert errors == []  # a barrier broken by a timeout: the reads went one after the other
    assert sum(inner.read.values()) == 3


def test_one_act_in_two_languages_is_two_texts():
    inner = SlowSource(together=2)
    locked = service._LockedSource(inner)
    gdpr = Version("32016R0679", None)
    assert _in_threads(locked.articles, [(gdpr, "IT"), (gdpr, "EN")]) == []


def test_the_same_text_is_read_once():
    inner = SlowSource()
    locked = service._LockedSource(inner)
    gdpr = Version("02016R0679-20160504", "2016-05-04")
    assert _in_threads(locked.articles, [(gdpr, "it")] * 6) == []
    assert inner.read == Counter({("02016R0679-20160504", "it"): 1})
    assert inner.most_inside_one == 1


class SlowItalian:
    """A stand-in for Normattiva whose articles take a while; records what overlaps."""

    def __init__(self, together: int = 0) -> None:
        self.barrier = threading.Barrier(together, timeout=WAIT) if together else None
        self.inside: Counter[tuple[str, str]] = Counter()
        self.most_inside_one = 0
        self._guard = threading.Lock()

    def article(self, act_urn: str, key: str, on: str) -> str:
        with self._guard:
            self.inside[(act_urn, key)] += 1
            self.most_inside_one = max(self.most_inside_one, self.inside[(act_urn, key)])
        try:
            if self.barrier is not None:
                self.barrier.wait()
            else:
                time.sleep(0.02)
            return f"{act_urn} {key} {on}"
        finally:
            with self._guard:
                self.inside[(act_urn, key)] -= 1

    def original(self, act_urn: str, key: str) -> str:
        return self.article(act_urn, key, "")


def test_italian_articles_are_read_at_the_same_time_and_each_one_at_a_time():
    privacy = "urn:nir:stato:decreto.legislativo:2003;196"
    italian = SlowItalian(together=2)
    locked = service._LockedSource(OfficialSources(SlowSource(), italian))  # type: ignore[arg-type]
    args = [(privacy, "art:13", "2026-11-18"), (privacy, "art:2ter", "2026-11-18")]
    assert _in_threads(locked.italian.article, args) == []
    one = SlowItalian()
    locked = service._LockedSource(OfficialSources(SlowSource(), one))  # type: ignore[arg-type]
    days = [(privacy, "art:13", f"2026-11-{day:02d}") for day in range(10, 16)]
    assert _in_threads(locked.italian.article, days) == []
    assert _in_threads(lambda u, k, _: locked.italian.original(u, k), days[:2]) == []
    assert one.most_inside_one == 1


def test_the_lists_of_versions_go_one_at_a_time():
    inside: list[str] = []
    overlaps: list[list[str]] = []

    class Catalogue(SlowSource):
        def versions(self, celex: str) -> list[Version]:
            inside.append(celex)
            if len(inside) > 1:
                overlaps.append(list(inside))
            time.sleep(0.02)
            inside.remove(celex)
            return [Version(celex, None)]

    locked = service._LockedSource(Catalogue())
    assert _in_threads(locked.versions, [(f"3201{i}R0001",) for i in range(5)]) == []
    assert overlaps == []


# ─── Normattiva: one request at a time, a memory threads can share ───


def test_normattiva_is_asked_one_request_at_a_time_by_many_threads():
    inside: list[int] = []
    most = 0
    guard = threading.Lock()

    def answer(request: httpx.Request) -> httpx.Response:
        nonlocal most
        with guard:
            inside.append(1)
            most = max(most, len(inside))
        time.sleep(0.02)
        with guard:
            inside.pop()
        return httpx.Response(500, json={"message": "occupato"})

    client = NormattivaClient(
        delay=0, retries=0, http=httpx.Client(transport=httpx.MockTransport(answer))
    )
    errors = _in_threads(
        client.article, [(f"urn:nir:stato:legge:2025;132~art{n}",) for n in range(6)]
    )
    assert len(errors) == 6  # every answer is a 500
    assert most == 1


@pytest.mark.parametrize("memory", [1, 3])
def test_the_normattiva_cache_in_memory_is_shared_safely(tmp_path, memory, monkeypatch):
    monkeypatch.setattr(NormattivaTextSource, "MEMORY", memory)
    source = NormattivaTextSource(tmp_path, RecordedApi())  # type: ignore[arg-type]
    locked = service._LockedSource(OfficialSources(SlowSource(), source))  # type: ignore[arg-type]
    asks = [
        ("urn:nir:stato:legge:2025;132", "art:13", "2026-11-11"),
        ("urn:nir:stato:decreto.legislativo:2003;196", "art:2ter", "2026-11-11"),
        ("urn:nir:stato:decreto.legislativo:2024;138", "art:24", "2026-11-11"),
        ("urn:nir:stato:legge:1970;300", "art:18", "2026-11-11"),
    ] * 3
    results: list[Any] = []
    errors = _in_threads(lambda *a: results.append(locked.italian.article(*a)), asks)
    assert errors == []
    assert len(results) == len(asks)
    assert {r.key for r in results} == {"art:13", "art:2ter", "art:24", "art:18"}
