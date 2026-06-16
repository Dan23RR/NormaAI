"""Chain-of-Verification (CoVe) orchestrator — main coordinator for the 5-phase pipeline.

Orchestrates:
1. Draft extraction — parse claims from initial LLM response
2. Planning — generate verification questions
3. Verification — independently verify each claim in isolated context
4. Revision — rewrite response based on evidence
5. Validation — check citations against regulatory databases

Each phase emits SSE events for streaming progress to clients.
Graceful degradation: if any phase fails, continue to next phase.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from src.agents.cove.models import (
    CitationCheck,
    Claim,
    CoVeConfig,
    CoVeResult,
    DraftResult,
    RevisionResult,
    VerificationPlan,
    VerificationQuestion,
    VerificationStep,
)
from src.agents.llm import acall_llm, extract_confidence
from src.api.streaming.sse import (
    DoneEvent,
    ErrorEvent,
    PhaseChangeEvent,
    SSEEvent,
    VerificationResultEvent,
    VerificationStartEvent,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# Canonical CELEX format (sector 3 = legislation): 3 + YYYY + type letter(s) + number.
_CELEX_RE = re.compile(r"^3\d{4}[A-Z]{1,2}\d{3,4}$")


def _known_celex() -> set[str]:
    """CELEX numbers we have actually seeded — our trusted ground truth.

    A citation to a regulation we never indexed is, by definition, unverifiable
    from our corpus and must NOT be rubber-stamped as valid (that was the bug
    that hollowed out the 'audit-defensible' promise).
    """
    try:
        from src.crawler.eurlex.client import CORE_FRAMEWORKS

        return {celex for fw in CORE_FRAMEWORKS.values() for celex in fw}
    except Exception:  # noqa: BLE001
        return set()


def _load_prompt(name: str) -> str:
    """Load prompt template from prompts directory."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _extract_citations_from_text(text: str) -> list[dict]:
    """Extract potential URN and CELEX citations from text using regex patterns."""
    citations = []

    # URN pattern: urn:nir:... (Italian law)
    urn_pattern = r"urn:nir:[a-z0-9\-_/:]+"
    for match in re.finditer(urn_pattern, text, re.IGNORECASE):
        citations.append(
            {
                "type": "urn",
                "value": match.group(0),
                "text": match.group(0),
            }
        )

    # CELEX pattern: real CELEX numbers carry a sector digit + year + type
    # LETTER + number, e.g. 32022L2464 (CSRD), 32024R1689 (AI Act). The old
    # all-digit pattern \b3\d{7}\b never matched these — EU citations slipped
    # through unvalidated. Match both the lettered form and the rare all-digit.
    celex_pattern = r"\b3\d{4}[A-Z]{1,2}\d{3,4}\b|\b3\d{7}\b"
    seen_celex = set()
    for match in re.finditer(celex_pattern, text):
        celex = match.group(0)
        if celex in seen_celex:
            continue
        seen_celex.add(celex)
        citations.append(
            {
                "type": "celex",
                "value": celex,
                "text": celex,
            }
        )

    # Article references: "Art. 29", "Article 5", "artt. 1-3"
    article_pattern = r"(?:Art\.?|Article|artt\.?)\s+(\d+)(?:\s*[-–]\s*(\d+))?"
    for match in re.finditer(article_pattern, text, re.IGNORECASE):
        start = match.group(1)
        end = match.group(2) if match.group(2) else start
        citations.append(
            {
                "type": "article",
                "value": f"Articles {start}" + (f"-{end}" if end != start else ""),
                "text": match.group(0),
            }
        )

    return citations


class CoVeOrchestrator:
    """Main orchestrator for the Chain-of-Verification pipeline.

    Coordinates all 5 phases and emits SSE events for streaming progress.
    """

    def __init__(
        self,
        indexer=None,
        normattiva_client=None,
        config: CoVeConfig | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            indexer: HybridIndexer instance for searching regulatory documents
            normattiva_client: Client for validating Italian law citations
            config: CoVeConfig with pipeline parameters
        """
        self.indexer = indexer
        self.normattiva_client = normattiva_client
        self.config = config or CoVeConfig()
        self._start_time = None

    async def run(
        self,
        draft_state: dict,
        task_type: str,
    ) -> AsyncIterator[SSEEvent]:
        """Run the complete CoVe pipeline.

        Args:
            draft_state: AgentState dict with query, company_profile, retrieved_chunks, result_json
            task_type: The task type (monitor, gap, qa, etc.)

        Yields:
            SSE events for each phase and result
        """
        self._start_time = datetime.now()
        phases_completed = 0

        try:
            # Phase 1: Draft extraction
            yield PhaseChangeEvent(
                phase="draft", message="Parsing initial response and extracting claims..."
            )

            result_json = draft_state.get("result_json", "{}")
            try:
                result_obj = (
                    json.loads(result_json) if isinstance(result_json, str) else result_json
                )
            except (json.JSONDecodeError, TypeError):
                result_obj = {"answer": str(result_json), "citations": []}

            # Get the response text
            response_text = ""
            if isinstance(result_obj, dict):
                response_text = result_obj.get("answer", str(result_obj))
            else:
                response_text = str(result_obj)

            draft = DraftResult(
                text=response_text,
                claims=[],
                raw_json=result_obj if isinstance(result_obj, dict) else {},
                confidence=extract_confidence(result_obj) if isinstance(result_obj, dict) else 0.5,
            )

            # Extract claims from draft
            claims = await self._extract_claims(response_text)
            draft.claims = claims
            phases_completed = 1

            if not claims:
                logger.info("No claims extracted from response, skipping verification phases")
                # Skip directly to validation and finish
                yield PhaseChangeEvent(
                    phase="validation", message="No claims to verify, validating citations only..."
                )
                citation_checks = await self._validate_citations(response_text)
                phases_completed = 5

                elapsed = (datetime.now() - self._start_time).total_seconds()
                yield DoneEvent(
                    total_tokens=len(response_text.split()),
                    confidence_score=draft.confidence,
                    requires_review=draft.confidence < 0.7,
                    cove_applied=False,
                )
                return

            # Phase 2: Planning
            yield PhaseChangeEvent(
                phase="planning", message=f"Planning verification for {len(claims)} claims..."
            )

            plan = await self._plan_verification(claims)
            phases_completed = 2

            # Phase 3: Verification
            yield PhaseChangeEvent(
                phase="verification",
                message=f"Verifying {len(plan.questions)} claims against regulatory database...",
            )

            verifications = []
            for _i, question in enumerate(plan.questions):
                yield VerificationStartEvent(
                    claim=claims[question.claim_index].text,
                    claim_index=question.claim_index,
                    total_claims=len(claims),
                )

                try:
                    step = await asyncio.wait_for(
                        self._verify_claim(claims[question.claim_index], question),
                        timeout=self.config.timeout_per_phase_seconds,
                    )
                    verifications.append(step)

                    yield VerificationResultEvent(
                        claim=step.claim.text,
                        claim_index=step.claim_index,
                        verified=step.verified,
                        confidence=step.confidence,
                        evidence=step.answer,
                    )
                except TimeoutError:
                    logger.warning(f"Verification timeout for claim {question.claim_index}")
                    yield ErrorEvent(
                        message=f"Verification timeout for claim {question.claim_index}",
                        recoverable=True,
                    )
                except Exception as e:
                    logger.error(f"Verification error for claim {question.claim_index}: {e}")
                    yield ErrorEvent(
                        message=f"Verification error: {str(e)}",
                        recoverable=True,
                    )

            phases_completed = 3

            # Phase 4: Revision
            yield PhaseChangeEvent(
                phase="revision", message="Revising response based on verification results..."
            )

            revision = await self._revise_draft(draft, verifications)
            phases_completed = 4

            # Phase 5: Citation validation
            yield PhaseChangeEvent(
                phase="validation", message="Validating all citations in revised response..."
            )

            if not self.config.skip_citation_check:
                citation_checks = await self._validate_citations(revision.revised_text)
            else:
                citation_checks = []
            phases_completed = 5

            # Compile final result
            elapsed = (datetime.now() - self._start_time).total_seconds()
            CoVeResult(
                draft=draft,
                plan=plan,
                verifications=verifications,
                revision=revision,
                citation_checks=citation_checks,
                total_time_seconds=elapsed,
                phases_completed=phases_completed,
            )

            # Emit done event with final stats
            verified_count = sum(1 for v in verifications if v.verified)
            final_confidence = (
                (verified_count / len(verifications)) * 0.7 + revision.confidence * 0.3
                if verifications
                else revision.confidence
            )

            # Flag review when a citation FAILED validation (e.g. a CELEX we
            # could not verify) — not merely because a citation is present.
            invalid_citations = sum(1 for c in citation_checks if not c.exists)
            yield DoneEvent(
                total_tokens=len(revision.revised_text.split()),
                confidence_score=final_confidence,
                requires_review=final_confidence < 0.7 or invalid_citations > 0,
                cove_applied=True,
                # Surface the corrected text so the caller can replace the draft.
                revised_text=revision.revised_text or None,
            )

            logger.info(
                "cove_pipeline_complete",
                extra={
                    "claims": len(claims),
                    "verified": verified_count,
                    "unverified": len(verifications) - verified_count,
                    "citations_checked": len(citation_checks),
                    "elapsed_seconds": elapsed,
                    "phases_completed": phases_completed,
                },
            )

        except TimeoutError:
            logger.error("CoVe pipeline timeout")
            yield ErrorEvent(
                message="CoVe pipeline timeout",
                recoverable=False,
            )
        except Exception as e:
            logger.error(f"CoVe pipeline error: {e}", exc_info=True)
            yield ErrorEvent(
                message=f"CoVe pipeline error: {str(e)}",
                recoverable=False,
            )

    async def _extract_claims(self, response_text: str) -> list[Claim]:
        """Extract factual claims and citations from response text.

        Args:
            response_text: The LLM-generated response

        Returns:
            List of extracted claims
        """
        if not response_text or len(response_text.strip()) < 10:
            return []

        prompt = _load_prompt("cove_extract_claims")
        system_prompt = prompt.format(response_text=response_text[:3000])  # Truncate for context

        try:
            result = await acall_llm(system_prompt, "Extract all factual claims and citations.")

            if "error" in result:
                logger.warning(f"Claim extraction error: {result.get('error')}")
                return []

            claims_data = result
            if isinstance(claims_data, dict) and not isinstance(claims_data, list):
                # Single dict result, wrap it
                if "claims" in claims_data:
                    claims_data = claims_data["claims"]
                elif "text" in claims_data:
                    return []

            claims = []
            if isinstance(claims_data, list):
                for item in claims_data[: self.config.max_claims]:
                    try:
                        claim = Claim(
                            text=item.get("text", ""),
                            citation=item.get("citation"),
                            article_ref=item.get("article_ref"),
                            framework=item.get("framework"),
                            confidence=float(item.get("confidence", 0.5)),
                        )
                        if claim.text:
                            claims.append(claim)
                    except (ValueError, TypeError, KeyError) as e:
                        logger.debug(f"Skipping malformed claim: {e}")
                        continue

            return claims

        except Exception as e:
            logger.error(f"Claim extraction failed: {e}")
            return []

    async def _plan_verification(self, claims: list[Claim]) -> VerificationPlan:
        """Generate verification questions for each claim.

        Args:
            claims: List of extracted claims

        Returns:
            Verification plan with questions
        """
        if not claims:
            return VerificationPlan(questions=[], estimated_time_seconds=0.0)

        prompt = _load_prompt("cove_plan_verification")
        claims_text = "\n".join(
            f"{i}. {c.text} (framework: {c.framework or 'unknown'})"
            for i, c in enumerate(claims[: self.config.max_claims])
        )
        system_prompt = prompt.format(claims=claims_text)

        try:
            result = await acall_llm(
                system_prompt, "Generate verification questions for each claim."
            )

            if "error" in result:
                logger.warning(f"Plan generation error: {result.get('error')}")
                return VerificationPlan(questions=[], estimated_time_seconds=0.0)

            questions_data = result
            if isinstance(questions_data, dict):
                if "questions" in questions_data:
                    questions_data = questions_data["questions"]
                elif "plans" in questions_data:
                    questions_data = questions_data["plans"]

            questions = []
            if isinstance(questions_data, list):
                for i, item in enumerate(questions_data):
                    try:
                        q = VerificationQuestion(
                            claim_index=min(item.get("claim_index", i), len(claims) - 1),
                            question=item.get("question", ""),
                            search_query=item.get("search_query", item.get("question", "")),
                            expected_source=item.get("expected_source"),
                        )
                        if q.question:
                            questions.append(q)
                    except (ValueError, TypeError, KeyError) as e:
                        logger.debug(f"Skipping malformed question: {e}")
                        continue

            estimated_time = len(questions) * 2.0  # ~2 seconds per verification
            return VerificationPlan(questions=questions, estimated_time_seconds=estimated_time)

        except Exception as e:
            logger.error(f"Plan generation failed: {e}")
            return VerificationPlan(questions=[], estimated_time_seconds=0.0)

    async def _verify_claim(
        self,
        claim: Claim,
        question: VerificationQuestion,
    ) -> VerificationStep:
        """Verify a single claim against regulatory evidence.

        Args:
            claim: The claim to verify
            question: The verification question

        Returns:
            Verification result
        """
        evidence_chunks = []

        # Search for evidence in isolated context
        if self.indexer:
            try:
                framework_filter = [claim.framework] if claim.framework else None
                evidence_chunks = self.indexer.hybrid_search(
                    query=question.search_query,
                    limit=self.config.max_verification_chunks,
                    framework_filter=framework_filter,
                )
            except Exception as e:
                logger.warning(f"Evidence search failed: {e}")

        # Format evidence for verification
        evidence_text = ""
        if evidence_chunks:
            evidence_text = "\n".join(
                f"[{c.get('framework', '?')}, {c.get('article_number', '?')}]: {c.get('text', '')}"
                for c in evidence_chunks[: self.config.max_verification_chunks]
            )
        else:
            evidence_text = "No relevant evidence found."

        # Verify claim against evidence
        prompt = _load_prompt("cove_verify_claim")
        system_prompt = prompt.format(
            evidence=evidence_text,
            claim=claim.text,
            question=question.question,
        )

        try:
            result = await acall_llm(system_prompt, "Is this claim accurate based on the evidence?")

            if "error" in result:
                answer = f"Verification error: {result.get('error')}"
                verified = False
                confidence = 0.0
                discrepancy = "Verification failed"
            else:
                answer = result.get("answer", result.get("analysis", str(result)))
                verified = result.get("verified", False)
                confidence = float(result.get("confidence", 0.5))
                discrepancy = result.get("discrepancy") if not verified else None

            return VerificationStep(
                claim_index=question.claim_index,
                claim=claim,
                question=question.question,
                answer=str(answer)[:500],  # Truncate answer
                evidence_chunks=evidence_chunks,
                verified=verified,
                confidence=confidence,
                discrepancy=discrepancy,
            )

        except Exception as e:
            logger.error(f"Claim verification failed: {e}")
            return VerificationStep(
                claim_index=question.claim_index,
                claim=claim,
                question=question.question,
                answer=f"Verification error: {str(e)}",
                evidence_chunks=[],
                verified=False,
                confidence=0.0,
                discrepancy=f"Exception: {str(e)}",
            )

    async def _revise_draft(
        self,
        draft: DraftResult,
        verifications: list[VerificationStep],
    ) -> RevisionResult:
        """Revise the draft response based on verification results.

        Args:
            draft: Original draft response
            verifications: Results from verification phase

        Returns:
            Revised response
        """
        if not verifications:
            # No verifications, return draft as-is
            return RevisionResult(
                original_text=draft.text,
                revised_text=draft.text,
                changes_made=[],
                claims_corrected=0,
                claims_removed=0,
                confidence=draft.confidence,
            )

        # Build verification summary for revision
        verification_summary = ""
        for v in verifications:
            status = "VERIFIED" if v.verified else "UNVERIFIED"
            verification_summary += (
                f"- Claim: {v.claim.text}\n  Status: {status}\n  Confidence: {v.confidence:.1%}\n"
            )
            if v.discrepancy:
                verification_summary += f"  Issue: {v.discrepancy}\n"

        prompt = _load_prompt("cove_revise_draft")
        system_prompt = prompt.format(
            original_response=draft.text,
            verification_results=verification_summary,
        )

        try:
            result = await acall_llm(
                system_prompt, "Revise the response based on the verification results."
            )

            if "error" in result:
                revised_text = draft.text
                changes = ["Revision failed: " + result.get("error")]
                confidence = draft.confidence * 0.8
            else:
                revised_text = result.get("revised_response", result.get("answer", draft.text))
                changes = result.get("changes_made", [])
                confidence = float(result.get("confidence", draft.confidence))

            # Count corrections and removals
            corrected = sum(1 for v in verifications if v.verified)
            removed = sum(1 for v in verifications if not v.verified)

            return RevisionResult(
                original_text=draft.text,
                revised_text=str(revised_text),
                changes_made=[str(c) for c in changes],
                claims_corrected=corrected,
                claims_removed=removed,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"Draft revision failed: {e}")
            return RevisionResult(
                original_text=draft.text,
                revised_text=draft.text,
                changes_made=[f"Revision error: {str(e)}"],
                claims_corrected=0,
                claims_removed=0,
                confidence=draft.confidence,
            )

    async def _validate_citations(self, text: str) -> list[CitationCheck]:
        """Validate all citations in the response.

        Args:
            text: The response text to validate

        Returns:
            List of citation validation results
        """
        citations = _extract_citations_from_text(text)
        checks = []

        for citation in citations:
            try:
                if citation["type"] == "urn" and self.normattiva_client:
                    # Validate Italian law URN. validate_urn is ASYNC and returns
                    # a URNValidationResult object (attributes, not a dict) — the
                    # old code neither awaited it nor read it correctly.
                    try:
                        result = await self.normattiva_client.validate_urn(citation["value"])
                        checks.append(
                            CitationCheck(
                                urn=citation["value"],
                                exists=bool(result.exists),
                                is_current=bool(result.is_in_force),
                                url=result.url,
                                validation="verified" if result.exists else "unverified",
                            )
                        )
                    except Exception as e:
                        checks.append(
                            CitationCheck(
                                urn=citation["value"],
                                exists=False,
                                is_current=False,
                                validation="unverified",
                                error=str(e),
                            )
                        )

                elif citation["type"] == "celex":
                    celex = citation["value"]
                    url = (
                        f"https://eur-lex.europa.eu/legal-content/EN/TXT/"
                        f"?uri=CELEX:{celex}"
                    )
                    if not _CELEX_RE.match(celex):
                        # Malformed CELEX — almost certainly fabricated.
                        checks.append(
                            CitationCheck(celex=celex, exists=False, is_current=False, url=url,
                                          validation="invalid", error="Malformed CELEX identifier")
                        )
                    elif celex in _known_celex():
                        # Cited a regulation we actually indexed → trusted.
                        checks.append(
                            CitationCheck(celex=celex, exists=True, is_current=True, url=url,
                                          validation="verified")
                        )
                    elif self.indexer is not None and getattr(self.indexer, "eurlex", None):
                        # Best-effort live check against EUR-Lex (when wired).
                        try:
                            meta = self.indexer.eurlex.fetch_regulation_metadata(celex)
                            exists = bool(getattr(meta, "title", None))
                            checks.append(
                                CitationCheck(
                                    celex=celex, exists=exists,
                                    is_current=bool(getattr(meta, "is_in_force", exists)),
                                    url=getattr(meta, "full_text_url", url) or url,
                                    validation="verified" if exists else "unverified",
                                )
                            )
                        except Exception as e:  # noqa: BLE001
                            checks.append(
                                CitationCheck(celex=celex, exists=False, is_current=False,
                                              url=url, validation="unverified",
                                              error=f"unverified: {e}")
                            )
                    else:
                        # Well-formed but outside our corpus and no live check:
                        # mark UNVERIFIED rather than rubber-stamping it valid.
                        checks.append(
                            CitationCheck(celex=celex, exists=False, is_current=False, url=url,
                                          validation="unverified",
                                          error="Not in indexed corpus; unverified")
                        )

                elif citation["type"] == "article":
                    # An article reference alone can't be checked against a registry;
                    # it is trusted only insofar as the CoVe verify phase grounds the
                    # claim in retrieved evidence. Record that honestly (no rubber-stamp).
                    checks.append(
                        CitationCheck(
                            article=citation["value"],
                            exists=True,
                            is_current=True,
                            validation="grounded",
                            error="Article-level reference; grounded via retrieved evidence, "
                            "not an independent registry lookup",
                        )
                    )

            except Exception as e:
                logger.warning(f"Citation validation error for {citation}: {e}")
                checks.append(
                    CitationCheck(
                        urn=citation.get("value") if citation["type"] == "urn" else None,
                        celex=citation.get("value") if citation["type"] == "celex" else None,
                        article=citation.get("value") if citation["type"] == "article" else None,
                        exists=False,
                        is_current=False,
                        error=str(e),
                    )
                )

        return checks
