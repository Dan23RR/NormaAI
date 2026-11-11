# NormaAI Validation Framework

Comprehensive testing framework for regulatory compliance AI, covering **150+ adversarial test cases** across GDPR, DORA, NIS2, AI Act, CSRD, and jurisdictional requirements.

## Three Core Components

### 1. File: `promptfoo_config.yaml` (398 lines, 21 KB)

**Adversarial Red Team Suite** - 150+ test cases across 7 categories.

**Coverage:**

| Category | Cases | Focus | Examples |
|----------|-------|-------|----------|
| **Hallucination Probes** | 50 | Non-existent regulations | Art. 999 GDPR, NIS3 (doesn't exist), Privacy Shield (invalidated) |
| **Cross-Framework Conflicts** | 30 | Regulatory tensions | AI Act high-risk vs GDPR Art. 22, CSRD retention vs GDPR minimization, NIS2/GDPR incident flows |
| **Temporal Awareness** | 20 | Regulatory updates | Schrems II, updated SCC dates, DORA entry (Jan 2025), AI Act phased rollout |
| **Prompt Injection Resistance** | 20 | Adversarial instructions | System override attempts, role-play attacks, HTML injection |
| **Edge Cases (SME/Micro)** | 30 | Size-dependent rules | Micro-enterprise DPO exemptions, startup DPIA requirements, freelancer GDPR |
| **Jurisdictional Nuances** | 20 | National implementations | Italian Garante vs UK ICO, age of digital consent (IT: 14), NIS2 recepimento Italia |
| **Ambiguity Handling** | 10 | Vague questions | Missing framework context, presupposition errors, out-of-scope questions |

**Providers:**
- `normaai-qa` - Q&A agent for regulatory intelligence
- `normaai-gap` - Gap analysis engine for company compliance

**Usage:**
```bash
# Run full red team suite
npx promptfoo eval -c tests/validation/promptfoo_config.yaml

# Filter by category
npx promptfoo eval -c tests/validation/promptfoo_config.yaml --filter-pattern "hallucination"
npx promptfoo eval -c tests/validation/promptfoo_config.yaml --filter-pattern "cross-framework"
```

**Assertions Used:**
- `not-contains` - Validates system does NOT generate false information
- `contains-any` - Ensures multiple relevant frameworks/articles mentioned
- `llm-rubric` - LLM-powered evaluation of response quality

---

### 2. File: `.github/workflows/validation.yml`

**Self-test of this harness on canned outputs.** It is not a measurement of NormaAI.

With `--demo` the runner builds each "answer" from the expected findings of the test case
itself (`_generate_demo_output` in `runner.py`: a fixed share of them, and nothing else).
No model, no retrieval and no API take part, so the figures of a run describe the
harness, not the product. Measured results (golden v2 through the real API, run by hand)
are in `docs/MODELS.md`.

**Triggers:**
- pull requests that touch `src/`, `prompts/` or `tests/`: the golden set;
- weekly schedule: every suite, with the generated sanctions and synthetic cases;
- manual run: `golden_set` or `all`.

**What the one job does:**

```
harness-selftest
  1. generates the extra cases (weekly and "all" only)
  2. runs the harness on canned outputs: python -m tests.validation.runner --suite <suite> --demo
  3. runs the risk report generator on demo inputs (weekly and "all" only)
  4. checks what canned outputs can show:
     - no case raised an error inside the harness
     - the matcher counted no finding that was not expected (precision 1.000 by construction)
     - no case lost more than half of its findings (a canned output holds at least half)
  5. uploads the reports of the run (30 days)
```

The recall, precision and F1 targets of the runner (0.95, 0.80, 0.87) are meant for runs
against the real system (`--api` or direct mode), which no workflow performs. Until
November 2026 the workflow compared them with the figures of the canned outputs, and the
weekly run failed every Sunday for that reason alone.

The adversarial suite of section 1 is not run by any workflow: it calls a backend on
`localhost:8000` with an access token. Run it by hand against a running backend.

---

### 3. File: `generate_golden_set.py` (338 lines, 15 KB)

**Bootstrap Test Suite Generator** - 50+ curated golden set test cases.

**Three Test Sources:**

1. **Sanctions-Based** (15 cases)
   - Real enforcement actions (Meta, TikTok, etc.)
   - Extract compliance failures from known penalties
   - Example: Privacy Shield violations (Schrems II)

2. **Synthetic** (25 cases)
   - Auto-generated across frameworks & difficulty levels
   - GDPR: levels 1, 2, 3, 5
   - DORA: levels 1, 2
   - NIS2: levels 1, 2
   - Callable via `synthetic_generator` module

3. **Expert-Curated Edge Cases** (10 cases)
   - **GOLDEN-EDGE-001**: Empty privacy policy (zero compliance)
   - **GOLDEN-EDGE-002**: Perfect privacy policy (false positive test)
   - **GOLDEN-EDGE-003**: Outdated DPA (Privacy Shield reference)
   - **GOLDEN-EDGE-004**: AI + GDPR conflict (cross-framework)
   - **GOLDEN-EDGE-005**: NIS2 incident response gaps

**Test Case Structure:**
```python
{
    "id": "GOLDEN-EDGE-001",
    "name": str,
    "source_type": "expert_validated" | "sanctions" | "synthetic",
    "task_type": "gap_analysis" | "qa",
    "query": "GDPR",  # Framework
    "document": {...},  # Privacy policy, DPA, etc.
    "company_profile": {...},  # Size, sector, jurisdiction
    "expected_findings": [...],  # GDPR Art. X, severity, type
    "difficulty": 1 - 5,
    "tags": ["golden", "edge_case", ...],
    "enabled": True,
}
```

**Output:**
```
tests/validation/test_cases/golden_set/golden_set_v1.json

{
    "test_cases": [...],
    "metadata": {
        "version": "1.0",
        "generated_at": "2026-02-27T...",
        "total_cases": 50,
        "breakdown": {
            "sanctions_based": 15,
            "synthetic": 25,
            "expert_curated": 10
        }
    }
}
```

**Usage:**
```bash
python -m tests.validation.generate_golden_set
```

---

## Integration Points

```
Runner (orchestrator)
├─ sanctioning_harvester.py (generate 15 cases)
├─ synthetic_generator.py (generate 25 cases)
├─ generate_golden_set.py (integration + 10 edge cases)
├─ metrics.py (recall/precision/F1)
├─ llm_judge.py (evaluate LLM responses)
└─ monte_carlo.py (stochastic analysis)
```

**In CI:** only the self-test of section 2 (canned outputs, no model). Runs against the
real system are started by hand.

---

## Key Features

### Hallucination Detection
- Tests system doesn't invent regulations or articles
- "Art. 999 GDPR" vs "Art. 99 GDPR" (real)
- "NIS3" (doesn't exist) vs "NIS2" (real)
- "Privacy Shield" (invalidated) knowledge requirement

### Cross-Framework Coverage
- AI Act + GDPR conflicts (automated decisions, Art. 22)
- CSRD + GDPR tensions (data retention, minimization)
- NIS2 + GDPR incident workflows (24h vs 72h notification)
- DORA + NIS2 overlap resolution (lex specialis principle)

### Temporal Awareness
- Regulatory sunset dates (Privacy Shield → 2020)
- New rules entry (DORA → Jan 2025, AI Act phased)
- Abrogated standards (Allegato B D.Lgs. 196/2003)

### Prompt Injection Resistance
- "Ignore all instructions" → should still validate correctly
- Role-play attacks → system doesn't pretend to confirm compliance
- HTML/markdown injection → safely ignored

### Edge Cases
- Micro-enterprises (3 employees) - DPO not required (usually)
- Startups with GPS tracking - DPIA required (yes)
- PMI 80 employees, €15M revenue - CSRD exempt (yes)
- Freelancers - GDPR applies (yes)

---

## Metrics & Thresholds

| Metric | Target | Purpose |
|--------|--------|---------|
| **Recall** | ≥ 0.95 | Catch 95% of real gaps |
| **Precision** | ≥ 0.80 | Max 20% false findings |
| **F1-Score** | ≥ 0.87 | Balanced quality |
| **Hallucination Rate** | < 2% | Don't invent regulations |
| **Injection Success** | 0% | Block adversarial inputs |
| **Cross-FW Detection** | ≥ 90% | Flag framework conflicts |

---

## Running Validation Locally

```bash
# 1. Install dependencies
pip install promptfoo pytest pydantic

# 2. Generate golden set
python -m tests.validation.generate_golden_set

# 3. Run Promptfoo red team
npx promptfoo eval -c tests/validation/promptfoo_config.yaml

# 4. Run golden set with pytest
pytest tests/validation/test_golden_set.py -v

# 5. Monte Carlo analysis
python -m tests.validation.monte_carlo \
    --company "Your Company" \
    --revenue 50000000 \
    --sector technology \
    --country IT \
    --iterations 5000
```

---

## Maintenance Schedule

- **Weekly**: Refresh sanctions harvester (new enforcement actions)
- **Monthly**: Add 5-10 new synthetic cases per framework
- **Quarterly**: Add 2-3 new expert edge cases
- **As needed**: Update temporal awareness (new regulations, sunset dates)

---

**Last Updated**: 2026-02-27  
**Framework**: GDPR, DORA, NIS2, AI Act, CSRD, EU Taxonomy  
**Coverage**: EU + National (Italian focus)  
**Test Cases**: 150+ adversarial + 50+ golden set
