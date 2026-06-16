"""Data models for the Chain-of-Verification (CoVe) anti-hallucination pipeline.

Models represent the complete lifecycle of a verification workflow:
- Draft: initial response with extracted claims
- Verification: questions and evidence-based validation
- Revision: updated response with corrections
- Citation checks: validation of regulatory references
"""

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """Factual claim extracted from LLM-generated response."""

    text: str = Field(..., description="The exact claim text")
    citation: str | None = Field(
        default=None, description="Article/law reference (e.g., 'Art. 29 CSRD')"
    )
    article_ref: str | None = Field(
        default=None, description="Article number or section identifier"
    )
    framework: str | None = Field(
        default=None,
        description="Regulatory framework (CSRD, CSDDD, AI_ACT, DORA, NIS2, TAXONOMY, GDPR, ITALIAN_LAW)",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence that this claim is accurately stated (0.0-1.0)",
    )


class VerificationQuestion(BaseModel):
    """Verification question generated for a specific claim."""

    claim_index: int = Field(..., description="Index of the claim this question targets")
    question: str = Field(..., description="The verification question to answer")
    search_query: str = Field(
        ..., description="Search query to find evidence in regulatory database"
    )
    expected_source: str | None = Field(
        default=None, description="Expected source document (e.g., CELEX number, URN)"
    )


class VerificationStep(BaseModel):
    """Result of verifying a single claim."""

    claim_index: int = Field(..., description="Index of the verified claim")
    claim: Claim = Field(..., description="The claim that was verified")
    question: str = Field(..., description="The verification question asked")
    answer: str = Field(..., description="Answer to the verification question from evidence")
    evidence_chunks: list[dict] = Field(
        default_factory=list,
        description="Retrieved evidence chunks supporting or contradicting the claim",
    )
    verified: bool = Field(..., description="Whether the claim was verified as accurate")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in this verification result"
    )
    discrepancy: str | None = Field(
        default=None, description="If verified=False, description of what doesn't match"
    )


class DraftResult(BaseModel):
    """Initial LLM-generated response with extracted claims."""

    text: str = Field(..., description="The original response text")
    claims: list[Claim] = Field(default_factory=list, description="Extracted factual claims")
    raw_json: dict = Field(default_factory=dict, description="Raw JSON from LLM")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Overall confidence in the draft response"
    )


class VerificationPlan(BaseModel):
    """Plan for verifying a set of claims."""

    questions: list[VerificationQuestion] = Field(
        default_factory=list, description="List of verification questions to answer"
    )
    estimated_time_seconds: float = Field(
        default=0.0, description="Estimated time to complete verification (seconds)"
    )


class RevisionResult(BaseModel):
    """Revised response based on verification results."""

    original_text: str = Field(..., description="The original draft text")
    revised_text: str = Field(..., description="The revised text after verification")
    changes_made: list[str] = Field(
        default_factory=list, description="List of changes made during revision"
    )
    claims_corrected: int = Field(default=0, description="Number of claims that were corrected")
    claims_removed: int = Field(
        default=0, description="Number of claims that were removed as unverified"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Overall confidence in the revised response"
    )


class CitationCheck(BaseModel):
    """Result of validating a single citation."""

    urn: str | None = Field(default=None, description="URN identifier (Italian law)")
    celex: str | None = Field(default=None, description="CELEX identifier (EU law)")
    article: str | None = Field(default=None, description="Article reference")
    exists: bool = Field(..., description="Whether the citation was found in the database")
    is_current: bool = Field(..., description="Whether the citation is current/not superseded")
    url: str | None = Field(default=None, description="URL to the verified document")
    error: str | None = Field(default=None, description="Error message if validation failed")
    # Honest provenance of the check, surfaced to the client / audit trail:
    #   verified   = matched a trusted source (seeded corpus or live registry)
    #   unverified = well-formed but not independently confirmable here
    #   invalid    = malformed / fabricated
    #   grounded   = article-level ref, trusted via retrieved evidence not a registry
    validation: str = Field(default="verified", description="verified|unverified|invalid|grounded")


class CoVeResult(BaseModel):
    """Complete result of the Chain-of-Verification pipeline."""

    draft: DraftResult = Field(..., description="Initial draft and extracted claims")
    plan: VerificationPlan = Field(..., description="Verification plan")
    verifications: list[VerificationStep] = Field(
        default_factory=list, description="Results of verifying each claim"
    )
    revision: RevisionResult = Field(..., description="Final revised response")
    citation_checks: list[CitationCheck] = Field(
        default_factory=list, description="Results of citation validation"
    )
    total_time_seconds: float = Field(
        default=0.0, description="Total time spent in CoVe pipeline (seconds)"
    )
    phases_completed: int = Field(default=0, description="Number of phases completed (0-5)")


class CoVeConfig(BaseModel):
    """Configuration for the Chain-of-Verification pipeline."""

    enabled: bool = Field(default=False, description="Whether CoVe verification is enabled")
    max_claims: int = Field(
        default=10, description="Maximum number of claims to verify per response"
    )
    max_verification_chunks: int = Field(
        default=5, description="Maximum number of evidence chunks to retrieve per claim"
    )
    skip_citation_check: bool = Field(
        default=False, description="Skip the citation validation phase"
    )
    parallel_verification: bool = Field(
        default=False, description="Verify multiple claims in parallel (if supported)"
    )
    timeout_per_phase_seconds: float = Field(
        default=30.0, description="Timeout per phase in seconds"
    )
