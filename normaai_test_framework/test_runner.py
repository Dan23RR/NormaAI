"""
NormaAI Validation Framework - Test Runner
=============================================
Esegue automaticamente tutti i test case contro gli endpoint NormaAI
e raccoglie i risultati per la confusion matrix.

Uso:
    python test_runner.py [--base-url http://localhost:8000] [--delay 5] [--output results.json]
"""

import argparse
import datetime
import json
import os
import re
import sys
import time

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    os.system(f"{sys.executable} -m pip install httpx --break-system-packages -q")
    import httpx

from synthetic_profiles import SYNTHETIC_PROFILES, get_all_test_cases

# ─── Result Classification ───────────────────────────

def classify_result(test_case, agent_response):
    """
    Classifica il risultato del test confrontando la risposta dell'agente
    con il gap atteso.

    Returns:
        dict con classification, match_score, matched_articles, analysis
    """
    if not agent_response or "error" in str(agent_response).lower():
        return {
            "classification": "ERROR",
            "match_score": 0.0,
            "matched_articles": [],
            "analysis": f"Agent returned error or empty response: {str(agent_response)[:200]}"
        }

    response_text = json.dumps(agent_response, ensure_ascii=False).lower()
    expected_gap = test_case["injected_gap"].lower()
    expected_article = test_case["expected_article"].lower()

    # Extract key terms from the injected gap
    gap_keywords = _extract_keywords(expected_gap)
    article_refs = _extract_article_refs(expected_article)

    # Score: how many key concepts from the gap were found
    keyword_hits = sum(1 for kw in gap_keywords if kw in response_text)
    keyword_score = keyword_hits / max(len(gap_keywords), 1)

    # Score: how many article references were found
    article_hits = [ref for ref in article_refs if ref in response_text]
    article_score = len(article_hits) / max(len(article_refs), 1)

    # Combined score (60% concept match, 40% article citation)
    combined_score = 0.6 * keyword_score + 0.4 * article_score

    # Classification
    if combined_score >= 0.5:
        classification = "TRUE_POSITIVE"
    elif combined_score >= 0.25:
        classification = "PARTIAL_MATCH"
    else:
        classification = "FALSE_NEGATIVE"

    return {
        "classification": classification,
        "match_score": round(combined_score, 3),
        "keyword_score": round(keyword_score, 3),
        "article_score": round(article_score, 3),
        "keyword_hits": f"{keyword_hits}/{len(gap_keywords)}",
        "matched_articles": article_hits,
        "analysis": (
            f"Gap keywords matched: {keyword_hits}/{len(gap_keywords)} | "
            f"Article refs matched: {len(article_hits)}/{len(article_refs)}"
        )
    }


def _extract_keywords(text):
    """Extract meaningful keywords from gap description."""
    stop_words = {
        "no", "not", "the", "a", "an", "is", "are", "was", "were", "for", "of",
        "in", "on", "to", "with", "without", "has", "have", "been", "its", "and",
        "or", "but", "by", "from", "that", "this", "which", "their", "does"
    }
    words = re.findall(r'[a-z]+', text.lower())
    return [w for w in words if len(w) > 3 and w not in stop_words]


def _extract_article_refs(text):
    """Extract article references like 'art. 7', 'art. 28(3)', 'esrs e1-6'."""
    refs = []
    # Match "art. X" patterns
    for m in re.finditer(r'art\.?\s*(\d+)', text.lower()):
        refs.append(f"art. {m.group(1)}")
        refs.append(f"article {m.group(1)}")
        refs.append(f"art.{m.group(1)}")
    # Match "ESRS XX-Y" patterns
    for m in re.finditer(r'esrs\s+([a-z]\d+-\d+)', text.lower()):
        refs.append(f"esrs {m.group(1)}")
        refs.append(m.group(1))
    return refs


# ─── API Calls ────────────────────────────────────────

def _is_rate_limited(response_data):
    """Check if the API response indicates rate limiting."""
    if isinstance(response_data, dict):
        data = response_data.get("data", response_data)
        if isinstance(data, dict):
            error_msg = str(data.get("error", "")).lower()
            if "rate limit" in error_msg or "rate_limit" in error_msg or "quota" in error_msg:
                return True
    return False


def run_gap_analysis(client, base_url, profile, framework, timeout=180, max_retries=5):
    """Call the NormaAI gap-analysis endpoint with retry on rate limit."""
    payload = {
        "framework": framework,
        "company_profile": {
            "name": profile["company_name"],
            "sector": profile["sector"],
            "employees": profile["employees"],
            "jurisdictions": profile["jurisdictions"],
            "description": profile["description"]
        }
    }

    for attempt in range(max_retries):
        try:
            resp = client.post(
                f"{base_url}/api/v1/gap-analysis",
                json=payload,
                timeout=timeout
            )
            resp.raise_for_status()
            result = resp.json()

            # Check for rate limit in successful response
            if _is_rate_limited(result):
                wait = min(30 * (2 ** attempt), 120)  # 30s, 60s, 120s, 120s...
                print(f"       Rate limited (attempt {attempt+1}/{max_retries}). "
                      f"Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            return result

        except httpx.TimeoutException:
            return {"error": "TIMEOUT", "detail": f"Request timed out after {timeout}s"}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = min(30 * (2 ** attempt), 120)
                print(f"       HTTP 429 Rate Limited (attempt {attempt+1}/{max_retries}). "
                      f"Waiting {wait}s...")
                time.sleep(wait)
                continue
            return {"error": f"HTTP_{e.response.status_code}", "detail": str(e)}
        except Exception as e:
            return {"error": type(e).__name__, "detail": str(e)}

    return {"error": "RATE_LIMIT_EXHAUSTED",
            "detail": f"Still rate limited after {max_retries} retries"}


def run_qa_query(client, base_url, question, framework=None, company_profile=None, timeout=180, max_retries=5):
    """Call the NormaAI Q&A endpoint with retry on rate limit."""
    payload = {"question": question}
    if framework:
        payload["framework"] = framework
    if company_profile:
        payload["company_profile"] = company_profile

    for attempt in range(max_retries):
        try:
            resp = client.post(
                f"{base_url}/api/v1/qa",
                json=payload,
                timeout=timeout
            )
            resp.raise_for_status()
            result = resp.json()

            if _is_rate_limited(result):
                wait = min(30 * (2 ** attempt), 120)
                print(f"       Rate limited (attempt {attempt+1}/{max_retries}). "
                      f"Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            return result

        except httpx.TimeoutException:
            return {"error": "TIMEOUT", "detail": f"Request timed out after {timeout}s"}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = min(30 * (2 ** attempt), 120)
                print(f"       HTTP 429 (attempt {attempt+1}/{max_retries}). Waiting {wait}s...")
                time.sleep(wait)
                continue
            return {"error": f"HTTP_{e.response.status_code}", "detail": str(e)}
        except Exception as e:
            return {"error": type(e).__name__, "detail": str(e)}

    return {"error": "RATE_LIMIT_EXHAUSTED",
            "detail": f"Still rate limited after {max_retries} retries"}


# ─── Main Test Execution ─────────────────────────────

def run_all_tests(base_url, delay_between_tests=5, timeout=120):
    """Execute all test cases and collect results."""
    results = {
        "metadata": {
            "run_date": datetime.datetime.now().isoformat(),
            "base_url": base_url,
            "normaai_version": "0.3.0",
            "total_profiles": len(SYNTHETIC_PROFILES),
            "total_test_cases": len(get_all_test_cases()),
        },
        "test_results": [],
        "summary": {}
    }

    client = httpx.Client()
    all_cases = get_all_test_cases()
    total = len(all_cases)

    # Group test cases by (profile, framework) for efficient API calls
    profile_framework_groups = {}
    for tc in all_cases:
        key = (tc["profile_id"], tc["framework"])
        if key not in profile_framework_groups:
            profile_framework_groups[key] = []
        profile_framework_groups[key].append(tc)

    test_num = 0
    for (profile_id, framework), cases in profile_framework_groups.items():
        profile = next(p for p in SYNTHETIC_PROFILES if p["id"] == profile_id)
        print(f"\n{'='*60}")
        print(f"PROFILE: {profile['company_name']} | FRAMEWORK: {framework}")
        print(f"{'='*60}")

        # Run gap analysis for this profile+framework
        print("  Calling gap-analysis endpoint...")
        start_time = time.time()
        api_response = run_gap_analysis(client, base_url, profile, framework, timeout)
        elapsed = round(time.time() - start_time, 2)
        print(f"  Response received in {elapsed}s")

        # Evaluate each test case against the response
        for tc in cases:
            test_num += 1
            print(f"\n  [{test_num}/{total}] Test {tc['test_id']}: {tc['injected_gap'][:60]}...")

            classification = classify_result(tc, api_response)

            result_entry = {
                "test_id": tc["test_id"],
                "profile_id": tc["profile_id"],
                "company_name": tc["company_name"],
                "framework": tc["framework"],
                "injected_gap": tc["injected_gap"],
                "expected_article": tc["expected_article"],
                "expected_severity": tc["severity"],
                "difficulty": tc["difficulty"],
                "classification": classification["classification"],
                "match_score": classification["match_score"],
                "keyword_score": classification.get("keyword_score", 0),
                "article_score": classification.get("article_score", 0),
                "matched_articles": classification["matched_articles"],
                "analysis": classification["analysis"],
                "api_response_time_s": elapsed,
                "api_response_preview": str(api_response)[:500],
            }
            results["test_results"].append(result_entry)

            # Print result
            symbol = {
                "TRUE_POSITIVE": "\u2705",
                "PARTIAL_MATCH": "\U0001F7E1",
                "FALSE_NEGATIVE": "\u274C",
                "ERROR": "\u26A0\uFE0F"
            }.get(classification["classification"], "?")
            print(f"       {symbol} {classification['classification']} "
                  f"(score: {classification['match_score']}) - {classification['analysis']}")

        # Delay between API calls to avoid rate limiting
        if delay_between_tests > 0:
            print(f"\n  Waiting {delay_between_tests}s before next call (rate limit)...")
            time.sleep(delay_between_tests)

    client.close()

    # ─── Summary Statistics ───────────────────────
    classifications = [r["classification"] for r in results["test_results"]]
    results["summary"] = {
        "total_tests": total,
        "true_positives": classifications.count("TRUE_POSITIVE"),
        "partial_matches": classifications.count("PARTIAL_MATCH"),
        "false_negatives": classifications.count("FALSE_NEGATIVE"),
        "errors": classifications.count("ERROR"),
        "detection_rate": round(
            (classifications.count("TRUE_POSITIVE") + 0.5 * classifications.count("PARTIAL_MATCH"))
            / max(total, 1) * 100, 1
        ),
        "avg_match_score": round(
            sum(r["match_score"] for r in results["test_results"]) / max(total, 1), 3
        ),
        "by_framework": {},
        "by_difficulty": {},
    }

    # Per-framework breakdown
    for fw in sorted(set(r["framework"] for r in results["test_results"])):
        fw_results = [r for r in results["test_results"] if r["framework"] == fw]
        fw_tp = sum(1 for r in fw_results if r["classification"] == "TRUE_POSITIVE")
        fw_total = len(fw_results)
        results["summary"]["by_framework"][fw] = {
            "total": fw_total,
            "true_positives": fw_tp,
            "detection_rate": round(fw_tp / max(fw_total, 1) * 100, 1)
        }

    # Per-difficulty breakdown
    for diff in ["EASY", "MEDIUM", "HARD"]:
        diff_results = [r for r in results["test_results"] if r["difficulty"] == diff]
        diff_tp = sum(1 for r in diff_results if r["classification"] == "TRUE_POSITIVE")
        diff_total = len(diff_results)
        results["summary"]["by_difficulty"][diff] = {
            "total": diff_total,
            "true_positives": diff_tp,
            "detection_rate": round(diff_tp / max(diff_total, 1) * 100, 1)
        }

    return results


def print_summary(results):
    """Print a formatted summary of test results."""
    s = results["summary"]
    print("\n" + "=" * 60)
    print("NORMAAI VALIDATION RESULTS")
    print("=" * 60)
    print(f"  Total Tests:      {s['total_tests']}")
    print(f"  True Positives:   {s['true_positives']}  \u2705")
    print(f"  Partial Matches:  {s['partial_matches']}  \U0001F7E1")
    print(f"  False Negatives:  {s['false_negatives']}  \u274C")
    print(f"  Errors:           {s['errors']}  \u26A0\uFE0F")
    print(f"  Detection Rate:   {s['detection_rate']}%")
    print(f"  Avg Match Score:  {s['avg_match_score']}")
    print()
    print("  Per Framework:")
    for fw, data in s["by_framework"].items():
        print(f"    {fw:12s}  {data['true_positives']}/{data['total']} ({data['detection_rate']}%)")
    print()
    print("  Per Difficulty:")
    for diff, data in s["by_difficulty"].items():
        print(f"    {diff:8s}  {data['true_positives']}/{data['total']} ({data['detection_rate']}%)")


# ─── Entry Point ──────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NormaAI Validation Test Runner")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="NormaAI API base URL")
    parser.add_argument("--delay", type=int, default=30,
                        help="Delay between API calls in seconds (rate limit, default 30s for free tier)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Request timeout in seconds")
    parser.add_argument("--output", default="test_results.json",
                        help="Output file for results JSON")
    parser.add_argument("--profile", default=None,
                        help="Run only a specific profile (e.g., SYNTH-A, SYNTH-E)")
    parser.add_argument("--retries", type=int, default=5,
                        help="Max retries per API call on rate limit")
    args = parser.parse_args()

    print("=" * 60)
    print("NormaAI Validation Framework - Test Runner v1.0")
    print("=" * 60)
    print(f"  Target:  {args.base_url}")
    print(f"  Delay:   {args.delay}s between calls")
    print(f"  Timeout: {args.timeout}s per request")
    print(f"  Output:  {args.output}")

    # Quick health check
    try:
        r = httpx.get(f"{args.base_url}/health", timeout=10)
        print(f"  Health:  {r.status_code} OK")
    except Exception as e:
        print(f"  Health:  FAILED - {e}")
        print("\n  \u26A0\uFE0F  NormaAI API non raggiungibile. Assicurati che sia in esecuzione.")
        sys.exit(1)

    # Filter profiles if --profile specified
    if args.profile:
        from synthetic_profiles import get_profile_by_id
        p = get_profile_by_id(args.profile.upper())
        if not p:
            print(f"\n  Profile '{args.profile}' not found. Available: SYNTH-A .. SYNTH-E")
            sys.exit(1)
        import synthetic_profiles
        original = synthetic_profiles.SYNTHETIC_PROFILES
        synthetic_profiles.SYNTHETIC_PROFILES = [p]
        print(f"  Profile: {args.profile.upper()} only ({len(p['test_cases'])} test cases)")

    results = run_all_tests(args.base_url, args.delay, args.timeout)
    print_summary(results)

    # Save results
    output_path = os.path.join(os.path.dirname(__file__), args.output)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Risultati salvati in: {output_path}")
