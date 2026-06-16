"""
NormaAI Validation Test Runner.

Loads test cases from JSON files, runs them through NormaAI agents,
calculates metrics, and generates reports.

Three execution modes:
    --demo          Mock responses (no backend needed)
    --api           HTTP calls to running NormaAI backend
    (default)       Direct Python import of agents (in-process)

Usage:
    # Demo mode (no backend)
    python -m tests.validation.runner --suite golden_set --demo --verbose

    # API mode (requires running backend at localhost:8000)
    python -m tests.validation.runner --suite golden_set --api --verbose

    # Direct agent mode (requires full Python env with src/ importable)
    python -m tests.validation.runner --suite golden_set --verbose

    # Filter by framework or difficulty
    python -m tests.validation.runner --suite all --framework GDPR --api
    python -m tests.validation.runner --suite golden_set --difficulty 3 --api

    # Single test case
    python -m tests.validation.runner --case GDPR-SANCTION-2024-IT-001-L1 --api
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from .metrics import aggregate_suite_results, calculate_test_metrics
from .schemas import SuiteResult, TestCase, TestResult

logger = logging.getLogger(__name__)

TEST_CASES_DIR = Path(__file__).parent / "test_cases"
REPORTS_DIR = Path(__file__).parent / "reports"


def load_test_cases(
    suite: str = "all",
    framework: str | None = None,
    difficulty: int | None = None,
    case_id: str | None = None,
) -> list[TestCase]:
    """
    Load test cases from JSON files.

    Args:
        suite: Suite name ('all', 'golden_set', 'sanctions', 'synthetic', 'greenwashing')
        framework: Filter by framework (e.g., 'GDPR')
        difficulty: Filter by difficulty level (1-5)
        case_id: Load a specific test case by ID
    """
    cases: list[TestCase] = []

    if suite == "all":
        search_dirs = [TEST_CASES_DIR]
    else:
        suite_dir = TEST_CASES_DIR / suite
        search_dirs = [suite_dir] if suite_dir.exists() else [TEST_CASES_DIR]

    for search_dir in search_dirs:
        for json_file in search_dir.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))

                # Handle both single case and array of cases
                if isinstance(data, list):
                    for item in data:
                        cases.append(TestCase(**item))
                elif isinstance(data, dict):
                    # Check if it's a single case or a wrapper
                    if "test_cases" in data:
                        for item in data["test_cases"]:
                            cases.append(TestCase(**item))
                    elif "id" in data:
                        cases.append(TestCase(**data))

            except Exception as e:
                logger.warning(f"Failed to load {json_file}: {e}")

    # Apply filters
    if case_id:
        cases = [c for c in cases if c.id == case_id]
    if framework:
        cases = [
            c for c in cases if any(f.framework.value == framework for f in c.expected_findings)
        ]
    if difficulty:
        cases = [c for c in cases if c.difficulty.value == difficulty]

    # Only enabled cases
    cases = [c for c in cases if c.enabled]

    return cases


# ─── Execution Modes ──────────────────────────────────────────────


async def run_single_test(
    test_case: TestCase,
    mode: str = "demo",
    api_client=None,
) -> TestResult:
    """
    Run a single test case through NormaAI.

    Args:
        test_case: The test case to run
        mode: "demo", "api", or "direct"
        api_client: NormaAIClient instance (required for mode="api")

    Returns:
        TestResult with metrics
    """
    start_time = time.time()

    try:
        if mode == "demo":
            output = _generate_demo_output(test_case)
        elif mode == "api":
            output = await _call_normaai_api(test_case, api_client)
        else:
            output = await _call_normaai_direct(test_case)

        elapsed_ms = (time.time() - start_time) * 1000
        return calculate_test_metrics(test_case, output, elapsed_ms)

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"Test {test_case.id} failed: {e}")
        return calculate_test_metrics(test_case, {}, elapsed_ms, error=str(e))


async def _call_normaai_api(test_case: TestCase, client) -> dict:
    """
    Call NormaAI via HTTP API and parse the response.

    This is the preferred mode for real validation:
    tests the full stack including API routing, auth, serialization.
    """
    from .response_parser import parse_api_response

    if client is None:
        raise RuntimeError("API client not provided. Use --api flag and ensure backend is running.")

    # Build company profile dict
    profile = test_case.company_profile.model_dump()

    # If the test case has inline document content, pass it as existing_documents
    if test_case.document and test_case.document.content:
        profile["existing_documents"] = test_case.document.content

    # Call the appropriate endpoint
    if test_case.task_type == "gap_analysis":
        # For gap analysis, query is the framework name
        framework = test_case.query  # e.g., "GDPR"
        raw_response = await client.run_gap_analysis(framework, profile)
    elif test_case.task_type == "qa":
        raw_response = await client.run_qa(test_case.query, profile)
    elif test_case.task_type == "monitor":
        raw_response = await client.run_monitor(test_case.query, profile)
    else:
        raise ValueError(f"Unknown task type: {test_case.task_type}")

    # Parse API response into the format metrics.py expects
    return parse_api_response(raw_response, test_case.task_type)


async def _call_normaai_direct(test_case: TestCase) -> dict:
    """
    Call NormaAI agents directly via Python import.

    Faster but doesn't test the API layer.
    Requires src/ to be importable (PYTHONPATH=.).
    """
    from src.agents.graph import arun_gap_analysis, arun_monitor_check, arun_qa

    profile = test_case.company_profile.model_dump()

    # If the document has inline content, add it to the profile
    if test_case.document and test_case.document.content:
        profile["existing_documents"] = test_case.document.content

    if test_case.task_type == "gap_analysis":
        return await arun_gap_analysis(test_case.query, profile)
    elif test_case.task_type == "qa":
        return await arun_qa(test_case.query, profile)
    elif test_case.task_type == "monitor":
        return await arun_monitor_check(test_case.query, profile)
    else:
        raise ValueError(f"Unknown task type: {test_case.task_type}")


def _generate_demo_output(test_case: TestCase) -> dict:
    """
    Generate a demo output that simulates NormaAI detecting SOME findings.

    For testing the test infrastructure itself, not for real validation.
    Returns ~70% of expected findings as detected (simulating imperfect system).
    """
    import random

    findings = test_case.expected_findings
    # Simulate detecting 70% of findings
    n_detect = max(1, int(len(findings) * 0.7))
    detected = random.sample(findings, min(n_detect, len(findings)))

    if test_case.task_type == "gap_analysis":
        return {
            "requirements": [
                {
                    "article": f.article,
                    "status": "NON_COMPLIANT",
                    "description": f.description,
                    "severity": f.severity.value,
                }
                for f in detected
            ],
            "compliance_score": random.uniform(20, 60),
            "confidence_score": random.uniform(0.7, 0.95),
        }
    elif test_case.task_type == "qa":
        return {
            "answer": "Test answer based on regulatory analysis.",
            "citations": [{"article": f.article, "text": f.description} for f in detected],
            "confidence_score": random.uniform(0.7, 0.95),
        }
    else:
        return {
            "required_actions": [
                {"article": f.article, "description": f.description} for f in detected
            ],
            "confidence_score": random.uniform(0.7, 0.95),
        }


# ─── Suite Runner ─────────────────────────────────────────────────


async def run_suite(
    suite_name: str,
    cases: list[TestCase],
    mode: str = "demo",
    max_concurrent: int = 5,
    api_client=None,
) -> SuiteResult:
    """
    Run a full test suite with concurrency control.

    Args:
        suite_name: Name for the suite run
        cases: Test cases to run
        mode: "demo", "api", or "direct"
        max_concurrent: Max concurrent test executions
        api_client: NormaAIClient instance (for mode="api")
    """
    # In API mode, limit concurrency to avoid rate limits
    if mode == "api":
        max_concurrent = min(max_concurrent, 3)

    logger.info(
        f"Running suite '{suite_name}' with {len(cases)} test cases "
        f"(mode={mode}, concurrency={max_concurrent})"
    )

    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(tc: TestCase) -> TestResult:
        async with semaphore:
            return await run_single_test(tc, mode=mode, api_client=api_client)

    results = await asyncio.gather(
        *[run_with_semaphore(tc) for tc in cases],
        return_exceptions=True,
    )

    # Convert exceptions to error results
    processed_results: list[TestResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed_results.append(
                TestResult(
                    test_case_id=cases[i].id,
                    error=str(r),
                )
            )
        else:
            processed_results.append(r)

    return aggregate_suite_results(suite_name, processed_results, cases)


# ─── Report Generation ────────────────────────────────────────────


def generate_report(suite_result: SuiteResult, mode: str = "demo") -> str:
    """Generate a human-readable report from suite results."""
    mode_label = {"demo": "DEMO", "api": "API", "direct": "DIRECT"}.get(mode, mode.upper())
    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        f"║  NormaAI Validation Report: {suite_result.suite_name:<28s}║",
        "╠══════════════════════════════════════════════════════════╣",
        f"║  Mode: {mode_label:<49s}║",
        f"║  Run: {suite_result.run_timestamp:<50s}║",
        "╠══════════════════════════════════════════════════════════╣",
        "║  OVERALL RESULTS                                        ║",
        f"║  Total:  {suite_result.total_cases:<47d}║",
        f"║  Passed: {suite_result.passed_cases:<47d}║",
        f"║  Failed: {suite_result.failed_cases:<47d}║",
        f"║  Errors: {suite_result.error_cases:<47d}║",
        "╠══════════════════════════════════════════════════════════╣",
        "║  AGGREGATE METRICS                                      ║",
        f"║  Precision:  {suite_result.avg_precision:.4f}  (target: ≥{suite_result.precision_threshold})          ║",
        f"║  Recall:     {suite_result.avg_recall:.4f}  (target: ≥{suite_result.recall_threshold})          ║",
        f"║  F1 Score:   {suite_result.avg_f1:.4f}  (target: ≥{suite_result.f1_threshold})          ║",
        f"║  Min Recall: {suite_result.min_recall:.4f}                                  ║",
        f"║  Suite Pass: {'✅ YES' if suite_result.suite_passed else '❌ NO':<50s}║",
        "╠══════════════════════════════════════════════════════════╣",
    ]

    if suite_result.framework_metrics:
        lines.append("║  PER-FRAMEWORK BREAKDOWN                                ║")
        for fw, m in sorted(suite_result.framework_metrics.items()):
            lines.append(
                f"║  {fw:<12s} P={m['avg_precision']:.3f} R={m['avg_recall']:.3f} "
                f"F1={m['avg_f1']:.3f} (n={m['count']})       ║"
            )
        lines.append("╠══════════════════════════════════════════════════════════╣")

    if suite_result.difficulty_metrics:
        lines.append("║  PER-DIFFICULTY BREAKDOWN                               ║")
        for diff, m in sorted(suite_result.difficulty_metrics.items()):
            lines.append(
                f"║  {diff:<12s} P={m['avg_precision']:.3f} R={m['avg_recall']:.3f} "
                f"F1={m['avg_f1']:.3f} (n={m['count']})       ║"
            )
        lines.append("╠══════════════════════════════════════════════════════════╣")

    # Error details
    errors = [r for r in suite_result.results if r.error]
    if errors:
        lines.append("║  ERRORS                                                 ║")
        for r in errors[:5]:
            err_short = r.error[:50] if r.error else "?"
            lines.append(f"║  {r.test_case_id}: {err_short}  ║")
        if len(errors) > 5:
            lines.append(f"║  ... and {len(errors) - 5} more errors              ║")
        lines.append("╠══════════════════════════════════════════════════════════╣")

    # Latency stats (only in API/direct mode)
    if mode != "demo":
        latencies = [r.execution_time_ms for r in suite_result.results if r.execution_time_ms > 0]
        if latencies:
            avg_lat = sum(latencies) / len(latencies)
            max_lat = max(latencies)
            min_lat = min(latencies)
            lines.append("║  LATENCY (ms)                                           ║")
            lines.append(
                f"║  Avg: {avg_lat:>8.0f}  Min: {min_lat:>8.0f}  Max: {max_lat:>8.0f}          ║"
            )
            lines.append("╠══════════════════════════════════════════════════════════╣")

    # Failed tests detail
    failed = [r for r in suite_result.results if r.false_negatives]
    if failed:
        lines.append("║  MISSED FINDINGS (False Negatives)                      ║")
        for r in failed[:10]:  # Show first 10
            lines.append(f"║  {r.test_case_id}: missed {r.false_negatives}  ║")
        if len(failed) > 10:
            lines.append(f"║  ... and {len(failed) - 10} more                    ║")

    lines.append("╚══════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


def save_report(suite_result: SuiteResult, mode: str = "demo") -> Path:
    """Save suite result as JSON and text report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = suite_result.run_timestamp.replace(":", "-").replace(".", "-")[:19]
    mode_suffix = f"_{mode}" if mode != "demo" else ""
    base_name = f"{suite_result.suite_name}{mode_suffix}_{timestamp}"

    # JSON report
    json_path = REPORTS_DIR / f"{base_name}.json"
    json_path.write_text(
        suite_result.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Text report
    txt_path = REPORTS_DIR / f"{base_name}.txt"
    txt_path.write_text(generate_report(suite_result, mode), encoding="utf-8")

    logger.info(f"Reports saved: {json_path}, {txt_path}")
    return json_path


# ─── CLI ──────────────────────────────────────────────────────────


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="NormaAI Validation Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution modes:
  --demo      Mock responses (default, no backend needed)
  --api       HTTP calls to running backend (requires docker compose up)
  (neither)   Direct Python agent import (requires PYTHONPATH=.)

Examples:
  python -m tests.validation.runner --suite golden_set --demo --verbose
  python -m tests.validation.runner --suite golden_set --api --verbose
  python -m tests.validation.runner --suite golden_set --api --base-url http://my-server:8000
  python -m tests.validation.runner --case GDPR-SANCTION-2024-IT-001-L1 --api
        """,
    )
    parser.add_argument("--suite", default="golden_set", help="Test suite to run")
    parser.add_argument("--framework", default=None, help="Filter by framework")
    parser.add_argument("--difficulty", type=int, default=None, help="Filter by difficulty (1-5)")
    parser.add_argument("--case", default=None, help="Run a specific test case by ID")
    parser.add_argument("--demo", action="store_true", help="Use demo mode (no real NormaAI)")
    parser.add_argument(
        "--api", action="store_true", help="Use HTTP API mode (requires running backend)"
    )
    parser.add_argument(
        "--base-url", default=None, help="Backend URL (default: http://localhost:8000)"
    )
    parser.add_argument("--email", default=None, help="Override test user email")
    parser.add_argument("--password", default=None, help="Override test user password")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent tests")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Determine mode
    if args.demo:
        mode = "demo"
    elif args.api:
        mode = "api"
    else:
        mode = "direct"

    # Load test cases
    cases = load_test_cases(
        suite=args.suite,
        framework=args.framework,
        difficulty=args.difficulty,
        case_id=args.case,
    )

    if not cases:
        print(f"No test cases found for suite='{args.suite}'")
        sys.exit(1)

    print(f"Loaded {len(cases)} test cases")

    # Setup API client if needed
    api_client = None
    if mode == "api":
        from .api_client import APIConfig, AuthenticationError, NormaAIClient

        config = APIConfig()
        if args.base_url:
            config.base_url = args.base_url

        client = NormaAIClient(config=config)
        await client.connect()

        try:
            # Health check
            print(f"Checking backend at {config.base_url}...")
            health = await client.health_check()

            if health.get("qdrant") != "up":
                print("⚠  WARNING: Qdrant is not available. Results may be degraded.")
            if health.get("llm") != "configured":
                print("⚠  WARNING: LLM is not configured. API calls will fail.")
                sys.exit(1)

            print(f"✓  Backend healthy (qdrant={health.get('qdrant')}, llm={health.get('llm')})")

            # Authenticate
            print("Authenticating...")
            await client.authenticate(
                email=args.email,
                password=args.password,
            )
            print("✓  Authenticated")

            api_client = client
        except ConnectionError as e:
            print(f"\n✗  {e}")
            print("\nMake sure the backend is running:")
            print("  docker compose up -d")
            print("  # or: uvicorn src.api.main:app --host 0.0.0.0 --port 8000")
            sys.exit(1)
        except AuthenticationError as e:
            print(f"\n✗  {e}")
            print("\nTry with explicit credentials:")
            print("  --email your@email.com --password yourpassword")
            sys.exit(1)

    # Run suite
    try:
        result = await run_suite(
            args.suite,
            cases,
            mode=mode,
            max_concurrent=args.concurrency,
            api_client=api_client,
        )

        # Print and save
        report = generate_report(result, mode)
        print(report)
        save_report(result, mode)

        # Print API client stats if applicable
        if api_client:
            stats = api_client.stats
            print(
                f"\nAPI Stats: {stats['total_requests']} requests, "
                f"{stats['total_errors']} errors"
            )

    finally:
        if api_client:
            await api_client.close()

    # Exit code based on pass/fail
    sys.exit(0 if result.suite_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
