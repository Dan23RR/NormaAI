"""
Test case schemas — structured format for all validation test cases.

Each test case describes:
- Source (sanction, synthetic, greenwashing benchmark)
- Input document/query to test
- Expected findings (ground truth)
- Metadata for filtering and reporting
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Framework(str, Enum):
    GDPR = "GDPR"
    DORA = "DORA"
    NIS2 = "NIS2"
    CSRD = "CSRD"
    AI_ACT = "AI_ACT"
    EU_TAXONOMY = "EU_TAXONOMY"
    CSDDD = "CSDDD"


class ViolationType(str, Enum):
    OMISSION = "omission"  # Clause completely missing
    INSUFFICIENT = "insufficient"  # Clause present but incomplete
    AMBIGUOUS = "ambiguous"  # Clause present but vague/unclear
    CONFLICTING = "conflicting"  # Contradicts another requirement
    OUTDATED = "outdated"  # Based on superseded regulation version
    INCORRECT = "incorrect"  # Factually wrong statement


class Severity(str, Enum):
    CRITICAL = "critical"  # Would result in major fine
    MAJOR = "major"  # Significant compliance gap
    MINOR = "minor"  # Technical non-compliance
    INFORMATIONAL = "informational"  # Best practice suggestion


class TestCaseSource(str, Enum):
    SANCTION = "sanction"
    SYNTHETIC = "synthetic"
    GREENWASHING = "greenwashing"
    EXPERT_VALIDATED = "expert_validated"
    ADVERSARIAL = "adversarial"


class DifficultyLevel(int, Enum):
    OBVIOUS = 1  # Clauses completely missing
    SUBTLE = 2  # Clauses present but incomplete
    ADVERSARIAL = 3  # Looks compliant but isn't
    CROSS_FRAMEWORK = 4  # Compliant for one, violates another
    TEMPORAL = 5  # Compliant under old law, not under current


class SanctionSource(BaseModel):
    """Metadata from a real enforcement action."""

    authority: str = Field(..., description="Regulatory authority (e.g., Garante Privacy)")
    reference: str = Field(..., description="Decision reference number")
    url: str | None = Field(None, description="URL to the decision")
    fine_amount_eur: float | None = Field(None, description="Fine amount in EUR")
    decision_date: str | None = Field(None, description="Date of decision (YYYY-MM-DD)")
    country: str = Field("EU", description="Country of the decision")


class SyntheticSource(BaseModel):
    """Metadata for synthetically generated test documents."""

    generator_model: str = Field(
        ..., description="Model used to generate (e.g., claude-sonnet-4-5)"
    )
    generation_prompt_hash: str | None = Field(None, description="Hash of generation prompt")
    difficulty_level: DifficultyLevel = Field(..., description="Intended difficulty")
    flaw_injection_method: str = Field("targeted_removal", description="How flaws were injected")


class ExpectedFinding(BaseModel):
    """A single expected finding (ground truth) for a test case."""

    framework: Framework
    article: str = Field(..., description="Specific article/clause (e.g., Art. 13(2)(a))")
    violation_type: ViolationType
    severity: Severity
    description: str = Field(..., description="Human-readable description of the violation")
    requirement_text: str | None = Field(
        None, description="The actual requirement text from the regulation"
    )
    remediation_hint: str | None = Field(None, description="How to fix the violation")


class DocumentInput(BaseModel):
    """The document or query to test against NormaAI."""

    document_type: str = Field(
        ..., description="Type of document (privacy_policy, dpa, sustainability_report, etc.)"
    )
    content: str | None = Field(None, description="Inline document content (for small docs)")
    file_path: str | None = Field(None, description="Path to document file (for large docs/PDFs)")
    language: str = Field("it", description="Document language (ISO 639-1)")
    industry: str | None = Field(None, description="Industry sector")
    company_size: str | None = Field(
        None, description="Company size category (PMI, mid-cap, large)"
    )


class CompanyProfile(BaseModel):
    """Company profile for testing (matches NormaAI's company_profile input)."""

    name: str = Field("Test Company S.r.l.")
    sector: str = Field("technology")
    employee_count: int = Field(50)
    revenue_eur: int = Field(5_000_000)
    jurisdictions: list[str] = Field(default_factory=lambda: ["IT", "EU"])
    applicable_frameworks: list[str] = Field(default_factory=lambda: ["GDPR"])
    existing_documents: str | None = Field(None)


class TestCase(BaseModel):
    """
    Complete test case for NormaAI validation.

    This is the atomic unit of testing. Each test case represents one
    document/query with known ground truth findings.
    """

    id: str = Field(..., description="Unique test case ID (e.g., GDPR-SANCTION-2024-IT-042)")
    name: str = Field(..., description="Human-readable test case name")
    description: str | None = Field(None, description="Detailed description of what this tests")

    # Source metadata
    source_type: TestCaseSource
    sanction_source: SanctionSource | None = None
    synthetic_source: SyntheticSource | None = None

    # Test inputs
    task_type: str = Field(
        "gap_analysis", description="NormaAI task type: qa, gap_analysis, monitor"
    )
    query: str = Field(..., description="The query/framework to pass to NormaAI")
    document: DocumentInput
    company_profile: CompanyProfile = Field(default_factory=CompanyProfile)

    # Ground truth
    expected_findings: list[ExpectedFinding] = Field(
        ..., description="Expected violations to be detected"
    )
    expected_not_findings: list[str] = Field(
        default_factory=list,
        description="Articles that should NOT be flagged (for false positive testing)",
    )

    # Metadata
    difficulty: DifficultyLevel = Field(DifficultyLevel.OBVIOUS)
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    validated_by: str | None = Field(None, description="Legal expert who validated this case")
    enabled: bool = Field(True, description="Whether this test case is active")


class TestResult(BaseModel):
    """Result of running a single test case through NormaAI."""

    test_case_id: str
    run_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Raw output from NormaAI
    normaai_output: dict = Field(default_factory=dict)
    execution_time_ms: float = 0.0
    error: str | None = None

    # Extracted findings from NormaAI output
    detected_findings: list[dict] = Field(
        default_factory=list, description="Findings extracted from NormaAI output"
    )

    # Matching results
    true_positives: list[str] = Field(
        default_factory=list, description="Article IDs correctly detected"
    )
    false_negatives: list[str] = Field(default_factory=list, description="Article IDs missed")
    false_positives: list[str] = Field(
        default_factory=list, description="Article IDs incorrectly flagged"
    )

    # Scores
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    confidence_score: float = 0.0


class SuiteResult(BaseModel):
    """Aggregated results for a full test suite run."""

    suite_name: str
    run_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    skipped_cases: int = 0

    # Aggregate metrics
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_f1: float = 0.0
    min_recall: float = 0.0

    # Per-framework breakdown
    framework_metrics: dict[str, dict] = Field(default_factory=dict)

    # Per-difficulty breakdown
    difficulty_metrics: dict[str, dict] = Field(default_factory=dict)

    # Individual results
    results: list[TestResult] = Field(default_factory=list)

    # Pass/fail thresholds
    recall_threshold: float = 0.95
    precision_threshold: float = 0.80
    f1_threshold: float = 0.87

    @property
    def suite_passed(self) -> bool:
        """Suite passes if aggregate metrics meet all thresholds."""
        return (
            self.avg_recall >= self.recall_threshold
            and self.avg_precision >= self.precision_threshold
            and self.avg_f1 >= self.f1_threshold
        )
