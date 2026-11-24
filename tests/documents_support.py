"""Shared helpers of the document tests (not a test module).

- ``FakeSource``: a stand-in for the official texts, with the AI Act as adopted,
  as consolidated on 12/07/2024 and on 27/07/2026 (art. 4 rewritten) and the
  GDPR. ``publish`` adds a new consolidated version, which is how a test makes a
  provision change after a check.
- ``FakeItalian``: a stand-in for Normattiva, one wording per Italian outcome
  (verified quote, change already published, ruling in the notes, act not
  found, article read in part); with ``FakeSource`` behind
  ``sources.OfficialSources`` it is the composite source of production.
- ``Database``: the real tables on SQLite in memory, reached through the async
  session interface the application uses (``db_manager.session(org_id=...)``).
  SQLite has no row-level security: what these tests prove is the filtering the
  application does itself, on ``org_id``, in every query.
"""

from __future__ import annotations

import contextlib
import re
import uuid
from dataclasses import replace
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.agents.citation_verifier import parse_article
from src.db.models import (
    Alert,
    Assessment,
    Base,
    Client,
    Conversation,
    DocumentCheck,
    DocumentDependency,
    Organization,
    Regulation,
    SystemState,
    User,
)
from src.document_check.normattiva import (
    IN_FORCE,
    ActNotFoundError,
    ArticleNotFoundError,
    ItalianArticle,
)
from src.document_check.official import ArticleText, TextUnavailableError, Version

# The official texts below are the ones of tests/test_document_check.py.
OLD_ART4 = (
    "Articolo 4\nAlfabetizzazione in materia di IA\nI fornitori e i deployer dei sistemi di IA "
    "adottano misure per garantire nella misura del possibile un livello sufficiente di "
    "alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che "
    "si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto."
)
NEW_ART4 = (
    "Articolo 4\nAlfabetizzazione in materia di IA\n1. I fornitori e i deployer di sistemi di IA "
    "adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del "
    "loro personale.\n2. La Commissione e gli Stati membri sostengono e agevolano gli sforzi dei "
    "fornitori e dei deployer di sistemi di IA, in particolare delle PMI."
)
ART50 = (
    "Articolo 50\nObblighi di trasparenza\n1. I fornitori garantiscono che i sistemi di IA "
    "destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in "
    "modo tale che le persone fisiche interessate siano informate del fatto di stare interagendo "
    "con un sistema di IA.\n2. Testo del paragrafo due.\n3. Testo del paragrafo tre.\n"
    "4. Testo del paragrafo quattro.\n5. Le informazioni di cui ai paragrafi da 1 a 4 sono "
    "fornite alle persone fisiche interessate in maniera chiara e distinguibile al più tardi al "
    "momento della prima interazione o esposizione.\n6. Testo del paragrafo sei.\n"
    "7. Testo del paragrafo sette."
)
ART13 = (
    "Articolo 13\nInformazioni da fornire qualora i dati personali siano raccolti presso "
    "l'interessato\n1. In caso di raccolta presso l'interessato di dati che lo riguardano, il "
    "titolare del trattamento fornisce all'interessato, nel momento in cui i dati personali sono "
    "ottenuti, le seguenti informazioni:"
)
# An invented later wording of art. 13, for the tests that make the GDPR change.
ART13_AMENDED = ART13.replace("le seguenti informazioni:", "almeno le seguenti informazioni:")

AI_ACT = "32024R1689"
GDPR = "32016R0679"

# A document with one reference per outcome the interface shows.
DOCUMENT = (
    "Informativa sull'uso dell'intelligenza artificiale\n"
    "Ai sensi dell'art. 4 dell'AI Act, i deployer «adottano misure per garantire nella misura "
    "del possibile un livello sufficiente di alfabetizzazione in materia di IA del loro "
    "personale».\n"
    "L'assistente del sito rispetta l'art. 50, par. 5, AI Act: «Le informazioni di cui ai "
    "paragrafi da 1 a 3 sono fornite alle persone fisiche interessate in maniera chiara e "
    "distinguibile».\n"
    "Non esiste l'art. 50, par. 9, AI Act.\n"
    "Ai sensi dell'art. 13 del GDPR, il titolare «fornisce all'interessato, nel momento in cui i "
    "dati personali sono ottenuti, le seguenti informazioni».\n"
    "Resta fermo l'art. 13 del d.lgs. 196/2003.\n"
    "Si veda l'art. 22.\n"
)
# A document that only cites provisions in force, word for word.
CLEAN_DOCUMENT = (
    "Nota per il cliente\n"
    "Ai sensi dell'art. 13 del GDPR, il titolare «fornisce all'interessato, nel momento in cui i "
    "dati personali sono ottenuti, le seguenti informazioni».\n"
    "Per l'assistente del sito vale l'art. 50, par. 1, dell'AI Act.\n"
)


def article(label: str, text: str) -> ArticleText:
    key = parse_article(label)
    assert key is not None
    return ArticleText(key, label, text, tuple(re.findall(r"(?m)^(\d{1,3})\.\s", text)))


class FakeSource:
    """Official texts by version, with what was asked of it."""

    def __init__(self) -> None:
        self._versions: dict[str, list[Version]] = {
            AI_ACT: [
                Version(AI_ACT, None),
                Version("02024R1689-20240712", "2024-07-12"),
                Version("02024R1689-20260727", "2026-07-27"),
            ],
            GDPR: [Version(GDPR, None), Version("02016R0679-20160504", "2016-05-04")],
        }
        ai_old = [article("Art. 4", OLD_ART4), article("Art. 50", ART50)]
        ai_new = [article("Art. 4", NEW_ART4), article("Art. 50", ART50)]
        gdpr = [article("Art. 13", ART13)]
        self._articles: dict[str, list[ArticleText]] = {
            AI_ACT: ai_old,
            "02024R1689-20240712": ai_old,
            "02024R1689-20260727": ai_new,
            GDPR: gdpr,
            "02016R0679-20160504": gdpr,
        }
        self.asked_versions: list[str] = []
        self.asked_articles: list[str] = []
        self.unreachable: set[str] = set()  # acts whose list of versions cannot be read

    def publish(self, act: str, as_of: str, articles: list[ArticleText]) -> Version:
        """A new consolidated version of ``act`` with these articles."""
        celex = f"0{act[1:]}-{as_of.replace('-', '')}"
        version = Version(celex, as_of)
        self._versions[act].append(version)
        self._articles[celex] = articles
        return version

    def versions(self, celex: str) -> list[Version]:
        self.asked_versions.append(celex)
        if celex not in self._versions or celex in self.unreachable:
            raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")
        return list(self._versions[celex])

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        self.asked_articles.append(version.celex)
        return self._articles[version.celex]


# ─── Italian law ─────────────────────────────────────────────────────

AI_LAW = "urn:nir:stato:legge:2025;132"
PRIVACY = "urn:nir:stato:decreto.legislativo:2003;196"
WORKERS = "urn:nir:stato:legge:1970;300"
BUDGET = "urn:nir:stato:legge:2024;207"

# Invented wordings: what matters is how each one is read, not the words.
IT_ART13 = (
    "Art. 13\nDisposizioni in materia di professioni intellettuali\n1. L'utilizzo di sistemi di "
    "intelligenza artificiale nelle professioni intellettuali è consentito esclusivamente per "
    "esercitare attività strumentali e di supporto all'attività professionale.\n2. Per assicurare "
    "il rapporto fiduciario il professionista comunica al cliente le informazioni sui sistemi "
    "utilizzati."
)
IT_ART13_AMENDED = IT_ART13.replace("esclusivamente", "prevalentemente")
IT_ART2TER = (
    "Art. 2-ter\nBase giuridica per il trattamento di dati personali\n1. La base giuridica è "
    "costituita da una norma di legge o di regolamento."
)
IT_ART2TER_NEXT = IT_ART2TER.replace("di legge o di regolamento", "di legge")
IT_ART4 = "Art. 4\nImpianti audiovisivi\n1. Gli impianti audiovisivi possono essere impiegati."
IT_ART4_NOTES = (
    "La Corte costituzionale, con sentenza 7 aprile - 19 maggio 2022, n. 125 (in G.U. 1a s.s. "
    "25/05/2022, n. 21), ha dichiarato l'illegittimità costituzionale dell'art. 4."
)
IT_ART1 = "Art. 1\nRisultati differenziali\n1. Testo del comma uno.\n2. Testo del comma due."

# One reference per Italian outcome, and one EU provision in force.
ITALIAN_DOCUMENT = (
    "Nota al cliente\n"
    "Ai sensi dell'art. 13, comma 1, della legge 23 settembre 2025, n. 132, l'intelligenza "
    "artificiale «è consentito esclusivamente per esercitare attività strumentali e di supporto "
    "all'attività professionale».\n"
    "La base giuridica è quella dell'art. 2-ter del Codice privacy.\n"
    "Le telecamere seguono l'art. 4 della legge 300/1970.\n"
    "Si veda anche l'art. 7 della legge 999/2025.\n"
    "Vale l'art. 1, comma 120, della legge 207/2024.\n"
    "Ai sensi dell'art. 13 del GDPR, il titolare «fornisce all'interessato, nel momento in cui i "
    "dati personali sono ottenuti, le seguenti informazioni».\n"
)


class FakeItalian:
    """Normattiva stand-in: wordings of articles by the days they are in force.

    ``article(urn, key, on)`` gives the wording in force on ``on``; an act it
    does not know raises ActNotFoundError, an article it does not know (or no
    longer has) ArticleNotFoundError.
    """

    def __init__(self) -> None:
        self.wordings: dict[tuple[str, str], list[ItalianArticle]] = {}
        self.asked: list[tuple[str, str, str]] = []
        self.add(AI_LAW, "art:13", "Art. 13", IT_ART13, "2025-10-10")
        # A wording whose end is already set, and the one published to follow it.
        self.add(PRIVACY, "art:2ter", "Art. 2-ter", IT_ART2TER, "2018-09-19", "2099-12-31")
        self.add(PRIVACY, "art:2ter", "Art. 2-ter", IT_ART2TER_NEXT, "2100-01-01")
        self.add(WORKERS, "art:4", "Art. 4", IT_ART4, "2015-09-24", notes=IT_ART4_NOTES)
        # Normattiva gives only the first part of a long article.
        self.add(BUDGET, "art:1", "Art. 1", IT_ART1, "2025-01-01", partial=True)

    def add(
        self,
        urn: str,
        key: str,
        label: str,
        text: str,
        start: str,
        end: str | None = None,
        *,
        notes: str = "",
        partial: bool = False,
    ) -> None:
        commi = tuple(re.findall(r"(?m)^(\d{1,3})\.\s", text))
        if partial:
            commi = tuple(str(n) for n in range(1, 101))
        self.wordings.setdefault((urn, key), []).append(
            ItalianArticle(
                urn=urn,
                key=key,
                label=label,
                text=text,
                commi=commi,
                numbered=True,
                state=IN_FORCE,
                asked="",
                start=start,
                end=end,
                act_title=f"Atto {urn}",
                notes=notes,
                partial=partial,
            )
        )

    def replace_text(self, urn: str, key: str, text: str) -> None:
        """The article in force has other words from now on."""
        self.wordings[(urn, key)] = [replace(w, text=text) for w in self.wordings[(urn, key)]]

    def remove(self, urn: str, key: str) -> None:
        """The article is no longer on Normattiva."""
        self.wordings[(urn, key)] = []

    def article(self, act_urn: str, key: str, on: str) -> ItalianArticle:
        self.asked.append((act_urn, key, on))
        if act_urn not in {urn for urn, _ in self.wordings}:
            raise ActNotFoundError("Atto non trovato")
        for wording in self.wordings.get((act_urn, key), []):
            if (wording.start or "") <= on and (wording.end is None or on <= wording.end):
                return replace(wording, asked=on)
        raise ArticleNotFoundError("Nessun articolo trovato")

    def original(self, act_urn: str, key: str) -> ItalianArticle:
        wordings = self.wordings.get((act_urn, key), [])
        if not wordings:
            raise ArticleNotFoundError("Nessun articolo trovato")
        return replace(wordings[0], asked="", original=True)


# ─── Database ────────────────────────────────────────────────────────

TABLES = [
    Base.metadata.tables[model.__tablename__]
    for model in (
        Organization,
        User,
        Client,
        Regulation,
        Alert,
        Assessment,
        Conversation,
        DocumentCheck,
        DocumentDependency,
        SystemState,
    )
]


class AsyncSessionFacade:
    """The part of ``AsyncSession`` the application uses, over a synchronous session."""

    def __init__(self, session: Session) -> None:
        self.sync = session

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        return self.sync.execute(statement, *args, **kwargs)

    async def get(self, entity: Any, ident: Any) -> Any:
        return self.sync.get(entity, ident)

    def add(self, instance: Any) -> None:
        self.sync.add(instance)

    def add_all(self, instances: Any) -> None:
        self.sync.add_all(instances)

    async def delete(self, instance: Any) -> None:
        self.sync.delete(instance)

    async def flush(self) -> None:
        self.sync.flush()

    async def commit(self) -> None:
        self.sync.commit()

    async def rollback(self) -> None:
        self.sync.rollback()

    async def refresh(self, instance: Any) -> None:
        self.sync.refresh(instance)

    async def close(self) -> None:
        self.sync.close()


class Database:
    """The application's tables on SQLite in memory, with a stand-in for ``db_manager``."""

    def __init__(self) -> None:
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def _foreign_keys(connection: Any, _record: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine, tables=TABLES)
        # The org_id every session was opened with, in order (None: no tenant).
        self.session_orgs: list[str | None] = []

    @contextlib.asynccontextmanager
    async def session(self, org_id: str | None = None):
        self.session_orgs.append(org_id)
        with Session(self.engine, expire_on_commit=False) as session:
            yield AsyncSessionFacade(session)

    def sync_session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    # ─── Rows a test starts from ──────────────────────────────

    def add_org(self, name: str = "Studio Rossi") -> uuid.UUID:
        org = Organization(id=uuid.uuid4(), name=name, slug=f"org-{uuid.uuid4().hex[:8]}")
        with self.sync_session() as session:
            session.add(org)
            session.commit()
        return org.id

    def add_user(
        self,
        org_id: uuid.UUID,
        email: str,
        *,
        name: str = "Anna",
        role: str = "member",
        notify: bool = True,
        active: bool = True,
        verified: bool = True,
    ) -> uuid.UUID:
        user = User(
            id=uuid.uuid4(),
            org_id=org_id,
            email=email,
            name=name,
            role=role,
            is_active=active,
            email_verified=verified,
            notify_document_changes=notify,
        )
        with self.sync_session() as session:
            session.add(user)
            session.commit()
        return user.id

    def add_client(self, org_id: uuid.UUID, name: str = "Acme Srl") -> uuid.UUID:
        client = Client(id=uuid.uuid4(), org_id=org_id, name=name)
        with self.sync_session() as session:
            session.add(client)
            session.commit()
        return client.id

    def rows(self, model: Any, **filters: Any) -> list[Any]:
        with self.sync_session() as session:
            query = session.query(model)
            for name, value in filters.items():
                query = query.filter(getattr(model, name) == value)
            return list(query.all())
