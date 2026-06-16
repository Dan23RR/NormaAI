"""Real-LLM smoke test via OpenRouter free models.

Runs the NormaAI gap-analyst system prompt against live models with two
regulatory canary questions whose ground truth we control (ADR-003), and
checks JSON contract + factual dates. Costs nothing (free-tier models).

Usage:  python scripts/smoke_openrouter.py [model_id ...]
"""
import os
import sys
import time
from pathlib import Path

# Allow running from anywhere: repo root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows console defaults to cp1252; model output may contain U+202F etc.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["LLM_PROVIDER"] = "openrouter"

DEFAULT_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

SYSTEM = (
    "You are NormaAI, an EU regulatory compliance assistant.\n"
    "IMPORTANT CONTEXT:\n"
    "- Post-Omnibus I (Directive (EU) 2026/470, in force 18 March 2026): "
    "CSRD scope narrowed to 1,000+ employees AND EUR 450M turnover (cumulative)\n"
    "- CSDDD transposition deadline: 26 July 2028, first compliance: 26 July 2029\n"
    'Respond ONLY with valid JSON: {"answer": "...", "confidence_score": 0.0-1.0}'
)

CANARIES = [
    {
        "q": "What is the CSDDD national transposition deadline after the Omnibus I package? Answer in one sentence.",
        "must_contain": ["2028"],
        "must_not": ["July 2027"],
    },
    {
        "q": "A company with 800 employees and EUR 50M turnover: is it in mandatory CSRD scope post-Omnibus? One sentence.",
        "must_contain": ["1,000", "1000"],  # any of these counts as pass
        "must_not": [],
    },
]


def main() -> int:
    models = sys.argv[1:] or DEFAULT_MODELS
    failures = 0

    for model in models:
        os.environ["OPENROUTER_MODEL_ANALYSIS"] = model
        # Reset the settings cache so the model override is picked up.
        from src.config import get_settings

        get_settings.cache_clear()
        from src.agents.llm import call_llm

        print(f"\n=== {model} ===")
        for c in CANARIES:
            t0 = time.time()
            result = call_llm(SYSTEM, c["q"])
            dt = time.time() - t0

            if "error" in result:
                print(f"  [FAIL] error after {dt:.1f}s: {result['error'][:140]}")
                failures += 1
                continue

            answer = str(result.get("answer", ""))
            conf = result.get("confidence_score", "n/a")
            ok_contain = any(tok in answer for tok in c["must_contain"])
            ok_not = all(tok not in answer for tok in c["must_not"])
            status = "PASS" if (ok_contain and ok_not) else "FAIL"
            if status == "FAIL":
                failures += 1
            print(f"  [{status}] {dt:.1f}s conf={conf} :: {answer[:160]}")

    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
