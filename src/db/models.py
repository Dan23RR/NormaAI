"""SQLAlchemy ORM models - the single source of truth for the database schema.

Every table the application touches is declared here. Alembic turns this
metadata into the live schema (``alembic upgrade head``) and CI runs
``alembic check`` against a freshly migrated database, so any drift between
these models and the migrations fails the build. Do not hand-edit the schema
elsewhere (``scripts/init_db.sql`` only creates extensions).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Key of ``system_state`` under which ``python -m src.pipeline --action
# check-freshness`` stores its outcome (read by GET /api/v1/stats).
CORPUS_FRESHNESS_KEY = "corpus_freshness"


def _json_doc() -> Any:
    """JSONB on PostgreSQL (what the migrations create and ``alembic check``
    compares), JSON on SQLite, where the test-suite creates these tables."""
    return JSONB().with_variant(JSON(), "sqlite")


def _text_array() -> Any:
    """TEXT[] on PostgreSQL, a JSON list on SQLite (see ``_json_doc``)."""
    return ARRAY(Text).with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="starter")
    max_clients: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    clients: Mapped[list["Client"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(50), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Flipped by POST /auth/verify-email (or at registration when the invite
    # email matches). Gates the intelligence endpoints when
    # settings.require_email_verification is on.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The digest email "N documenti da rivedere" of the document surveillance.
    # Turned off from PATCH /documents/preferences or from the link in the email.
    notify_document_changes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="assessed_by_user")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class Invite(Base):
    """Registration invite (``settings.registration_mode == "invite"``).

    The plaintext code is shown ONCE (API response / CLI output); only its
    SHA-256 is stored, so a database leak does not yield redeemable codes.

    ``org_id`` NULL = the invitee creates a NEW organization and becomes its
    admin; set = the invitee joins that organization with ``role``.

    ``used_by`` is a plain UUID, deliberately without a FK to ``users``: the
    redemption UPDATE is flushed BEFORE the user row exists, because it has to
    run before the RLS org context is switched to the new/joined organization
    (an org-less invite is invisible to a tenant-scoped session).
    """

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    revenue_eur: Mapped[int | None] = mapped_column(BigInteger)
    jurisdictions: Mapped[list[str]] = mapped_column(_text_array(), default=list)
    applicable_frameworks: Mapped[list[str]] = mapped_column(_text_array(), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="clients")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="client")


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The UNIQUE constraint already backs celex with an index; a second,
    # non-constraint index (the old ``index=True``) was pure duplication.
    celex: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    doc_type: Mapped[str | None] = mapped_column(String(50))
    date_document: Mapped[date | None] = mapped_column(Date)
    date_in_force: Mapped[date | None] = mapped_column(Date)
    is_in_force: Mapped[bool] = mapped_column(Boolean, default=True)
    full_text_url: Mapped[str | None] = mapped_column(Text)
    raw_html: Mapped[str | None] = mapped_column(Text)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_amended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Multi-source fields
    source: Mapped[str] = mapped_column(String(20), default="eurlex")  # "eurlex" or "normattiva"
    urn: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    current_text_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    versions: Mapped[dict | None] = mapped_column(
        _json_doc(), nullable=True
    )  # [{date, status, url}, ...]

    # Relationships
    amendments: Mapped[list["Amendment"]] = relationship(back_populates="original_regulation")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="regulation")


class Amendment(Base):
    __tablename__ = "amendments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_regulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulations.id")
    )
    amending_celex: Mapped[str] = mapped_column(String(50), nullable=False)
    amending_title: Mapped[str | None] = mapped_column(Text)
    amendment_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    original_regulation: Mapped[Optional["Regulation"]] = relationship(back_populates="amendments")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE")
    )
    regulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulations.id")
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actions_required: Mapped[list[str] | None] = mapped_column(_text_array())
    deadline: Mapped[date | None] = mapped_column(Date)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set on the alerts the document surveillance writes: the check to open.
    # Such an alert belongs to the organisation of the check and may have no
    # client (the row-level-security policies of migration 009 let it through).
    document_check_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_checks.id", ondelete="CASCADE"), index=True
    )

    __table_args__ = (Index("idx_alerts_client", "client_id", "created_at"),)

    # Relationships
    client: Mapped[Optional["Client"]] = relationship(back_populates="alerts")
    regulation: Mapped[Optional["Regulation"]] = relationship(back_populates="alerts")


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="in_progress")
    gaps: Mapped[Any] = mapped_column(_json_doc(), default=dict)
    recommendations: Mapped[Any] = mapped_column(_json_doc(), default=dict)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    __table_args__ = (Index("idx_assessments_client", "client_id", "framework"),)

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="assessments")
    assessed_by_user: Mapped[Optional["User"]] = relationship(back_populates="assessments")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    messages: Mapped[Any] = mapped_column(_json_doc(), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    client: Mapped[Optional["Client"]] = relationship(back_populates="conversations")
    user: Mapped["User"] = relationship(back_populates="conversations")


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    regulations_processed: Mapped[int] = mapped_column(Integer, default=0)
    amendments_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParentDocument(Base):
    """Full regulatory articles for the Parent Document Retrieval pattern.

    Small sub-chunks live in Qdrant for vector search and resolve back to
    their parent article here for LLM context. Read and written through raw
    SQL in ``src/nlp/chunking/parent_retriever.py`` (the upsert relies on the
    ``(celex, article_number)`` unique constraint and on the server-side id
    default); the model exists so the ORM metadata describes every table the
    application relies on. Shared regulatory text, not tenant-scoped.
    """

    __tablename__ = "parent_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    celex: Mapped[str] = mapped_column(String(20), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    article_number: Mapped[str | None] = mapped_column(String(50))  # e.g. "Art. 29"
    section_title: Mapped[str | None] = mapped_column(String(500))
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 for dedup
    chunk_ids: Mapped[list[str] | None] = mapped_column(_text_array())  # Qdrant point ids
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_parent_docs_celex", "celex"),
        Index("idx_parent_docs_framework", "framework"),
        Index("idx_parent_docs_article", "celex", "article_number"),
        UniqueConstraint("celex", "article_number", name="uq_parent_docs_celex_article"),
    )


class CitationVerification(Base):
    """Tracks verified citations for CoVe pipeline."""

    __tablename__ = "citation_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(300))  # URN, CELEX, or article ref
    reference_type: Mapped[str] = mapped_column(String(20))  # "urn", "celex", "article"
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(20))  # "normattiva" or "eurlex"
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Lead(Base):
    """Leads captured from the public Codex download form.

    Source: 'codex_download', 'demo_request', or 'newsletter'.
    """

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    org_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(50), default="codex_download")
    # Anti-spam / observability
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    referer: Mapped[str | None] = mapped_column(String(500))
    # Legacy lifecycle (inbound CRM-light)
    status: Mapped[str] = mapped_column(
        String(50), default="new"
    )  # new, contacted, qualified, converted, lost
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Codex download + email tracking (G6.17)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_leads_email_created", "email", "created_at"),)


class DocumentCheck(Base):
    """One check of a document's legal references (src/document_check).

    The document is read in memory and never stored. What is kept: its name,
    its SHA-256, the dates and ``findings``, the outcome for every reference
    (the reference, at most 160 characters of the text around it, the quotes).
    ``status`` and ``counts`` describe the findings as they stand after the
    last re-check; ``needs_review`` is set when a provision the document cites
    changed since the check.

    Tenant-scoped: row-level security on ``org_id``, like ``clients``.
    """

    __tablename__ = "document_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Deleting a client deletes the checks of its documents with it.
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="IT")
    # Watched checks are re-checked by the scheduled surveillance.
    watch: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="a_posto")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    counts: Mapped[Any] = mapped_column(_json_doc(), default=dict, nullable=False)
    findings: Mapped[Any] = mapped_column(_json_doc(), default=list, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    rechecked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the digest email about the present changes was sent. Cleared when a
    # new change is found, so every change is announced once.
    review_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_document_checks_org_checked", "org_id", "checked_at"),
        Index("ix_document_checks_client_id", "client_id"),
    )


class DocumentDependency(Base):
    """A provision a checked document relies on, as it was on the day of the check.

    ``version``, ``fingerprint`` and ``official_text`` are the term of
    comparison of every later re-check (one entry of the lock file of
    ``src.document_check.check.build_lock``). ``state`` is ``current``,
    ``changed``, ``removed`` or ``unavailable``; ``change`` holds what the last
    re-check found when the provision is no longer the same.

    Tenant-scoped: row-level security on ``org_id``, like ``clients``. The
    official text is public; ``cited_as`` comes from the document.
    """

    __tablename__ = "document_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_checks.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="eurlex")
    act: Mapped[str] = mapped_column(String(300), nullable=False)  # CELEX, or URN:NIR
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    article: Mapped[str] = mapped_column(String(100), nullable=False)  # "Art. 33"
    key: Mapped[str] = mapped_column(String(100), nullable=False)  # "art:33"
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="IT")
    version: Mapped[str] = mapped_column(String(300), nullable=False)
    as_of: Mapped[str | None] = mapped_column(String(32))  # ISO date of the version
    fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    official_text: Mapped[str] = mapped_column(Text, nullable=False)
    cited_as: Mapped[Any] = mapped_column(_json_doc(), default=list, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="current")
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change: Mapped[Any | None] = mapped_column(_json_doc())

    __table_args__ = (
        Index("ix_document_dependencies_provision", "source", "act", "key"),
        Index("ix_document_dependencies_check_id", "check_id"),
        Index("ix_document_dependencies_org_id", "org_id"),
    )


class SystemState(Base):
    """Small key-value store for state that belongs to no tenant.

    Written by the scheduled jobs (``CORPUS_FRESHNESS_KEY``: the outcome of the
    nightly corpus freshness check). No row-level security: nothing here comes
    from a tenant.
    """

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(_json_doc(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
