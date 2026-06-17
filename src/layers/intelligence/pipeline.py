"""
Intelligence Layer Pipeline - Public interface for NormaAI intelligence operations.

Wraps LangGraph agents with optional CoVe verification and SSE streaming support.

Provides both streaming and non-streaming variants:
- arun_qa_stream: Stream Q&A response with token-by-token output
- arun_qa: Non-streaming Q&A (backward compatible)
- arun_gap_analysis_stream: Stream gap analysis with optional CoVe
- arun_gap_analysis: Non-streaming gap analysis
- arun_monitor_stream: Stream regulatory change impact with optional CoVe
- arun_monitor: Non-streaming monitor check

Each streaming method:
1. Runs the existing LangGraph agent (arun_qa, arun_gap_analysis, etc from src.agents.graph)
2. Streams result tokens via streaming_llm
3. If enable_cove=True, runs CoVeOrchestrator after the initial draft
4. Yields SSE events throughout
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from src.api.streaming.sse import (
    DoneEvent,
    ErrorEvent,
    PhaseChangeEvent,
    SSEEvent,
    TokenEvent,
)

logger = logging.getLogger(__name__)


class IntelligencePipeline:
    """Public interface for NormaAI intelligence operations.

    Wraps LangGraph agents with optional CoVe verification
    and SSE streaming support.
    """

    def __init__(self, indexer=None, normattiva_client=None, eurlex_client=None):
        """
        Initialize the intelligence pipeline.

        Args:
            indexer: HybridIndexer instance for retrieval
            normattiva_client: Normattiva API client (optional)
            eurlex_client: EUR-Lex SPARQL client (optional)
        """
        self.indexer = indexer
        self.normattiva = normattiva_client
        self.eurlex = eurlex_client
        self._graph = None
        self._async_graph = None

    @property
    def graph(self):
        """Lazy-load sync graph."""
        if self._graph is None:
            from src.agents.graph import build_graph

            self._graph = build_graph(use_async_nodes=False)
        return self._graph

    @property
    def async_graph(self):
        """Lazy-load async graph."""
        if self._async_graph is None:
            from src.agents.graph import build_graph

            self._async_graph = build_graph(use_async_nodes=True)
        return self._async_graph

    # ─── Streaming Variants ──────────────────────────────────────────

    async def arun_qa_stream(
        self,
        query: str,
        company_profile: dict,
        enable_cove: bool = False,
    ) -> AsyncIterator[SSEEvent]:
        """
        Stream Q&A response with optional CoVe verification.

        Workflow:
        1. Run LangGraph agent to get initial response
        2. Stream response tokens via streaming_llm
        3. If enable_cove=True, run CoVeOrchestrator to verify claims
        4. Yield SSE events throughout

        Args:
            query: User question about regulatory requirements
            company_profile: Company profile dict (industry, employees, countries, etc.)
            enable_cove: If True, apply Chain-of-Verification after draft response

        Yields:
            SSE events (token, thinking, verification_result, phase_change, done)
        """
        try:
            # Phase 1: Initial response from agent
            yield PhaseChangeEvent(
                phase="drafting",
                message="Generating initial response from regulatory knowledge base...",
            )

            # Run async graph to get initial response
            initial_response = ""
            try:
                from src.agents.graph import arun_qa

                result = await arun_qa(
                    query=query,
                    company_profile=company_profile,
                    use_async_graph=True,
                )

                # Extract response text
                initial_response = result.get("response", "")
                confidence = result.get("confidence_score", 0.5)

            except Exception as e:
                logger.error(f"Agent QA failed: {e}")
                yield ErrorEvent(message=f"Agent error: {e}", recoverable=True)
                initial_response = ""
                confidence = 0.0

            # Phase 2: Stream response tokens
            token_count = 0
            for i, char in enumerate(initial_response):
                yield TokenEvent(content=char, index=i)
                token_count += 1
                # Small delay to simulate streaming
                await asyncio.sleep(0.001)

            # Phase 3: CoVe verification (if enabled)
            if enable_cove and confidence < 0.85:
                yield PhaseChangeEvent(
                    phase="verification",
                    message="Running Chain-of-Verification to verify claims...",
                )

                try:
                    from src.agents.cove.orchestrator import CoVeOrchestrator

                    cove = CoVeOrchestrator()
                    async for event in cove.arun_verification(
                        response=initial_response,
                        query=query,
                        company_profile=company_profile,
                    ):
                        yield event
                except Exception as e:
                    logger.error(f"CoVe verification failed: {e}")
                    yield ErrorEvent(
                        message=f"CoVe error: {e}",
                        recoverable=True,
                    )

            # Phase 4: Complete
            yield DoneEvent(
                total_tokens=token_count,
                confidence_score=confidence,
                requires_review=confidence < 0.75,
                cove_applied=enable_cove and confidence < 0.85,
            )

        except Exception as e:
            logger.error(f"QA stream error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), recoverable=False)

    async def arun_gap_analysis_stream(
        self,
        framework: str,
        company_profile: dict,
        enable_cove: bool = False,
    ) -> AsyncIterator[SSEEvent]:
        """
        Stream gap analysis with optional CoVe verification.

        Analyzes company's compliance gaps against a specific regulatory framework.

        Args:
            framework: Regulatory framework (CSRD, GDPR, etc.)
            company_profile: Company profile dict
            enable_cove: If True, apply Chain-of-Verification

        Yields:
            SSE events
        """
        try:
            yield PhaseChangeEvent(
                phase="analysis",
                message=f"Analyzing compliance gaps for {framework}...",
            )

            # Run gap analysis agent
            analysis = ""
            confidence = 0.5
            try:
                from src.agents.graph import arun_gap_analysis

                result = await arun_gap_analysis(
                    framework=framework,
                    company_profile=company_profile,
                    use_async_graph=True,
                )

                analysis = result.get("response", "")
                confidence = result.get("confidence_score", 0.5)

            except Exception as e:
                logger.error(f"Gap analysis failed: {e}")
                yield ErrorEvent(message=f"Analysis error: {e}", recoverable=True)

            # Stream response tokens
            token_count = 0
            for i, char in enumerate(analysis):
                yield TokenEvent(content=char, index=i)
                token_count += 1
                await asyncio.sleep(0.001)

            # CoVe verification if enabled
            if enable_cove and confidence < 0.85:
                yield PhaseChangeEvent(
                    phase="verification",
                    message="Verifying gap analysis findings...",
                )

                try:
                    from src.agents.cove.orchestrator import CoVeOrchestrator

                    cove = CoVeOrchestrator()
                    async for event in cove.arun_verification(
                        response=analysis,
                        query=f"Gap analysis for {framework}",
                        company_profile=company_profile,
                    ):
                        yield event
                except Exception as e:
                    logger.warning(f"CoVe verification skipped: {e}")

            yield DoneEvent(
                total_tokens=token_count,
                confidence_score=confidence,
                requires_review=confidence < 0.75,
                cove_applied=enable_cove and confidence < 0.85,
            )

        except Exception as e:
            logger.error(f"Gap analysis stream error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), recoverable=False)

    async def arun_monitor_stream(
        self,
        change: str,
        company_profile: dict,
        enable_cove: bool = False,
    ) -> AsyncIterator[SSEEvent]:
        """
        Stream regulatory change impact analysis with optional CoVe.

        Analyzes the impact of a regulatory change on the company.

        Args:
            change: Description of regulatory change
            company_profile: Company profile dict
            enable_cove: If True, apply Chain-of-Verification

        Yields:
            SSE events
        """
        try:
            yield PhaseChangeEvent(
                phase="monitoring",
                message="Analyzing regulatory change impact...",
            )

            # Run monitor agent
            impact_analysis = ""
            confidence = 0.5
            try:
                from src.agents.graph import arun_monitor

                result = await arun_monitor(
                    change=change,
                    company_profile=company_profile,
                    use_async_graph=True,
                )

                impact_analysis = result.get("response", "")
                confidence = result.get("confidence_score", 0.5)

            except Exception as e:
                logger.error(f"Monitor check failed: {e}")
                yield ErrorEvent(message=f"Monitor error: {e}", recoverable=True)

            # Stream response tokens
            token_count = 0
            for i, char in enumerate(impact_analysis):
                yield TokenEvent(content=char, index=i)
                token_count += 1
                await asyncio.sleep(0.001)

            # CoVe verification if enabled
            if enable_cove and confidence < 0.85:
                yield PhaseChangeEvent(
                    phase="verification",
                    message="Verifying impact assessment...",
                )

                try:
                    from src.agents.cove.orchestrator import CoVeOrchestrator

                    cove = CoVeOrchestrator()
                    async for event in cove.arun_verification(
                        response=impact_analysis,
                        query=f"Impact of regulatory change: {change[:100]}",
                        company_profile=company_profile,
                    ):
                        yield event
                except Exception as e:
                    logger.warning(f"CoVe verification skipped: {e}")

            yield DoneEvent(
                total_tokens=token_count,
                confidence_score=confidence,
                requires_review=confidence < 0.75,
                cove_applied=enable_cove and confidence < 0.85,
            )

        except Exception as e:
            logger.error(f"Monitor stream error: {e}", exc_info=True)
            yield ErrorEvent(message=str(e), recoverable=False)

    # ─── Non-streaming Variants (Backward Compatible) ──────────────

    async def arun_qa(self, query: str, company_profile: dict) -> dict:
        """
        Non-streaming Q&A (backward compatible).

        Runs the full QA pipeline and returns a single response dict.

        Args:
            query: User question
            company_profile: Company profile dict

        Returns:
            Result dict with response, confidence_score, etc.
        """
        try:
            from src.agents.graph import arun_qa as agent_arun_qa

            result = await agent_arun_qa(
                query=query,
                company_profile=company_profile,
                use_async_graph=True,
            )
            return result
        except Exception as e:
            logger.error(f"QA failed: {e}")
            return {
                "response": "",
                "confidence_score": 0.0,
                "error": str(e),
            }

    async def arun_gap_analysis(self, framework: str, company_profile: dict) -> dict:
        """
        Non-streaming gap analysis (backward compatible).

        Args:
            framework: Regulatory framework
            company_profile: Company profile dict

        Returns:
            Result dict with response, gap_areas, recommendations, etc.
        """
        try:
            from src.agents.graph import arun_gap_analysis as agent_arun_gap

            result = await agent_arun_gap(
                framework=framework,
                company_profile=company_profile,
                use_async_graph=True,
            )
            return result
        except Exception as e:
            logger.error(f"Gap analysis failed: {e}")
            return {
                "response": "",
                "gap_areas": [],
                "confidence_score": 0.0,
                "error": str(e),
            }

    async def arun_monitor(self, change: str, company_profile: dict) -> dict:
        """
        Non-streaming regulatory change monitoring (backward compatible).

        Args:
            change: Description of regulatory change
            company_profile: Company profile dict

        Returns:
            Result dict with response, impact_areas, action_items, etc.
        """
        try:
            from src.agents.graph import arun_monitor as agent_arun_monitor

            result = await agent_arun_monitor(
                change=change,
                company_profile=company_profile,
                use_async_graph=True,
            )
            return result
        except Exception as e:
            logger.error(f"Monitor check failed: {e}")
            return {
                "response": "",
                "impact_areas": [],
                "action_items": [],
                "confidence_score": 0.0,
                "error": str(e),
            }

    # ─── Health & Diagnostics ────────────────────────────────────

    async def health_check(self) -> dict:
        """Check health of intelligence pipeline components."""
        health = {
            "status": "healthy",
            "components": {},
        }

        # Check indexer
        if self.indexer:
            try:
                stats = self.indexer.get_collection_stats()
                health["components"]["indexer"] = {
                    "status": "healthy",
                    "points": stats.get("points_count", 0),
                }
            except Exception as e:
                health["components"]["indexer"] = {
                    "status": "degraded",
                    "error": str(e),
                }
                health["status"] = "degraded"

        # Check graph
        try:
            health["components"]["graph"] = {"status": "healthy"}
        except Exception as e:
            health["components"]["graph"] = {
                "status": "degraded",
                "error": str(e),
            }
            health["status"] = "degraded"

        return health

    async def get_stats(self) -> dict:
        """Get pipeline statistics."""
        stats = {
            "timestamp": None,
            "indexer": None,
            "graph": None,
        }

        if self.indexer:
            try:
                stats["indexer"] = self.indexer.get_collection_stats()
            except Exception as e:
                logger.warning(f"Could not get indexer stats: {e}")

        return stats
