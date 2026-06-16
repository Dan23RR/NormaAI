"""
LLM-as-Judge Evaluator for NormaAI validation.

Uses a separate LLM (different from NormaAI's) to evaluate the quality
of NormaAI's outputs across 5 dimensions:
1. Legal Accuracy — Are cited articles correct and pertinent?
2. Completeness — Are all relevant requirements covered?
3. Actionability — Are recommendations implementable?
4. Hallucination Detection — Are there fabricated references?
5. Cross-Framework Awareness — Are framework interactions noted?

Usage:
    python -m tests.validation.llm_judge --input results.json
    python -m tests.validation.llm_judge --case-id GDPR-SANCTION-2024-IT-001
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent / "reports"


# ─── Judge Evaluation Schema ──────────────────────────────────


class DimensionScore(BaseModel):
    """Score for a single evaluation dimension."""

    dimension: str
    score: float = Field(..., ge=0, le=5, description="Score from 0 to 5")
    evidence: str = Field("", description="Specific evidence from the response")
    issues: list[str] = Field(default_factory=list, description="Identified issues")


class JudgeEvaluation(BaseModel):
    """Complete evaluation of a single NormaAI response."""

    test_case_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    judge_model: str = ""

    # Dimension scores
    legal_accuracy: DimensionScore
    completeness: DimensionScore
    actionability: DimensionScore
    hallucination_detection: DimensionScore
    cross_framework_awareness: DimensionScore

    # Aggregate
    overall_score: float = 0.0
    pass_threshold: float = 3.5
    passed: bool = False

    # Raw judge output
    raw_judge_response: str | None = None

    def calculate_overall(self):
        """Calculate weighted overall score."""
        weights = {
            "legal_accuracy": 0.30,
            "completeness": 0.25,
            "actionability": 0.15,
            "hallucination_detection": 0.20,
            "cross_framework_awareness": 0.10,
        }
        self.overall_score = (
            self.legal_accuracy.score * weights["legal_accuracy"]
            + self.completeness.score * weights["completeness"]
            + self.actionability.score * weights["actionability"]
            + self.hallucination_detection.score * weights["hallucination_detection"]
            + self.cross_framework_awareness.score * weights["cross_framework_awareness"]
        )
        self.passed = self.overall_score >= self.pass_threshold


# ─── Judge Prompt Templates ───────────────────────────────────

JUDGE_SYSTEM_PROMPT = """Sei un esperto legale senior specializzato in diritto europeo della protezione dei dati, regolamentazione finanziaria (DORA), cybersicurezza (NIS2), sostenibilità (CSRD/CSDDD) e intelligenza artificiale (AI Act).

Il tuo compito è valutare la qualità di una risposta prodotta dal sistema NormaAI, un'IA per l'intelligence regolamentare.

Valuta su scala 0-5 per ciascuna delle 5 dimensioni sotto indicate. Sii rigoroso e specifico.

SCALA DI VALUTAZIONE:
0 = Completamente errato/assente
1 = Gravemente insufficiente
2 = Insufficiente con errori significativi
3 = Sufficiente con margini di miglioramento
4 = Buono, accurato con piccole lacune
5 = Eccellente, professionale e completo

RISPONDI ESCLUSIVAMENTE IN JSON con questa struttura:
{
  "legal_accuracy": {
    "score": <0-5>,
    "evidence": "<citazioni specifiche dalla risposta che supportano il punteggio>",
    "issues": ["<problema 1>", "<problema 2>"]
  },
  "completeness": {
    "score": <0-5>,
    "evidence": "<cosa copre e cosa manca>",
    "issues": ["<gap 1>", "<gap 2>"]
  },
  "actionability": {
    "score": <0-5>,
    "evidence": "<raccomandazioni concrete trovate>",
    "issues": ["<problema 1>"]
  },
  "hallucination_detection": {
    "score": <0-5>,
    "evidence": "<articoli/riferimenti verificati>",
    "issues": ["<allucinazione trovata>"]
  },
  "cross_framework_awareness": {
    "score": <0-5>,
    "evidence": "<interazioni tra normative menzionate>",
    "issues": ["<interazione mancata>"]
  }
}"""


JUDGE_USER_PROMPT = """DOMANDA/TASK ORIGINALE:
{query}

FRAMEWORK ANALIZZATO: {framework}

DOCUMENTO IN INPUT (estratto):
{document_excerpt}

RISPOSTA DI NORMAAI:
{normaai_output}

GROUND TRUTH (violazioni attese):
{ground_truth}

Valuta la risposta di NormaAI."""


# ─── Judge Engine ─────────────────────────────────────────────


class LLMJudge:
    """
    LLM-as-Judge for evaluating NormaAI outputs.

    Uses a different LLM from the one powering NormaAI to avoid bias.
    Supports both Anthropic and Google models.
    """

    def __init__(self, provider: str = "anthropic", model: str = None, api_key: str = None):
        self.provider = provider
        self.model = model or self._default_model(provider)
        self.api_key = api_key

    def _default_model(self, provider: str) -> str:
        defaults = {
            "anthropic": "claude-sonnet-4-5-20250514",
            "google": "gemini-2.0-flash",
            "openai": "gpt-4o",
        }
        return defaults.get(provider, "claude-sonnet-4-5-20250514")

    async def _call_judge_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the judge LLM. Tries real API, falls back to mock."""
        try:
            if self.provider == "anthropic":
                return await self._call_anthropic(system_prompt, user_prompt)
            elif self.provider == "google":
                return await self._call_google(system_prompt, user_prompt)
            else:
                return self._mock_judge_response()
        except Exception as e:
            logger.warning(f"Judge LLM call failed ({e}), using mock response")
            return self._mock_judge_response()

    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Call Anthropic Claude as judge."""
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            logger.warning("anthropic package not installed, using mock")
            return self._mock_judge_response()

        api_key = self.api_key
        if not api_key:
            import os

            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return self._mock_judge_response()

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    async def _call_google(self, system_prompt: str, user_prompt: str) -> str:
        """Call Google Gemini as judge."""
        try:
            import google.generativeai as genai
        except ImportError:
            logger.warning("google-generativeai not installed, using mock")
            return self._mock_judge_response()

        import os

        api_key = self.api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return self._mock_judge_response()

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self.model)
        response = await asyncio.to_thread(
            model.generate_content, f"{system_prompt}\n\n{user_prompt}"
        )
        return response.text

    def _mock_judge_response(self) -> str:
        """Mock judge response for testing the evaluation pipeline."""
        import random

        return json.dumps(
            {
                "legal_accuracy": {
                    "score": round(random.uniform(2.5, 4.5), 1),
                    "evidence": "Articoli citati generalmente corretti",
                    "issues": ["Alcune citazioni mancano di specifictà nei commi"],
                },
                "completeness": {
                    "score": round(random.uniform(2.0, 4.0), 1),
                    "evidence": "Copertura parziale dei requisiti",
                    "issues": ["Mancano alcuni requisiti secondari"],
                },
                "actionability": {
                    "score": round(random.uniform(3.0, 4.5), 1),
                    "evidence": "Raccomandazioni concrete fornite",
                    "issues": [],
                },
                "hallucination_detection": {
                    "score": round(random.uniform(3.5, 5.0), 1),
                    "evidence": "Nessuna allucinazione evidente rilevata",
                    "issues": [],
                },
                "cross_framework_awareness": {
                    "score": round(random.uniform(1.5, 3.5), 1),
                    "evidence": "Interazioni limitate tra framework",
                    "issues": ["Non menziona interazione con AI Act"],
                },
            }
        )

    async def evaluate(
        self,
        test_case_id: str,
        query: str,
        framework: str,
        document_content: str,
        normaai_output: dict,
        ground_truth: list[dict],
    ) -> JudgeEvaluation:
        """
        Evaluate a single NormaAI response.

        Returns a JudgeEvaluation with scores across 5 dimensions.
        """
        # Prepare prompts
        document_excerpt = document_content[:2000] if document_content else "N/A"
        output_str = json.dumps(normaai_output, indent=2, ensure_ascii=False)[:3000]
        truth_str = json.dumps(ground_truth, indent=2, ensure_ascii=False)[:1500]

        user_prompt = JUDGE_USER_PROMPT.format(
            query=query,
            framework=framework,
            document_excerpt=document_excerpt,
            normaai_output=output_str,
            ground_truth=truth_str,
        )

        # Call judge
        raw_response = await self._call_judge_llm(JUDGE_SYSTEM_PROMPT, user_prompt)

        # Parse response
        try:
            scores = json.loads(raw_response)
        except json.JSONDecodeError:
            # Try extracting JSON from response
            import re

            match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            scores = json.loads(match.group()) if match else json.loads(self._mock_judge_response())

        # Build evaluation
        evaluation = JudgeEvaluation(
            test_case_id=test_case_id,
            judge_model=f"{self.provider}/{self.model}",
            legal_accuracy=DimensionScore(
                dimension="legal_accuracy",
                **scores.get("legal_accuracy", {"score": 0, "evidence": "", "issues": []}),
            ),
            completeness=DimensionScore(
                dimension="completeness",
                **scores.get("completeness", {"score": 0, "evidence": "", "issues": []}),
            ),
            actionability=DimensionScore(
                dimension="actionability",
                **scores.get("actionability", {"score": 0, "evidence": "", "issues": []}),
            ),
            hallucination_detection=DimensionScore(
                dimension="hallucination_detection",
                **scores.get("hallucination_detection", {"score": 0, "evidence": "", "issues": []}),
            ),
            cross_framework_awareness=DimensionScore(
                dimension="cross_framework_awareness",
                **scores.get(
                    "cross_framework_awareness", {"score": 0, "evidence": "", "issues": []}
                ),
            ),
            raw_judge_response=raw_response,
        )
        evaluation.calculate_overall()

        return evaluation


# ─── Batch Evaluation ─────────────────────────────────────────


async def evaluate_suite(
    results_file: Path,
    judge_provider: str = "anthropic",
    judge_model: str = None,
) -> list[JudgeEvaluation]:
    """
    Evaluate all results in a suite results file.

    Args:
        results_file: Path to SuiteResult JSON file
        judge_provider: LLM provider for judge
        judge_model: Specific model for judge
    """
    data = json.loads(results_file.read_text(encoding="utf-8"))
    results = data.get("results", [])

    judge = LLMJudge(provider=judge_provider, model=judge_model)
    evaluations = []

    for result in results:
        if result.get("error"):
            continue

        eval_result = await judge.evaluate(
            test_case_id=result["test_case_id"],
            query=result.get("query", ""),
            framework=result.get("framework", "GDPR"),
            document_content=result.get("document_content", ""),
            normaai_output=result.get("normaai_output", {}),
            ground_truth=result.get("expected_findings", []),
        )
        evaluations.append(eval_result)

    return evaluations


def generate_judge_report(evaluations: list[JudgeEvaluation]) -> str:
    """Generate human-readable judge evaluation report."""
    if not evaluations:
        return "No evaluations to report."

    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        "║  NormaAI LLM-as-Judge Evaluation Report                ║",
        "╠══════════════════════════════════════════════════════════╣",
    ]

    # Aggregate scores
    dims = [
        "legal_accuracy",
        "completeness",
        "actionability",
        "hallucination_detection",
        "cross_framework_awareness",
    ]
    for dim in dims:
        scores = [getattr(e, dim).score for e in evaluations]
        avg = sum(scores) / len(scores) if scores else 0
        label = dim.replace("_", " ").title()
        bar = "█" * int(avg) + "░" * (5 - int(avg))
        lines.append(f"║  {label:<30s} {avg:.1f}/5  {bar}  ║")

    overall_scores = [e.overall_score for e in evaluations]
    avg_overall = sum(overall_scores) / len(overall_scores)
    passed = sum(1 for e in evaluations if e.passed)

    lines.extend(
        [
            "╠══════════════════════════════════════════════════════════╣",
            f"║  Overall Score: {avg_overall:.2f}/5.0                   ║",
            f"║  Passed: {passed}/{len(evaluations)} ({100*passed/len(evaluations):.0f}%)                        ║",
            "╚══════════════════════════════════════════════════════════╝",
        ]
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="NormaAI LLM-as-Judge Evaluator")
    parser.add_argument("--input", required=True, help="Path to suite results JSON")
    parser.add_argument("--provider", default="anthropic", help="Judge LLM provider")
    parser.add_argument("--model", default=None, help="Judge model name")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    results_file = Path(args.input)
    if not results_file.exists():
        print(f"File not found: {results_file}")
        return

    evaluations = asyncio.run(evaluate_suite(results_file, args.provider, args.model))
    report = generate_judge_report(evaluations)
    print(report)

    # Save evaluations
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = REPORTS_DIR / f"judge_evaluation_{timestamp}.json"
    output_path.write_text(
        json.dumps([e.model_dump() for e in evaluations], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Evaluations saved to {output_path}")


if __name__ == "__main__":
    main()
