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

### 2. File: `.github/workflows/validation.yml` (223 lines, 6.4 KB)

**CI/CD Pipeline** - Multi-stage validation with thresholds.

**Workflow Triggers:**
- **PR validation** (golden set) - Fast check on every pull request
- **Full regression** (on merge to main, weekly schedule) - 500+ test cases
- **Red team** (weekly) - Promptfoo adversarial suite
- **Manual trigger** - Parameterized runs with suite/framework filters

**Job Stages:**

```
├─ golden-set [PR trigger]
│  ├─ Setup Python 3.11
│  ├─ Run Golden Set (demo mode)
│  └─ Upload results (30-day retention)
│
├─ full-regression [main merge / schedule]
│  ├─ Spin up: PostgreSQL 16 + Qdrant
│  ├─ Generate test cases
│  │  ├─ Sanctions harvester (enforcement data)
│  │  ├─ Synthetic GDPR/DORA/NIS2 (levels 1-5)
│  │  └─ Monte Carlo simulation (5000 iterations)
│  ├─ Run full suite (demo mode)
│  └─ Check thresholds:
│     ├─ Recall ≥ 0.95
│     ├─ Precision ≥ 0.80
│     └─ F1 ≥ 0.87
│
└─ red-team [weekly schedule]
   ├─ Setup Node.js 20 + Promptfoo
   ├─ Run adversarial suite
   └─ Upload results (90-day retention)
```

**Performance Thresholds:**
- **Recall ≥ 0.95**: Must catch 95% of actual compliance gaps
- **Precision ≥ 0.80**: Max 20% false positives
- **F1 ≥ 0.87**: Balanced quality metric

**Monte Carlo Integration:**
- 5000 iterations per run
- Simulates company variations (size, sector, jurisdiction)
- Estimates confidence intervals for findings

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
    "difficulty": 1-5,
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

**CI/CD Flow:**
```
PR → golden-set (50 cases, 5 min) ✓
  ↓
merge → full-regression (500 cases, 30 min) ✓
  ↓
weekly → red-team (150 adversarial, 20 min) ✓
  ↓
Monte Carlo (5000 iterations, 60 min)
```

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
