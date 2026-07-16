"""
Metrics engine for NormaAI validation.

Calculates precision, recall, F1 at test case, framework, and suite level.
Includes article-level matching with fuzzy logic for partial matches.
"""

import re

from .schemas import (
    SuiteResult,
    TestCase,
    TestResult,
)


def citation_grounding_rate(output: dict, retrieved_chunks: list | None) -> float | None:
    """Fraction of an answer's citations backed by the retrieved evidence.

    Single source of truth is src.agents.nodes.citation_grounding_rate, so this
    validation KPI uses the SAME rules as the runtime grounding guard and the two
    never diverge. Returns None when there is nothing to score (no citations).

    Aggregate over a suite by averaging the non-None values into
    SuiteResult.avg_citation_grounding_rate. NOTE: this needs a run that captures
    retrieved_chunks per case; the online harness must expose them first.
    """
    from src.agents.nodes import citation_grounding_rate as _rate

    return _rate(output, retrieved_chunks)


def normalize_article(article: str) -> str:
    """
    Normalize article references for comparison.

    'Art. 13(2)(a)' → 'art_13_2_a'
    'Article 28(3)(h)' → 'art_28_3_h'
    'ESRS E1-6' → 'esrs_e1_6'
    """
    s = article.lower().strip()
    s = re.sub(r"\barticle\b|\bart\.?\b", "art", s)
    s = re.sub(r"[()§.\-/]", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s


def articles_match(expected: str, detected: str, fuzzy: bool = True) -> bool:
    """
    Check if two article references refer to the same provision.

    With fuzzy=True:
    - 'Art. 13' matches 'Art. 13(2)(a)' (parent matches child)
    - Exact match always works
    """
    norm_exp = normalize_article(expected)
    norm_det = normalize_article(detected)

    # Exact match
    if norm_exp == norm_det:
        return True

    # Fuzzy: parent-child match (Art. 13 matches Art. 13(2)(a))
    if fuzzy:
        if norm_det.startswith(norm_exp) or norm_exp.startswith(norm_det):
            return True

    return False


def extract_findings_from_output(output: dict, task_type: str = "gap_analysis") -> list[dict]:
    """
    Extract structured findings from NormaAI's raw output.

    Handles various output formats:
    - gap_analysis: requirements[] with status fields
    - qa: answer with citations[]
    - monitor: required_actions[] with impact analysis
    """
    findings = []

    if not isinstance(output, dict):
        return findings

    # Handle error responses
    if output.get("error"):
        return findings

    # Gap analysis output format
    if task_type == "gap_analysis":
        requirements = output.get("requirements", [])
        if not requirements:
            requirements = output.get("gaps", [])
        if not requirements:
            requirements = output.get("findings", [])

        for req in requirements:
            if isinstance(req, dict):
                status = str(req.get("status", "")).upper()
                if status in (
                    "NON_COMPLIANT",
                    "PARTIALLY_COMPLIANT",
                    "MISSING",
                    "GAP",
                    "NON-COMPLIANT",
                ):
                    findings.append(
                        {
                            "article": req.get(
                                "article", req.get("requirement_id", req.get("id", "unknown"))
                            ),
                            "status": status,
                            "description": req.get("description", req.get("finding", "")),
                            "severity": req.get("severity", req.get("priority", "major")),
                        }
                    )

    # QA output format
    elif task_type == "qa":
        citations = output.get("citations", [])
        for citation in citations:
            if isinstance(citation, dict):
                findings.append(
                    {
                        "article": citation.get("article", citation.get("reference", "unknown")),
                        "description": citation.get("text", citation.get("content", "")),
                    }
                )

    # Monitor output format
    elif task_type == "monitor":
        actions = output.get("required_actions", [])
        if not actions:
            actions = output.get("actions", [])
        for action in actions:
            if isinstance(action, dict):
                findings.append(
                    {
                        "article": action.get("article", action.get("regulation", "unknown")),
                        "description": action.get("description", action.get("action", "")),
                        "urgency": action.get("urgency", "medium"),
                    }
                )

    return findings


def calculate_test_metrics(
    test_case: TestCase,
    normaai_output: dict,
    execution_time_ms: float = 0.0,
    error: str | None = None,
) -> TestResult:
    """
    Calculate precision, recall, F1 for a single test case.

    Compares NormaAI's output against the expected findings (ground truth).
    """
    result = TestResult(
        test_case_id=test_case.id,
        normaai_output=normaai_output,
        execution_time_ms=execution_time_ms,
        error=error,
    )

    if error:
        # All expected findings are false negatives if there's an error
        result.false_negatives = [f.article for f in test_case.expected_findings]
        return result

    # Extract findings from NormaAI output
    detected = extract_findings_from_output(normaai_output, test_case.task_type)
    result.detected_findings = detected

    # Get detected article IDs
    detected_articles = [d.get("article", "") for d in detected]

    # Calculate TP, FN, FP
    matched_expected = set()
    matched_detected = set()

    for i, expected in enumerate(test_case.expected_findings):
        for j, det_art in enumerate(detected_articles):
            if j not in matched_detected and articles_match(expected.article, det_art):
                result.true_positives.append(expected.article)
                matched_expected.add(i)
                matched_detected.add(j)
                break
        else:
            result.false_negatives.append(expected.article)

    # Unmatched detected findings = false positives
    for j, det_art in enumerate(detected_articles):
        if j not in matched_detected:
            # Check if it's in the "expected not findings" list
            is_known_fp = any(
                articles_match(not_expected, det_art)
                for not_expected in test_case.expected_not_findings
            )
            if is_known_fp or det_art not in [f.article for f in test_case.expected_findings]:
                result.false_positives.append(det_art)

    # Calculate metrics
    tp = len(result.true_positives)
    fp = len(result.false_positives)
    fn = len(result.false_negatives)

    result.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    result.recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    result.f1_score = (
        2 * result.precision * result.recall / (result.precision + result.recall)
        if (result.precision + result.recall) > 0
        else 0.0
    )
    result.confidence_score = normaai_output.get("confidence_score", 0.0)

    return result


def aggregate_suite_results(
    suite_name: str,
    results: list[TestResult],
    test_cases: list[TestCase],
) -> SuiteResult:
    """
    Aggregate individual test results into suite-level metrics.

    Calculates per-framework and per-difficulty breakdowns.
    """
    suite = SuiteResult(suite_name=suite_name, results=results)
    suite.total_cases = len(results)

    if not results:
        return suite

    # Basic counts
    suite.error_cases = sum(1 for r in results if r.error)
    valid_results = [r for r in results if not r.error]

    # Define pass criteria per test
    suite.passed_cases = sum(1 for r in valid_results if r.recall >= suite.recall_threshold)
    suite.failed_cases = len(valid_results) - suite.passed_cases

    # Aggregate metrics
    if valid_results:
        suite.avg_precision = sum(r.precision for r in valid_results) / len(valid_results)
        suite.avg_recall = sum(r.recall for r in valid_results) / len(valid_results)
        suite.avg_f1 = sum(r.f1_score for r in valid_results) / len(valid_results)
        suite.min_recall = min(r.recall for r in valid_results)

    # Per-framework breakdown
    case_map = {tc.id: tc for tc in test_cases}
    framework_groups: dict[str, list[TestResult]] = {}
    difficulty_groups: dict[str, list[TestResult]] = {}

    for r in valid_results:
        tc = case_map.get(r.test_case_id)
        if tc:
            # Group by framework
            for finding in tc.expected_findings:
                fw = finding.framework.value
                framework_groups.setdefault(fw, []).append(r)
                break  # Use first framework

            # Group by difficulty
            diff_key = f"level_{tc.difficulty.value}"
            difficulty_groups.setdefault(diff_key, []).append(r)

    for fw, fw_results in framework_groups.items():
        suite.framework_metrics[fw] = {
            "count": len(fw_results),
            "avg_precision": sum(r.precision for r in fw_results) / len(fw_results),
            "avg_recall": sum(r.recall for r in fw_results) / len(fw_results),
            "avg_f1": sum(r.f1_score for r in fw_results) / len(fw_results),
        }

    for diff, diff_results in difficulty_groups.items():
        suite.difficulty_metrics[diff] = {
            "count": len(diff_results),
            "avg_precision": sum(r.precision for r in diff_results) / len(diff_results),
            "avg_recall": sum(r.recall for r in diff_results) / len(diff_results),
            "avg_f1": sum(r.f1_score for r in diff_results) / len(diff_results),
        }

    return suite
