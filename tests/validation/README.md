# NormaAI Validation & Benchmarking Framework

Comprehensive testing framework for validating NormaAI's compliance analysis across multiple regulatory frameworks (GDPR, DORA, NIS2, CSRD, AI Act, EU Taxonomy, CSDDD).

## Architecture

### Core Components

1. **schemas.py** (209 lines)
   - Pydantic models for structured test cases
   - Enums: Framework, ViolationType, Severity, TestCaseSource, DifficultyLevel
   - Classes: TestCase, ExpectedFinding, DocumentInput, CompanyProfile
   - Classes: TestResult, SuiteResult for storing results and metrics

2. **metrics.py** (261 lines)
   - Precision, recall, and F1 calculation engine
   - Article matching with fuzzy logic (parent-child matching)
   - Finding extraction from NormaAI output (gap_analysis, qa, monitor modes)
   - Suite-level aggregation with per-framework and per-difficulty breakdowns

3. **runner.py** (349 lines)
   - Test execution engine with async/await support
   - Test case loading from JSON files with filtering
   - Concurrent execution with semaphore control
   - Report generation (text and JSON formats)
   - CLI interface for running suites

## Test Case Structure

Each test case (`TestCase`) contains:

- **Metadata**: id, name, description, source_type, difficulty level, tags
- **Inputs**: 
  - task_type (qa, gap_analysis, monitor)
  - query (what framework to check)
  - document (the compliance document under test)
  - company_profile (organizational context)
- **Ground Truth**: 
  - expected_findings (violations that should be detected)
  - expected_not_findings (articles that should NOT be flagged)

### Test Case Sources

- **SANCTION**: Real enforcement actions from regulatory authorities
- **SYNTHETIC**: Generated documents with injected flaws
- **GREENWASHING**: Deceptive sustainability claims
- **EXPERT_VALIDATED**: Cases validated by legal experts
- **ADVERSARIAL**: Designed to trick the system

### Difficulty Levels

1. **OBVIOUS**: Clauses completely missing
2. **SUBTLE**: Clauses present but incomplete
3. **ADVERSARIAL**: Looks compliant but isn't
4. **CROSS_FRAMEWORK**: Compliant for one framework, violates another
5. **TEMPORAL**: Compliant under old law, not under current

## Metrics Calculation

### Per-Test Metrics

- **Precision**: TP / (TP + FP) - accuracy of positive predictions
- **Recall**: TP / (TP + FN) - coverage of actual violations
- **F1 Score**: 2 × (Precision × Recall) / (Precision + Recall)

### Article Matching Logic

Fuzzy matching allows:
- Exact matches: Art. 13 = Art. 13(2)(a)
- Normalized comparisons: "Article 28(3)(h)" = "Art 28 3 h"
- Parent-child matches: Art. 13 detects Art. 13(2)(a)

### Suite-Level Aggregation

- Per-framework breakdown (GDPR, DORA, NIS2, etc.)
- Per-difficulty breakdown (Levels 1-5)
- Aggregate metrics (avg precision, recall, F1, min recall)
- Pass/fail determination based on thresholds

## Usage

### Running a Full Suite

```bash
python -m tests.validation.runner --suite golden_set
```

### Filtering Test Cases

```bash
python -m tests.validation.runner --suite sanctions --framework GDPR
python -m tests.validation.runner --suite synthetic --difficulty 3
```

### Running a Specific Test Case

```bash
python -m tests.validation.runner --case GDPR-SANCTION-2024-IT-042
```

### Demo Mode (No Real NormaAI)

```bash
python -m tests.validation.runner --suite all --demo
```

### Verbose Output

```bash
python -m tests.validation.runner --suite golden_set --verbose
```

## Test Case File Structure

Test cases are stored in JSON files in `tests/validation/test_cases/` directory:

```
tests/validation/test_cases/
├── sanctions/           # Real enforcement actions
│   └── *.json
├── synthetic/           # Generated test cases
│   └── *.json
├── greenwashing/        # Deceptive claims
│   └── *.json
└── adversarial/         # Challenging edge cases
    └── *.json
```

Each JSON file contains either:
- A single test case with "id" field
- An array of test cases
- An object with "test_cases" array

## Reports

Test runs generate two types of reports in `tests/validation/reports/`:

1. **JSON Report** (`{suite}_{timestamp}.json`)
   - Complete structured results
   - All metrics and individual findings
   - Machine-readable format

2. **Text Report** (`{suite}_{timestamp}.txt`)
   - Human-readable formatted output
   - Aggregate metrics
   - Per-framework and per-difficulty breakdowns
   - Failed tests summary

### Report Contents

- Overall results (Total, Passed, Failed, Errors)
- Aggregate metrics (Precision, Recall, F1, Min Recall)
- Framework-specific performance
- Difficulty-level performance
- Detailed failure analysis

## Pass/Fail Thresholds

Default thresholds (configurable in SuiteResult):
- **Recall**: ≥0.95 (catch 95% of violations)
- **Precision**: ≥0.80 (minimize false positives)
- **F1 Score**: ≥0.87 (balanced performance)

## Integration with NormaAI

The runner calls three agent functions:
- `arun_gap_analysis(query, company_profile)` - identifies compliance gaps
- `arun_qa(query, company_profile)` - answers regulatory questions
- `arun_monitor_check(query, company_profile)` - monitors compliance status

Each returns a dict with findings that metrics.py extracts.

## Output Format Handling

The framework handles multiple NormaAI output formats:

### Gap Analysis Output
```json
{
  "requirements": [
    {
      "article": "Art. 13(2)(a)",
      "status": "NON_COMPLIANT",
      "description": "...",
      "severity": "major"
    }
  ]
}
```

### QA Output
```json
{
  "answer": "...",
  "citations": [
    {"article": "Art. 13", "text": "..."}
  ]
}
```

### Monitor Output
```json
{
  "required_actions": [
    {"article": "Art. 28", "description": "..."}
  ]
}
```

## Directory Structure

```
tests/validation/
├── __init__.py           # Package initialization
├── schemas.py            # Pydantic data models
├── metrics.py            # Metrics calculation engine
├── runner.py             # Test execution and reporting
├── test_cases/           # Test case JSON files
│   ├── sanctions/
│   ├── synthetic/
│   ├── greenwashing/
│   └── adversarial/
└── reports/              # Generated test reports
    ├── *.json            # Machine-readable results
    └── *.txt             # Human-readable reports
```

## Next Steps

1. **Populate Test Cases**: Add JSON files to `test_cases/` subdirectories
2. **Run Initial Suite**: Execute `--suite golden_set --demo` to validate framework
3. **Integrate Real Tests**: Replace demo data with actual regulatory test cases
4. **Monitor Performance**: Track metrics across NormaAI versions
5. **Expand Coverage**: Add more frameworks and difficulty levels
