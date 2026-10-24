"""SSE event protocol with Pydantic models and serialization.

This module defines the foundation for real-time streaming responses,
providing type-safe event models, serialization, and SSE formatting.

Event types:
- token: Incremental token from the LLM
- citation: Regulatory document reference with verification status
- thinking: CoVe (Chain of Verification) phase updates
- verification_start: Start of claim verification
- verification_result: Result of claim verification
- phase_change: Workflow phase transitions
- error: Streaming error
- done: Stream completion with metadata
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from enum import Enum
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─── Event Type Enum ────────────────────────────────────────────


class EventType(str, Enum):
    """Supported SSE event types."""

    TOKEN = "token"
    CITATION = "citation"
    THINKING = "thinking"
    VERIFICATION_START = "verification_start"
    VERIFICATION_RESULT = "verification_result"
    PHASE_CHANGE = "phase_change"
    ERROR = "error"
    DONE = "done"


# ─── Event Models ───────────────────────────────────────────────


class TokenEvent(BaseModel):
    """Incremental token from LLM response."""

    type: str = Field(default=EventType.TOKEN, frozen=True)
    content: str = Field(..., description="Token text content")
    index: int = Field(..., description="Token position in response")


# How and where a verified quote matched the official text (citation verifier).
CitationMatch = Literal["exact", "fuzzy"]
CitationLevel = Literal["article", "framework", "any"]


class CitationEvent(BaseModel):
    """Regulatory document reference with metadata and verification status.

    The verification fields come from the deterministic citation verifier
    (src.agents.citation_verifier): ``verified`` is True only when the quote was
    found word for word in a retrieved official text, and then ``celex``,
    ``article``, ``paragraph``, ``url``, ``chunk_id``, ``lang`` and ``quote``
    describe that text. Fields that are None are omitted from the wire format.
    """

    type: str = Field(default=EventType.CITATION, frozen=True)
    framework: str | None = Field(default=None, description="Framework key cited (e.g. AI_ACT)")
    celex: str = Field(default="", description="CELEX identifier (EUR-Lex); empty if unknown")
    urn: str | None = Field(default=None, description="URN identifier if available")
    article: str = Field(
        ...,
        description="Article of the verified passage (e.g. 'Art. 50'); else the model's reference",
    )
    paragraph: str | None = Field(
        default=None, description="Paragraph of the verified passage, when known"
    )
    title: str = Field(..., description="Document title")
    url: str | None = Field(default=None, description="Full URL to document, when resolvable")
    quote: str | None = Field(
        default=None,
        description="Official wording of the passage when verified, else the model's quote",
    )
    # Honest provenance: True/False only when a verification step actually ran
    # on this citation; omitted (None) when none did - never a default False.
    verified: bool | None = Field(
        default=None,
        description="True when the quote was found word for word in a retrieved official text",
    )
    match: CitationMatch | None = Field(
        default=None, description="How the quote matched the official text, when verified"
    )
    level: CitationLevel | None = Field(
        default=None,
        description=(
            "Where it matched: the cited article, another article of the cited framework, "
            "or another act"
        ),
    )
    chunk_id: str | None = Field(default=None, description="Id of the matching corpus chunk")
    lang: str | None = Field(default=None, description="Language of the matching text (IT, EN)")
    consolidated_as_of: str | None = Field(
        default=None, description="Date of the consolidated text the passage was found in"
    )
    grounded: bool | None = Field(
        default=None,
        description="Whether the citation is backed by the retrieved evidence (grounding guard)",
    )


class ThinkingEvent(BaseModel):
    """CoVe (Chain of Verification) phase update."""

    type: str = Field(default=EventType.THINKING, frozen=True)
    phase: str = Field(
        ..., description="Current CoVe phase (draft/planning/verification/revision/validation)"
    )
    message: str = Field(..., description="Descriptive message about current work")


class VerificationStartEvent(BaseModel):
    """Start of claim verification process."""

    type: str = Field(default=EventType.VERIFICATION_START, frozen=True)
    claim: str = Field(..., description="The claim being verified")
    claim_index: int = Field(..., description="Index of claim in response")
    total_claims: int = Field(..., description="Total number of claims to verify")


class VerificationResultEvent(BaseModel):
    """Result of claim verification."""

    type: str = Field(default=EventType.VERIFICATION_RESULT, frozen=True)
    claim: str = Field(..., description="The claim that was verified")
    claim_index: int = Field(..., description="Index of claim")
    verified: bool = Field(..., description="Whether claim was verified as accurate")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    evidence: str = Field(..., description="Supporting evidence or explanation")


class PhaseChangeEvent(BaseModel):
    """Workflow phase transition (draft → planning → verification → revision → validation)."""

    type: str = Field(default=EventType.PHASE_CHANGE, frozen=True)
    phase: str = Field(..., description="New phase name")
    message: str = Field(..., description="Descriptive message about the transition")


class ErrorEvent(BaseModel):
    """Streaming error during processing.

    ``recoverable`` is honest about the STREAM: True only when processing
    continues after the error (e.g. one CoVe claim timed out, the rest goes on);
    False when the stream ends here. ``error_code`` (see src.api.errors) lets
    clients tell a transient upstream condition from a permanent failure.
    """

    type: str = Field(default=EventType.ERROR, frozen=True)
    message: str = Field(..., description="Error message")
    recoverable: bool = Field(..., description="Whether processing can recover from this error")
    error_code: str | None = Field(default=None, description="Machine-readable error class")


class DoneEvent(BaseModel):
    """Stream completion marker with final metadata.

    ``abstention_reason`` and ``corpus_as_of`` are always on the wire (null when
    absent, see NULLABLE_FIELDS); the citation counters are present for Q&A.
    """

    # Serialized even when None (format_sse), so the client reads an explicit null.
    NULLABLE_FIELDS: ClassVar[frozenset[str]] = frozenset({"abstention_reason", "corpus_as_of"})

    type: str = Field(default=EventType.DONE, frozen=True)
    total_tokens: int = Field(..., description="Total tokens generated")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall confidence 0.0-1.0")
    requires_review: bool = Field(..., description="Whether response requires expert review")
    cove_applied: bool = Field(..., description="Whether CoVe verification was applied")
    # The corrected text after CoVe revision. MUST be surfaced to the client -
    # the whole point of verification is that the user reads the revised answer,
    # not the original draft (BUG-002). None when CoVe did not revise.
    revised_text: str | None = Field(
        default=None, description="CoVe-revised answer text; replaces the draft when present"
    )
    verified_citations: int | None = Field(
        default=None, ge=0, description="Citations whose quote was found word for word (Q&A)"
    )
    citations_total: int | None = Field(
        default=None, ge=0, description="Citations the answer proposed (Q&A)"
    )
    caveats: list[str] = Field(default_factory=list, description="Caveats of the answer")
    related_frameworks: list[str] = Field(
        default_factory=list, description="Other frameworks worth checking"
    )
    abstention_reason: str | None = Field(
        default=None,
        description="Why the system abstained (e.g. unverified_citations); null when it answered",
    )
    corpus_as_of: str | None = Field(
        default=None, description="Date of the regulatory corpus (ISO); null when not configured"
    )


# ─── Union Type for All Events ──────────────────────────────────

SSEEvent = (
    TokenEvent
    | CitationEvent
    | ThinkingEvent
    | VerificationStartEvent
    | VerificationResultEvent
    | PhaseChangeEvent
    | ErrorEvent
    | DoneEvent
)


# ─── SSE Serialization ──────────────────────────────────────────


def format_sse(event: SSEEvent) -> str:
    """Format a single event as proper Server-Sent Events format.

    SSE format: `data: {json}\n\n`

    Optional fields left unset (None) are omitted rather than sent as null, so
    an absent ``verified``/``url`` is honestly absent instead of a fake value -
    except the fields an event lists in ``NULLABLE_FIELDS``, which are always
    present (``null`` when unknown).

    Args:
        event: The SSE event to format

    Returns:
        Properly formatted SSE string with double newline terminator
    """
    keep_null: frozenset[str] = getattr(type(event), "NULLABLE_FIELDS", frozenset())
    exclude = {name for name, value in event if value is None and name not in keep_null}
    json_str = event.model_dump_json(exclude=exclude)
    return f"data: {json_str}\n\n"


# ─── Streaming Generator ────────────────────────────────────────


async def sse_generator(events: AsyncIterator[SSEEvent]) -> AsyncIterator[str]:
    """Wrap SSE events with formatting and keepalive comments.

    Yields formatted SSE strings and includes periodic keepalive comments
    (":keepalive" every 15 seconds) to maintain connection health and
    detect client disconnections.

    Args:
        events: Async iterator of SSE events

    Yields:
        Formatted SSE strings ready for HTTP streaming response

    Example:
        ```python
        async def endpoint_stream():
            events = generate_events_async()  # your event producer
            async for chunk in sse_generator(events):
                yield chunk
        ```
    """
    import asyncio

    last_keepalive = datetime.now()
    keepalive_interval = 15.0  # seconds

    try:
        async for event in events:
            # Send the formatted event
            yield format_sse(event)

            # Check if keepalive is needed
            now = datetime.now()
            elapsed = (now - last_keepalive).total_seconds()

            if elapsed >= keepalive_interval:
                # Send keepalive comment to maintain connection
                yield ": keepalive\n\n"
                last_keepalive = now

                # Yield control briefly to avoid blocking on slow consumers
                await asyncio.sleep(0)

    except asyncio.CancelledError:
        logger.info("sse_stream_cancelled", extra={"reason": "client disconnected"})
        # Clean disconnection - no error event needed
        raise

    except Exception as e:
        logger.error(
            "sse_stream_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        # Send error event before closing
        error_event = ErrorEvent(
            message=f"Streaming error: {str(e)}",
            recoverable=False,
        )
        yield format_sse(error_event)
