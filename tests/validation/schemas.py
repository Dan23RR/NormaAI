"""
Test case schemas - structured format for all validation test cases.

Each test case describes:
- Source (sanction, synthetic, greenwashing benchmark)
- Input document/query to test
- Expected findings (ground truth)
- Metadata for filtering and reporting
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Framework(str, Enum):
    GDPR = "GDPR"
    DORA = "DORA"
    NIS2 = "NIS2"
    CSRD = "CSRD"
    AI_ACT = "AI_ACT"
    EU_TAXONOMY = "EU_TAXONOMY"
    CSDDD = "CSDDD"
    TAXONOMY = "TAXONOMY"  # Regulation (EU) 2020/852, name used by the golden v2 set
    CRA = "CRA"  # Cyber Resilience Act, Regulation (EU) 2024/2847


class ViolationType(str, Enum):
    OMISSION = "omission"  # Clause completely missing
    INSUFFICIENT = "insufficient"  # Clause present but incomplete
    AMBIGUOUS = "ambiguous"  # Clause present but vague/unclear
    CONFLICTING = "conflicting"  # Contradicts another requirement
    OUTDATED = "outdated"  # Based on superseded regulation version
    INCORRECT = "incorrect"  # Factually wrong statement
    REFERENCE = "reference"  # Expected citation of a Q&A golden record, not a violation


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
    expected_answer: dict | None = Field(
        None,
        description=(
            "Answer-level checks for Q&A cases (golden v2): answer_must_contain, "
            "answer_must_not_contain, abstain, quote. Scored by golden_v2.check_answer."
        ),
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
    answer_checks: dict | None = Field(
        None,
        description="Result of golden_v2.check_answer when the case carries expected_answer",
    )


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
    # The moat as a number: mean fraction of emitted citations backed by the
    # retrieved evidence, over cases where it could be scored. None until wired to
    # a run that captures retrieved_chunks per case.
    avg_citation_grounding_rate: float | None = None
    # Share of Q&A cases whose answer passed the golden v2 answer checks
    # (must-contain / must-not-contain / abstain). None when no case carries them.
    answer_check_pass_rate: float | None = None

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


# ─── Golden set v2 (Q&A with verified citations) ─────────────────
#
# One JSON object per line in test_cases/golden_v2.jsonl. Every non-abstain
# record cites an act (CELEX), an article and a passage copied verbatim from the
# official text (see GOLDEN_V2.md and verify_golden_v2.py).

CELEX_PATTERN = r"^[0-9]{5}[A-Z]{1,2}[0-9]{4}(?:-[0-9]{8})?$"  # 32024R1689, 02013L0034-20260318
GOLDEN_ID_PATTERN = (
    r"^[a-z0-9]+(?:-[0-9a-z]+)*-[0-9]{3}$"  # aiact-050-001, csrd-19a-001, refuse-001
)
ISO_DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"


class GoldenLang(str, Enum):
    IT = "it"
    EN = "en"


class GoldenKind(str, Enum):
    FACTUAL = "factual"
    APPLICABILITY = "applicability"
    DATE = "date"
    THRESHOLD = "threshold"
    REFUSE = "refuse"  # outside the corpus: expected abstain
    INJECTION = "injection"  # prompt injection / fake citation: answer from the law or abstain


class GoldenFramework(str, Enum):
    AI_ACT = "AI_ACT"
    CSRD = "CSRD"
    CSDDD = "CSDDD"
    DORA = "DORA"
    NIS2 = "NIS2"
    GDPR = "GDPR"
    TAXONOMY = "TAXONOMY"
    CRA = "CRA"
    NONE = "NONE"  # out-of-corpus question (tax, medical, US law, secrets)


class GoldenVerification(str, Enum):
    FETCHED = "fetched"  # quote copied from the official text fetched from EUR-Lex/CELLAR
    UNVERIFIED = "unverified"  # kept on high confidence only; at most 15% of the set


class GoldenV2Expected(BaseModel):
    """Ground truth of a golden v2 record."""

    celex: str | None = Field(None, pattern=CELEX_PATTERN, description="Act to cite")
    article: str | None = Field(None, description="Article number to cite, e.g. '50', '19a'")
    paragraph: str | None = Field(None, description="Paragraph/point, e.g. '1', '2(a)', '3(c)'")
    quote: str = Field("", description="Passage copied verbatim from the official text")
    answer_must_contain: list[str] = Field(default_factory=list)
    answer_must_not_contain: list[str] = Field(default_factory=list)
    abstain: bool = False
    quote_celex: str | None = Field(
        None,
        pattern=CELEX_PATTERN,
        description=(
            "Act the quote was copied from when it differs from `celex`: a consolidated "
            "text (e.g. 02013L0034-20260318) or the amending act (e.g. 32026R1744)"
        ),
    )
    quote_article: str | None = Field(
        None, description="Article of `quote_celex` holding the quote (e.g. '1' of an amending act)"
    )

    @model_validator(mode="after")
    def _consistent(self) -> "GoldenV2Expected":
        if self.abstain:
            if self.quote.strip():
                raise ValueError("abstain records must not carry a quote")
            if self.answer_must_contain:
                raise ValueError("abstain records must not require answer content")
        else:
            if not self.celex or not self.article:
                raise ValueError("non-abstain records need celex and article")
        return self


class GoldenV2Record(BaseModel):
    """One question of the golden v2 set."""

    id: str = Field(..., pattern=GOLDEN_ID_PATTERN)
    lang: GoldenLang
    framework: GoldenFramework
    question: str = Field(..., min_length=10)
    kind: GoldenKind
    expected: GoldenV2Expected
    source_url: str | None = Field(None, pattern=r"^https://eur-lex\.europa\.eu/")
    verified_on: str = Field(..., pattern=ISO_DATE_PATTERN)
    verification: GoldenVerification
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> "GoldenV2Record":
        if self.kind == GoldenKind.REFUSE and not self.expected.abstain:
            raise ValueError("refuse records must expect abstain")
        if self.expected.abstain and self.kind not in (GoldenKind.REFUSE, GoldenKind.INJECTION):
            raise ValueError("only refuse/injection records may expect abstain")
        if (
            self.verification == GoldenVerification.FETCHED
            and not self.expected.abstain
            and not self.expected.quote.strip()
        ):
            raise ValueError("fetched records need a non-empty quote")
        if self.framework == GoldenFramework.NONE and not self.expected.abstain:
            raise ValueError("framework NONE is reserved for abstain records")
        return self

    @property
    def article_ref(self) -> str | None:
        """'Art. 50(1)', 'Art. 14(2)(a)', 'Art. 3(c)' — the form used by the metrics engine."""
        if not self.expected.article:
            return None
        ref = f"Art. {self.expected.article}"
        para = self.expected.paragraph or ""
        if para:
            if para.startswith("("):
                ref += para
            else:
                number, _, point = para.partition("(")
                ref += f"({number})"
                if point:
                    ref += f"({point}"
        return ref

    def to_test_case(self) -> TestCase:
        """Bridge to the legacy runner: a Q&A TestCase whose expected finding is the citation."""
        exp = self.expected
        findings: list[ExpectedFinding] = []
        if not exp.abstain and self.framework != GoldenFramework.NONE:
            findings.append(
                ExpectedFinding(
                    framework=Framework(self.framework.value),
                    article=self.article_ref or f"Art. {exp.article}",
                    violation_type=ViolationType.REFERENCE,
                    severity=Severity.INFORMATIONAL,
                    description=f"Expected citation: CELEX {exp.celex}, {self.article_ref}",
                    requirement_text=exp.quote or None,
                )
            )
        difficulty = (
            DifficultyLevel.ADVERSARIAL
            if self.kind in (GoldenKind.REFUSE, GoldenKind.INJECTION)
            else DifficultyLevel.OBVIOUS
            if self.kind == GoldenKind.FACTUAL
            else DifficultyLevel.SUBTLE
        )
        profile = CompanyProfile(
            applicable_frameworks=[]
            if self.framework == GoldenFramework.NONE
            else [self.framework.value]
        )
        return TestCase(
            id=self.id,
            name=f"[golden_v2/{self.kind.value}] {self.question[:80]}",
            description=self.notes or None,
            source_type=TestCaseSource.EXPERT_VALIDATED,
            task_type="qa",
            query=self.question,
            document=DocumentInput(document_type="question", language=self.lang.value),
            company_profile=profile,
            expected_findings=findings,
            difficulty=difficulty,
            tags=["golden_v2", self.kind.value, self.lang.value, self.framework.value.lower()],
            validated_by=f"EUR-Lex/CELLAR verbatim check ({self.verification.value}, {self.verified_on})",
            expected_answer={
                "answer_must_contain": list(exp.answer_must_contain),
                "answer_must_not_contain": list(exp.answer_must_not_contain),
                "abstain": exp.abstain,
                "quote": exp.quote,
                "celex": exp.celex,
                "article_ref": self.article_ref,
            },
        )
