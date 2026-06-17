"""
Monte Carlo Regulatory Risk Simulation Engine.

Translates NormaAI gap analysis findings into quantified financial risk
using Monte Carlo simulation. Essential for PE/M&A due diligence.

For each compliance gap detected:
1. Estimates probability of enforcement (based on historical data)
2. Models potential fine distribution (from framework-specific ranges)
3. Adds indirect costs (reputation, remediation, business interruption)
4. Runs 10,000 iterations to produce risk distributions

Output:
- Expected Loss (mean)
- VaR 95% and VaR 99%
- Cost of remediation vs cost of risk (ROI)
- Per-framework and per-violation breakdown

Usage:
    python -m tests.validation.monte_carlo --gaps gap_analysis_output.json --revenue 50000000
"""

import argparse
import json
import logging
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "reports"


# ─── Framework Fine Structures ─────────────────────────────────


@dataclass
class FineStructure:
    """Maximum fine structure for a regulatory framework."""

    framework: str
    max_percentage_turnover: float  # e.g., 0.04 for 4%
    max_absolute_eur: float  # e.g., 20_000_000
    typical_fine_range_pct: tuple[float, float] = (0.001, 0.02)  # typical range as % of turnover
    enforcement_probability_base: float = 0.15  # base probability of enforcement per year
    avg_time_to_enforcement_months: float = 18.0
    remediation_cost_multiplier: float = 0.1  # remediation typically 10% of max fine


FINE_STRUCTURES = {
    "GDPR": FineStructure(
        framework="GDPR",
        max_percentage_turnover=0.04,
        max_absolute_eur=20_000_000,
        typical_fine_range_pct=(0.0005, 0.025),
        enforcement_probability_base=0.20,
        avg_time_to_enforcement_months=14,
        remediation_cost_multiplier=0.08,
    ),
    "AI_ACT": FineStructure(
        framework="AI_ACT",
        max_percentage_turnover=0.07,
        max_absolute_eur=35_000_000,
        typical_fine_range_pct=(0.001, 0.04),
        enforcement_probability_base=0.10,
        avg_time_to_enforcement_months=24,
        remediation_cost_multiplier=0.15,
    ),
    "DORA": FineStructure(
        framework="DORA",
        max_percentage_turnover=0.01,
        max_absolute_eur=10_000_000,
        typical_fine_range_pct=(0.001, 0.008),
        enforcement_probability_base=0.25,
        avg_time_to_enforcement_months=12,
        remediation_cost_multiplier=0.12,
    ),
    "NIS2": FineStructure(
        framework="NIS2",
        max_percentage_turnover=0.02,
        max_absolute_eur=10_000_000,
        typical_fine_range_pct=(0.001, 0.015),
        enforcement_probability_base=0.18,
        avg_time_to_enforcement_months=15,
        remediation_cost_multiplier=0.10,
    ),
    "CSRD": FineStructure(
        framework="CSRD",
        max_percentage_turnover=0.005,
        max_absolute_eur=5_000_000,
        typical_fine_range_pct=(0.0005, 0.003),
        enforcement_probability_base=0.12,
        avg_time_to_enforcement_months=20,
        remediation_cost_multiplier=0.06,
    ),
    "EU_TAXONOMY": FineStructure(
        framework="EU_TAXONOMY",
        max_percentage_turnover=0.005,
        max_absolute_eur=5_000_000,
        typical_fine_range_pct=(0.0005, 0.003),
        enforcement_probability_base=0.10,
        avg_time_to_enforcement_months=22,
        remediation_cost_multiplier=0.05,
    ),
    "CSDDD": FineStructure(
        framework="CSDDD",
        max_percentage_turnover=0.05,
        max_absolute_eur=25_000_000,
        typical_fine_range_pct=(0.001, 0.03),
        enforcement_probability_base=0.08,
        avg_time_to_enforcement_months=24,
        remediation_cost_multiplier=0.10,
    ),
}


# ─── Severity Multipliers ─────────────────────────────────────

SEVERITY_MULTIPLIERS = {
    "critical": {
        "enforcement_boost": 1.8,  # 80% more likely to be enforced
        "fine_percentile": 0.75,  # top quartile of fine range
        "reputation_multiplier": 3.0,  # 3x reputation damage
    },
    "major": {
        "enforcement_boost": 1.3,
        "fine_percentile": 0.50,
        "reputation_multiplier": 2.0,
    },
    "minor": {
        "enforcement_boost": 0.8,
        "fine_percentile": 0.25,
        "reputation_multiplier": 1.2,
    },
    "informational": {
        "enforcement_boost": 0.3,
        "fine_percentile": 0.10,
        "reputation_multiplier": 1.0,
    },
}

# Sector-specific enforcement probability adjustments
SECTOR_ENFORCEMENT_ADJUSTMENTS = {
    "technology": 1.3,
    "finance": 1.5,
    "banking": 1.5,
    "insurance": 1.4,
    "healthcare": 1.4,
    "e-commerce": 1.2,
    "advertising": 1.6,
    "social_media": 1.8,
    "energy": 1.1,
    "retail": 1.0,
    "manufacturing": 0.9,
    "hr_services": 1.1,
    "marketing": 1.3,
}

# Country-specific enforcement intensity
COUNTRY_ENFORCEMENT_ADJUSTMENTS = {
    "IT": 1.2,  # Garante very active
    "FR": 1.4,  # CNIL very active
    "ES": 1.3,  # AEPD very active
    "DE": 1.1,  # Distributed enforcement
    "IE": 0.9,  # Historically slower
    "UK": 1.3,  # ICO active
    "NL": 1.2,  # AP active
    "EU": 1.0,  # baseline
}


# ─── Violation Risk Model ─────────────────────────────────────


@dataclass
class ViolationRisk:
    """Risk model for a single compliance violation."""

    framework: str
    article: str
    severity: str
    description: str

    # Calculated parameters
    enforcement_probability: float = 0.0
    fine_min_eur: float = 0.0
    fine_max_eur: float = 0.0
    fine_expected_eur: float = 0.0
    remediation_cost_eur: float = 0.0
    reputation_cost_multiplier: float = 1.0


@dataclass
class SimulationResult:
    """Result of Monte Carlo simulation for a company."""

    company_name: str
    revenue_eur: float
    sector: str
    country: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Input violations
    total_violations: int = 0
    violations_by_framework: dict = field(default_factory=dict)
    violations_by_severity: dict = field(default_factory=dict)

    # Simulation parameters
    n_iterations: int = 10000
    time_horizon_months: int = 24

    # Direct fine risk
    expected_fine: float = 0.0
    fine_var_95: float = 0.0
    fine_var_99: float = 0.0

    # Total risk (fines + indirect costs)
    expected_total_loss: float = 0.0
    total_var_95: float = 0.0
    total_var_99: float = 0.0

    # Remediation
    total_remediation_cost: float = 0.0
    remediation_roi: float = 0.0  # (avoided risk / remediation cost)

    # Per-framework breakdown
    framework_risks: dict = field(default_factory=dict)

    # Distribution data (for visualization)
    distribution_percentiles: dict = field(default_factory=dict)

    # Individual violation risks
    violation_details: list = field(default_factory=list)


# ─── Simulation Engine ─────────────────────────────────────────


class MonteCarloEngine:
    """
    Monte Carlo simulation engine for regulatory risk quantification.

    Takes NormaAI gap analysis output and produces financial risk estimates.
    """

    def __init__(
        self,
        n_iterations: int = 10_000,
        time_horizon_months: int = 24,
        seed: int = None,
    ):
        self.n_iterations = n_iterations
        self.time_horizon_months = time_horizon_months
        if seed is not None:
            random.seed(seed)

    def _calculate_enforcement_probability(
        self,
        base_prob: float,
        severity: str,
        sector: str,
        country: str,
        time_horizon_months: int,
        avg_enforcement_months: float,
    ) -> float:
        """
        Calculate probability of enforcement within time horizon.

        Uses a simplified Weibull-like model:
        P(enforcement by T) = 1 - exp(-(T/λ)^k)
        """
        # Base probability per year
        severity_mult = SEVERITY_MULTIPLIERS.get(severity, {}).get("enforcement_boost", 1.0)
        sector_mult = SECTOR_ENFORCEMENT_ADJUSTMENTS.get(sector, 1.0)
        country_mult = COUNTRY_ENFORCEMENT_ADJUSTMENTS.get(country, 1.0)

        adjusted_annual_prob = min(0.95, base_prob * severity_mult * sector_mult * country_mult)

        # Weibull CDF: P(T) = 1 - exp(-(T/lambda)^k)
        # lambda = avg_enforcement_months, k = shape parameter (1.5 = slightly increasing hazard)
        k = 1.5
        lambda_param = avg_enforcement_months
        t = time_horizon_months

        weibull_prob = 1 - math.exp(-((t / lambda_param) ** k))

        # Combine: adjusted base * temporal model
        return min(0.95, adjusted_annual_prob * weibull_prob)

    def _sample_fine(
        self,
        revenue: float,
        fine_structure: FineStructure,
        severity: str,
    ) -> float:
        """
        Sample a fine amount from a Beta distribution.

        Fine is bounded by [0, max(percentage_of_turnover, absolute_max)].
        Beta distribution is parameterized by severity.
        """
        max_fine_turnover = revenue * fine_structure.max_percentage_turnover
        max_fine = min(max_fine_turnover, fine_structure.max_absolute_eur)

        if max_fine <= 0:
            return 0.0

        # Beta distribution parameters based on severity
        severity_percentile = SEVERITY_MULTIPLIERS.get(severity, {}).get("fine_percentile", 0.5)

        # Beta(alpha, beta) where mean = alpha/(alpha+beta)
        # We want mean ≈ severity_percentile * typical_range
        typical_pct = fine_structure.typical_fine_range_pct[0] + severity_percentile * (
            fine_structure.typical_fine_range_pct[1] - fine_structure.typical_fine_range_pct[0]
        )
        typical_fine = revenue * typical_pct

        # Shape the distribution
        alpha = 2.0 + severity_percentile * 3
        beta_param = alpha * (max_fine / max(typical_fine, 1) - 1)
        beta_param = max(1.0, beta_param)

        sample = random.betavariate(alpha, beta_param)
        fine = sample * max_fine

        return max(0.0, fine)

    def _calculate_indirect_costs(self, fine: float, severity: str, sector: str) -> dict:
        """Calculate indirect costs associated with a regulatory fine."""
        rep_mult = SEVERITY_MULTIPLIERS.get(severity, {}).get("reputation_multiplier", 1.0)

        # Reputation damage (function of fine size and sector sensitivity)
        sector_sensitivity = {
            "finance": 2.5,
            "banking": 2.5,
            "healthcare": 2.0,
            "social_media": 3.0,
            "technology": 1.5,
            "retail": 1.0,
        }.get(sector, 1.5)
        reputation_cost = fine * rep_mult * sector_sensitivity * random.uniform(0.3, 0.8)

        # Legal fees (10-20% of fine, minimum €10K)
        legal_fees = max(10_000, fine * random.uniform(0.10, 0.20))

        # Business interruption (for operational frameworks like DORA/NIS2)
        business_interruption = 0.0
        if sector in ("banking", "finance", "insurance", "energy"):
            business_interruption = fine * random.uniform(0.5, 2.0)

        return {
            "reputation": reputation_cost,
            "legal_fees": legal_fees,
            "business_interruption": business_interruption,
            "total_indirect": reputation_cost + legal_fees + business_interruption,
        }

    def _build_violation_risks(
        self,
        violations: list[dict],
        revenue: float,
        sector: str,
        country: str,
    ) -> list[ViolationRisk]:
        """Build risk models for each violation."""
        risks = []

        for v in violations:
            framework = v.get("framework", "GDPR")
            fine_struct = FINE_STRUCTURES.get(framework, FINE_STRUCTURES["GDPR"])
            severity = v.get("severity", "major")

            enforcement_prob = self._calculate_enforcement_probability(
                base_prob=fine_struct.enforcement_probability_base,
                severity=severity,
                sector=sector,
                country=country,
                time_horizon_months=self.time_horizon_months,
                avg_enforcement_months=fine_struct.avg_time_to_enforcement_months,
            )

            max_fine = min(
                revenue * fine_struct.max_percentage_turnover,
                fine_struct.max_absolute_eur,
            )
            typical_fine = revenue * sum(fine_struct.typical_fine_range_pct) / 2
            remediation = max_fine * fine_struct.remediation_cost_multiplier

            risk = ViolationRisk(
                framework=framework,
                article=v.get("article", "unknown"),
                severity=severity,
                description=v.get("description", ""),
                enforcement_probability=enforcement_prob,
                fine_min_eur=0,
                fine_max_eur=max_fine,
                fine_expected_eur=typical_fine * enforcement_prob,
                remediation_cost_eur=remediation,
                reputation_cost_multiplier=SEVERITY_MULTIPLIERS.get(severity, {}).get(
                    "reputation_multiplier", 1.0
                ),
            )
            risks.append(risk)

        return risks

    def simulate(
        self,
        violations: list[dict],
        company_name: str = "Target Company",
        revenue_eur: float = 10_000_000,
        sector: str = "technology",
        country: str = "IT",
    ) -> SimulationResult:
        """
        Run Monte Carlo simulation for regulatory risk.

        Args:
            violations: List of violation dicts from NormaAI gap analysis
                Each should have: framework, article, severity, description
            company_name: Company name
            revenue_eur: Annual revenue in EUR
            sector: Industry sector
            country: Country code

        Returns:
            SimulationResult with risk distributions
        """
        result = SimulationResult(
            company_name=company_name,
            revenue_eur=revenue_eur,
            sector=sector,
            country=country,
            total_violations=len(violations),
            n_iterations=self.n_iterations,
            time_horizon_months=self.time_horizon_months,
        )

        if not violations:
            return result

        # Count by framework and severity
        for v in violations:
            fw = v.get("framework", "GDPR")
            sev = v.get("severity", "major")
            result.violations_by_framework[fw] = result.violations_by_framework.get(fw, 0) + 1
            result.violations_by_severity[sev] = result.violations_by_severity.get(sev, 0) + 1

        # Build risk models
        risks = self._build_violation_risks(violations, revenue_eur, sector, country)
        result.violation_details = [asdict(r) for r in risks]
        result.total_remediation_cost = sum(r.remediation_cost_eur for r in risks)

        # Run simulation
        fine_samples = []
        total_samples = []

        for _ in range(self.n_iterations):
            iteration_fine = 0.0
            iteration_indirect = 0.0

            for risk in risks:
                # Will enforcement happen?
                if random.random() < risk.enforcement_probability:
                    fine_struct = FINE_STRUCTURES.get(risk.framework, FINE_STRUCTURES["GDPR"])
                    fine = self._sample_fine(revenue_eur, fine_struct, risk.severity)
                    iteration_fine += fine

                    indirect = self._calculate_indirect_costs(fine, risk.severity, sector)
                    iteration_indirect += indirect["total_indirect"]

            fine_samples.append(iteration_fine)
            total_samples.append(iteration_fine + iteration_indirect)

        # Calculate statistics
        fine_samples.sort()
        total_samples.sort()

        result.expected_fine = sum(fine_samples) / len(fine_samples)
        result.fine_var_95 = fine_samples[int(0.95 * len(fine_samples))]
        result.fine_var_99 = fine_samples[int(0.99 * len(fine_samples))]

        result.expected_total_loss = sum(total_samples) / len(total_samples)
        result.total_var_95 = total_samples[int(0.95 * len(total_samples))]
        result.total_var_99 = total_samples[int(0.99 * len(total_samples))]

        # ROI of remediation
        if result.total_remediation_cost > 0:
            result.remediation_roi = result.expected_total_loss / result.total_remediation_cost
        else:
            result.remediation_roi = float("inf")

        # Percentile distribution
        percentiles = [5, 10, 25, 50, 75, 90, 95, 99]
        result.distribution_percentiles = {
            f"p{p}": total_samples[int(p / 100 * len(total_samples))] for p in percentiles
        }

        # Per-framework breakdown
        for fw in result.violations_by_framework:
            fw_violations = [v for v in violations if v.get("framework") == fw]
            fw_risks = [r for r in risks if r.framework == fw]
            result.framework_risks[fw] = {
                "violation_count": len(fw_violations),
                "expected_fine": sum(r.fine_expected_eur for r in fw_risks),
                "max_exposure": sum(r.fine_max_eur for r in fw_risks),
                "remediation_cost": sum(r.remediation_cost_eur for r in fw_risks),
            }

        return result


# ─── Report Generation ─────────────────────────────────────────


def format_eur(amount: float) -> str:
    """Format EUR amount with thousands separator."""
    if amount >= 1_000_000:
        return f"€{amount/1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"€{amount/1_000:.0f}K"
    else:
        return f"€{amount:.0f}"


def generate_risk_report(result: SimulationResult) -> str:
    """Generate a PE/M&A-ready risk report."""
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  NORMAAI - REGULATORY RISK QUANTIFICATION REPORT           ║",
        "║  Monte Carlo Simulation Analysis                            ║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Company:    {result.company_name:<46s}║",
        f"║  Revenue:    {format_eur(result.revenue_eur):<46s}║",
        f"║  Sector:     {result.sector:<46s}║",
        f"║  Country:    {result.country:<46s}║",
        f"║  Horizon:    {result.time_horizon_months} months{' ':<39s}║",
        f"║  Iterations: {result.n_iterations:,}{' ':<43s}║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  VIOLATIONS DETECTED: {result.total_violations:<37d}║",
    ]

    for fw, count in sorted(result.violations_by_framework.items()):
        lines.append(f"║    {fw:<12s}: {count:<41d}║")

    for sev, count in sorted(result.violations_by_severity.items()):
        lines.append(f"║    {sev:<12s}: {count:<41d}║")

    lines.extend(
        [
            "╠══════════════════════════════════════════════════════════════╣",
            "║  DIRECT FINE RISK                                           ║",
            f"║  Expected (mean):  {format_eur(result.expected_fine):<40s}║",
            f"║  VaR 95%:          {format_eur(result.fine_var_95):<40s}║",
            f"║  VaR 99%:          {format_eur(result.fine_var_99):<40s}║",
            "╠══════════════════════════════════════════════════════════════╣",
            "║  TOTAL RISK (fines + reputation + legal + interruption)     ║",
            f"║  Expected Loss:    {format_eur(result.expected_total_loss):<40s}║",
            f"║  VaR 95%:          {format_eur(result.total_var_95):<40s}║",
            f"║  VaR 99%:          {format_eur(result.total_var_99):<40s}║",
            "╠══════════════════════════════════════════════════════════════╣",
            "║  REMEDIATION ANALYSIS                                       ║",
            f"║  Remediation Cost: {format_eur(result.total_remediation_cost):<40s}║",
            f"║  ROI of Compliance: {result.remediation_roi:.1f}x{' ':<38s}║",
            f"║  (ogni €1 investito evita €{result.remediation_roi:.1f} di rischio)      ║",
        ]
    )

    if result.framework_risks:
        lines.extend(
            [
                "╠══════════════════════════════════════════════════════════════╣",
                "║  PER-FRAMEWORK RISK BREAKDOWN                              ║",
            ]
        )
        for fw, risk in sorted(result.framework_risks.items()):
            lines.append(
                f"║  {fw:<10s}: E[fine]={format_eur(risk['expected_fine']):<8s} "
                f"MaxExp={format_eur(risk['max_exposure']):<8s} "
                f"Fix={format_eur(risk['remediation_cost']):<8s}║"
            )

    if result.distribution_percentiles:
        lines.extend(
            [
                "╠══════════════════════════════════════════════════════════════╣",
                "║  RISK DISTRIBUTION                                         ║",
            ]
        )
        for p, val in result.distribution_percentiles.items():
            bar_len = min(30, int(val / max(result.total_var_99, 1) * 30))
            bar = "█" * bar_len
            lines.append(f"║  {p:>4s}: {format_eur(val):<12s} {bar:<30s}       ║")

    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


def save_risk_report(result: SimulationResult, filename: str = None) -> Path:
    """Save simulation result as JSON and text report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = filename or f"monte_carlo_{result.company_name.replace(' ', '_')}_{timestamp}"

    json_path = OUTPUT_DIR / f"{base}.json"
    json_path.write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    txt_path = OUTPUT_DIR / f"{base}.txt"
    txt_path.write_text(generate_risk_report(result), encoding="utf-8")

    return json_path


# ─── Integration with NormaAI Gap Analysis ────────────────────


def extract_violations_from_gap_analysis(gap_output: dict) -> list[dict]:
    """
    Extract violations from NormaAI gap analysis output.

    Compatible with NormaAI's gap_analyst output format.
    """
    violations = []

    requirements = gap_output.get("requirements", [])
    if not requirements:
        requirements = gap_output.get("gaps", [])
    if not requirements:
        requirements = gap_output.get("findings", [])

    for req in requirements:
        if not isinstance(req, dict):
            continue

        status = str(req.get("status", "")).upper()
        if status in ("NON_COMPLIANT", "PARTIALLY_COMPLIANT", "MISSING", "GAP", "NON-COMPLIANT"):
            violations.append(
                {
                    "framework": req.get("framework", gap_output.get("framework", "GDPR")),
                    "article": req.get("article", req.get("requirement_id", "unknown")),
                    "severity": req.get("severity", req.get("priority", "major")).lower(),
                    "description": req.get("description", req.get("finding", "")),
                }
            )

    return violations


def run_risk_analysis(
    gap_output: dict,
    company_name: str = "Target Company",
    revenue_eur: float = 10_000_000,
    sector: str = "technology",
    country: str = "IT",
    n_iterations: int = 10_000,
    time_horizon_months: int = 24,
) -> SimulationResult:
    """
    High-level function: Gap Analysis output → Risk Report.

    This is the main integration point between NormaAI and Monte Carlo.
    """
    violations = extract_violations_from_gap_analysis(gap_output)

    if not violations:
        logger.warning("No violations found in gap analysis output")
        return SimulationResult(
            company_name=company_name,
            revenue_eur=revenue_eur,
            sector=sector,
            country=country,
        )

    engine = MonteCarloEngine(
        n_iterations=n_iterations,
        time_horizon_months=time_horizon_months,
    )

    return engine.simulate(
        violations=violations,
        company_name=company_name,
        revenue_eur=revenue_eur,
        sector=sector,
        country=country,
    )


# ─── CLI ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="NormaAI Monte Carlo Risk Simulation")
    parser.add_argument("--gaps", help="Path to gap analysis JSON output")
    parser.add_argument("--company", default="Target Company", help="Company name")
    parser.add_argument("--revenue", type=float, default=10_000_000, help="Annual revenue EUR")
    parser.add_argument("--sector", default="technology", help="Industry sector")
    parser.add_argument("--country", default="IT", help="Country code")
    parser.add_argument("--iterations", type=int, default=10_000, help="Simulation iterations")
    parser.add_argument("--horizon", type=int, default=24, help="Time horizon in months")
    parser.add_argument("--demo", action="store_true", help="Run demo with sample violations")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.demo:
        # Demo with realistic violations
        demo_violations = [
            {
                "framework": "GDPR",
                "article": "Art. 13(2)(a)",
                "severity": "critical",
                "description": "Missing retention period",
            },
            {
                "framework": "GDPR",
                "article": "Art. 28(3)(h)",
                "severity": "critical",
                "description": "No audit rights in DPA",
            },
            {
                "framework": "GDPR",
                "article": "Art. 32",
                "severity": "major",
                "description": "Insufficient security measures",
            },
            {
                "framework": "DORA",
                "article": "Art. 6",
                "severity": "critical",
                "description": "No ICT risk framework",
            },
            {
                "framework": "DORA",
                "article": "Art. 30",
                "severity": "major",
                "description": "Missing vendor contract clauses",
            },
            {
                "framework": "NIS2",
                "article": "Art. 23",
                "severity": "critical",
                "description": "No incident reporting procedure",
            },
        ]

        engine = MonteCarloEngine(
            n_iterations=args.iterations,
            time_horizon_months=args.horizon,
            seed=42,
        )
        result = engine.simulate(
            violations=demo_violations,
            company_name=args.company,
            revenue_eur=args.revenue,
            sector=args.sector,
            country=args.country,
        )
    elif args.gaps:
        gap_data = json.loads(Path(args.gaps).read_text())
        result = run_risk_analysis(
            gap_output=gap_data,
            company_name=args.company,
            revenue_eur=args.revenue,
            sector=args.sector,
            country=args.country,
            n_iterations=args.iterations,
            time_horizon_months=args.horizon,
        )
    else:
        print("Provide --gaps <file> or --demo")
        return

    report = generate_risk_report(result)
    print(report)
    path = save_risk_report(result)
    print(f"\nReport saved to {path}")


if __name__ == "__main__":
    main()
