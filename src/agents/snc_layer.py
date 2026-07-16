"""SNC Governance Layer - Behavioral Trust Clustering applied to NormaAI.

Wraps the existing acall_llm() pipeline with K-sample stochastic generation
and applies the closed-form trust thermodynamic governor.

Sits between agent nodes (monitor/gap/qa) and the existing confidence_check
gate. Composition with CoVe:
    SNC catches stochastic uncertainty (sample diversity).
    CoVe catches factual claim errors (evidence-based verification).
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass

from src.agents.llm import acall_llm, extract_confidence

logger = logging.getLogger(__name__)


# ----- Configuration -----


@dataclass(frozen=True)
class SNCConfig:
    k: int = 3
    temperature: float = 0.7
    theta_high: float = 0.85
    theta_low: float = 0.50
    enabled: bool = True
    # Consensus floor: the modal answer must be corroborated by at least this many
    # samples, else abstain regardless of the numeric trust. Guards K divergent
    # high-confidence answers (each self-graded ~0.95) that can otherwise clear
    # theta_low on entropy alone. Default 2 = "at least one other sample agrees".
    min_modal_agreement: int = 2
    # Retrieval support gate: if the best retrieved dense (cosine) score is below
    # this, the evidence is weak -> flag the served answer for review and cap its
    # confidence. Fires only when dense scores are present (conservative). 0 disables.
    weak_evidence_dense_score: float = 0.25


# ----- Normalization helpers -----

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    text = _PUNCT_RE.sub(" ", text.lower())
    text = _WS_RE.sub(" ", text).strip()
    return text[:500]


def _normalize_citations(citations: list) -> tuple:
    keys = set()
    for c in citations or []:
        if not isinstance(c, dict):
            keys.add(_normalize_text(str(c))[:80])
            continue
        urn = c.get("urn") or c.get("URN")
        celex = c.get("celex") or c.get("CELEX")
        if urn:
            keys.add(f"urn:{urn}")
        elif celex:
            keys.add(f"celex:{celex}")
        else:
            framework = c.get("framework", "?")
            article = c.get("article_number") or c.get("article") or "?"
            keys.add(f"{framework}:{article}")
    return tuple(sorted(keys))


def behavior_key(parsed: dict) -> tuple:
    """Cluster key: citations are the primary identity in the regulatory domain."""
    if not isinstance(parsed, dict):
        return ("txt", tuple(sorted(_normalize_text(str(parsed)).split())))
    answer = parsed.get("answer") or parsed.get("revised_response") or ""
    citations = parsed.get("citations") or []
    citation_key = _normalize_citations(citations)
    if citation_key:
        return ("cit", citation_key)
    tokens = tuple(sorted(_normalize_text(answer).split()))
    return ("txt", tokens)


# ----- Trust thermodynamics -----


def _shannon_entropy_normalized(cluster_sizes: list) -> float:
    n_clusters = len(cluster_sizes)
    if n_clusters <= 1:
        return 0.0
    total = sum(cluster_sizes)
    if total <= 0:
        return 0.0
    H = -sum((c / total) * math.log(c / total) for c in cluster_sizes if c > 0)
    H_max = math.log(n_clusters)
    if H_max <= 0:
        return 0.0
    return max(0.0, H / H_max)


def trust_thermodynamic(ppv: float, sigma_calib: float, t_comp: float | None = None) -> float:
    ppv = max(0.0, min(1.0, ppv))
    sigma_calib = max(0.0, min(1.0, sigma_calib))
    if t_comp is None:
        t_comp = 0.5 + (1.0 - ppv)
    return ppv * math.exp(-sigma_calib * t_comp)


# ----- Decision dataclass -----


@dataclass(frozen=True)
class SNCDecision:
    action: str
    trust: float
    ppv: float
    sigma_calib: float
    t_comp: float
    n_clusters: int
    modal_answer: dict
    samples: list


# ----- Main async entry point -----


async def snc_governance(
    initial_response: dict,
    system_prompt: str,
    user_message: str,
    config: SNCConfig | None = None,
) -> SNCDecision:
    cfg = config or SNCConfig()
    if not cfg.enabled or cfg.k < 2:
        ppv = extract_confidence(initial_response)
        if ppv >= cfg.theta_high:
            action = "ADMIT_HIGH"
        elif ppv >= cfg.theta_low:
            action = "ADMIT_MID"
        else:
            action = "ABSTAIN"
        return SNCDecision(
            action=action,
            trust=ppv,
            ppv=ppv,
            sigma_calib=0.0,
            t_comp=0.5,
            n_clusters=1,
            modal_answer=initial_response,
            samples=[initial_response],
        )

    n_extra = cfg.k - 1
    # Resample at the configured SNC temperature (NOT the global 0.0) so the K
    # samples actually differ - otherwise entropy is always 0 and the trust
    # score collapses to the model's self-declared confidence (BUG-001).
    extra_tasks = [
        acall_llm(system_prompt, user_message, temperature=cfg.temperature) for _ in range(n_extra)
    ]
    try:
        extra_samples = await asyncio.gather(*extra_tasks, return_exceptions=True)
    except Exception as e:
        logger.error("snc_extra_samples_failed", extra={"error": str(e)})
        extra_samples = []

    valid_extras = [s for s in extra_samples if isinstance(s, dict) and "error" not in s]
    samples = [initial_response] + valid_extras

    if len(samples) < 2:
        ppv = extract_confidence(initial_response)
        logger.warning(
            "snc_degraded_mode",
            extra={
                "valid_samples": len(samples),
                "expected": cfg.k,
            },
        )
        return SNCDecision(
            action="ABSTAIN",
            trust=ppv * 0.5,
            ppv=ppv,
            sigma_calib=1.0,
            t_comp=1.0,
            n_clusters=1,
            modal_answer=initial_response,
            samples=samples,
        )

    ppv = sum(extract_confidence(s) for s in samples) / len(samples)

    keys = [behavior_key(s) for s in samples]
    cluster_sizes = {}
    for i, k in enumerate(keys):
        cluster_sizes.setdefault(k, []).append(i)

    sizes = [len(v) for v in cluster_sizes.values()]
    sigma_calib = _shannon_entropy_normalized(sizes)
    t_comp = 0.5 + (1.0 - ppv)
    trust = trust_thermodynamic(ppv, sigma_calib, t_comp=t_comp)

    modal_key = max(cluster_sizes.keys(), key=lambda k: len(cluster_sizes[k]))
    modal_idx = cluster_sizes[modal_key][0]
    modal_answer = samples[modal_idx]

    if trust >= cfg.theta_high:
        action = "ADMIT_HIGH"
    elif trust >= cfg.theta_low:
        action = "ADMIT_MID"
    else:
        action = "ABSTAIN"

    # Consensus floor: if the modal answer is corroborated by NO other sample (its
    # cluster is a singleton while the others also diverge), there is no agreement
    # to admit - abstain regardless of the numeric trust. The trust score itself is
    # left unchanged for audit transparency; only the ACTION is overridden.
    modal_size = len(cluster_sizes[modal_key])
    if len(samples) >= cfg.min_modal_agreement and modal_size < cfg.min_modal_agreement:
        action = "ABSTAIN"

    logger.info(
        "snc_decision",
        extra={
            "action": action,
            "trust": round(trust, 4),
            "ppv": round(ppv, 4),
            "sigma_calib": round(sigma_calib, 4),
            "n_clusters": len(cluster_sizes),
            "n_samples": len(samples),
        },
    )

    return SNCDecision(
        action=action,
        trust=trust,
        ppv=ppv,
        sigma_calib=sigma_calib,
        t_comp=t_comp,
        n_clusters=len(cluster_sizes),
        modal_answer=modal_answer,
        samples=samples,
    )


# ----- Audit serialization -----


def serialize_decision(decision: SNCDecision) -> dict:
    return {
        "action": decision.action,
        "trust": round(decision.trust, 6),
        "ppv": round(decision.ppv, 6),
        "sigma_calib": round(decision.sigma_calib, 6),
        "t_comp": round(decision.t_comp, 6),
        "n_clusters": decision.n_clusters,
        "n_samples": len(decision.samples),
        "samples_summary": [
            {
                "self_confidence": extract_confidence(s),
                "answer_preview": (
                    str(s.get("answer", ""))[:200] if isinstance(s, dict) else str(s)[:200]
                ),
                "n_citations": len(s.get("citations", [])) if isinstance(s, dict) else 0,
            }
            for s in decision.samples
        ],
    }
