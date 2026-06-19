"""
Background scheduler for periodic regulatory data acquisition.

Schedules periodic crawls from Normattiva and EUR-Lex.
Uses asyncio tasks (no external scheduler dependency).
Runs in background during FastAPI lifespan.
"""

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class AcquisitionScheduler:
    """
    Schedules periodic crawls from Normattiva and EUR-Lex.

    Uses asyncio tasks (no external scheduler dependency).
    Runs in background during FastAPI lifespan.

    Usage:
        scheduler = AcquisitionScheduler(interval_hours=6)
        await scheduler.start()
        # ... server runs ...
        await scheduler.stop()
    """

    def __init__(
        self,
        normattiva_client=None,
        eurlex_client=None,
        interval_hours: int = 6,
        initial_delay_seconds: int = 30,
    ):
        """
        Initialize the scheduler.

        Args:
            normattiva_client: Normattiva API client instance (optional)
            eurlex_client: EUR-Lex SPARQL client instance (optional)
            interval_hours: Interval between acquisition cycles (default 6 hours)
            initial_delay_seconds: Delay before first run (default 30 seconds)
        """
        self.normattiva = normattiva_client
        self.eurlex = eurlex_client
        self.interval_hours = interval_hours
        self.initial_delay_seconds = initial_delay_seconds

        self._task = None
        self._running = False
        self._last_run = None
        self._cycle_count = 0
        self._error_count = 0

    async def start(self) -> None:
        """Start background acquisition loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        logger.info(
            f"Starting acquisition scheduler (interval={self.interval_hours}h, "
            f"initial_delay={self.initial_delay_seconds}s)"
        )

        # Create background task
        self._task = asyncio.create_task(self._background_loop())

    async def stop(self) -> None:
        """Stop gracefully."""
        if not self._running:
            return

        logger.info("Stopping acquisition scheduler...")
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except TimeoutError:
                logger.warning("Scheduler shutdown timeout, canceling task")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info(
            f"Scheduler stopped. Completed {self._cycle_count} cycles, "
            f"{self._error_count} errors"
        )

    async def _background_loop(self) -> None:
        """Background loop that runs acquisition cycles periodically."""
        try:
            # Initial delay
            await asyncio.sleep(self.initial_delay_seconds)

            # Main loop
            while self._running:
                try:
                    await self._run_cycle()
                    self._cycle_count += 1
                except Exception as e:
                    self._error_count += 1
                    logger.error(f"Acquisition cycle failed: {e}", exc_info=True)

                # Wait until next cycle
                if self._running:
                    await asyncio.sleep(self.interval_hours * 3600)

        except asyncio.CancelledError:
            logger.info("Acquisition scheduler cancelled")
        except Exception as e:
            logger.error(f"Acquisition scheduler crashed: {e}", exc_info=True)
            self._running = False

    async def _run_cycle(self) -> dict:
        """
        Execute one acquisition cycle: check for updates, download, process.

        Returns:
            Statistics dict
        """
        start_time = datetime.now(UTC)
        logger.info(
            f"[Acquisition Cycle {self._cycle_count + 1}] Starting at {start_time.isoformat()}"
        )

        stats = {
            "cycle": self._cycle_count + 1,
            "timestamp": start_time.isoformat(),
            "eurlex": {"regulations_found": 0, "chunks_indexed": 0},
            "normattiva": {"regulations_found": 0, "chunks_indexed": 0},
        }

        # EUR-Lex acquisition
        if self.eurlex:
            try:
                logger.info("  Checking EUR-Lex for new regulations...")
                eurlex_stats = await self._acquire_eurlex()
                stats["eurlex"] = eurlex_stats
                logger.info(
                    f"  EUR-Lex: found {eurlex_stats['regulations_found']}, "
                    f"indexed {eurlex_stats['chunks_indexed']}"
                )
            except Exception as e:
                logger.error(f"  EUR-Lex acquisition failed: {e}")
                stats["eurlex"]["error"] = str(e)

        # Normattiva acquisition
        if self.normattiva:
            try:
                logger.info("  Checking Normattiva for new regulations...")
                normattiva_stats = await self._acquire_normattiva()
                stats["normattiva"] = normattiva_stats
                logger.info(
                    f"  Normattiva: found {normattiva_stats['regulations_found']}, "
                    f"indexed {normattiva_stats['chunks_indexed']}"
                )
            except Exception as e:
                logger.error(f"  Normattiva acquisition failed: {e}")
                stats["normattiva"]["error"] = str(e)

        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        stats["elapsed_seconds"] = elapsed
        self._last_run = start_time

        logger.info(
            f"[Acquisition Cycle {self._cycle_count + 1}] Complete "
            f"({elapsed:.1f}s, total_indexed="
            f"{stats['eurlex']['chunks_indexed'] + stats['normattiva']['chunks_indexed']})"
        )

        return stats

    async def _acquire_eurlex(self) -> dict:
        """
        Check EUR-Lex for new regulations and amendments.

        Returns:
            Stats dict with regulations_found, chunks_indexed
        """
        if not self.eurlex:
            return {"regulations_found": 0, "chunks_indexed": 0}

        try:
            # Check for amendments to tracked regulations
            from src.crawler.eurlex.client import CORE_FRAMEWORKS

            all_celex = []
            for celex_map in CORE_FRAMEWORKS.values():
                all_celex.extend(celex_map.keys())

            amendments = self.eurlex.check_for_new_amendments(all_celex)
            logger.info(f"    Found {len(amendments)} amendments")

            # Check for new legislation
            new_legislation = self.eurlex.fetch_recent_legislation(days_back=1)
            logger.info(f"    Found {len(new_legislation)} new regulations")

            # Process and index new content
            new_chunks = []
            from src.nlp.chunking.contextual_chunker import ContextualChunker
            from src.nlp.chunking.legal_chunker import EURLexHTMLChunker

            for reg in new_legislation[:5]:  # Limit to 5 per cycle
                try:
                    html = self.eurlex.download_full_text_html(reg.celex)
                    if html and len(html.strip()) > 500:
                        chunker = EURLexHTMLChunker(
                            celex=reg.celex, framework=reg.framework or "UNKNOWN"
                        )
                        chunks = chunker.chunk_html(html)
                        new_chunks.extend(chunks)
                        logger.info(f"    Downloaded {reg.celex}: {len(chunks)} chunks")
                except Exception as e:
                    logger.warning(f"    Failed to download {reg.celex}: {e}")

            # Index new chunks
            indexed = 0
            if new_chunks:
                from src.nlp.embedding.indexer import HybridIndexer

                # Create indexer instance (would normally be passed in)
                try:
                    indexer = HybridIndexer()
                    ctx_chunker = ContextualChunker()

                    enriched = []
                    for chunk in new_chunks:
                        ctx = ctx_chunker.enrich_single(
                            text=chunk.text,
                            framework=chunk.metadata.get("framework", ""),
                            article=chunk.metadata.get("article_number", ""),
                            section=chunk.metadata.get("section_title", ""),
                        )
                        ctx.metadata.update(chunk.metadata)
                        enriched.append(ctx)

                    indexed = indexer.index_contextual_chunks(enriched)
                except Exception as e:
                    logger.warning(f"    Indexing failed: {e}")

            return {
                "regulations_found": len(new_legislation),
                "amendments_found": len(amendments),
                "chunks_indexed": indexed,
            }

        except Exception as e:
            logger.error(f"EUR-Lex acquisition error: {e}", exc_info=True)
            return {"regulations_found": 0, "chunks_indexed": 0, "error": str(e)}

    async def _acquire_normattiva(self) -> dict:
        """
        Check Normattiva for new Italian regulations.

        Returns:
            Stats dict with regulations_found, chunks_indexed
        """
        if not self.normattiva:
            return {"regulations_found": 0, "chunks_indexed": 0}

        try:
            # Check for new publications
            new_regs = self.normattiva.fetch_recent_publications(days_back=1)
            logger.info(f"    Found {len(new_regs)} new regulations")

            # Process and index (similar to EUR-Lex)
            new_chunks = []
            from src.nlp.chunking.contextual_chunker import ContextualChunker
            from src.nlp.chunking.legal_chunker import EURLexHTMLChunker

            for reg in new_regs[:5]:
                try:
                    html = self.normattiva.download_full_text_html(reg.id)
                    if html and len(html.strip()) > 500:
                        chunker = EURLexHTMLChunker(
                            celex=f"IT_{reg.id}",
                            framework=reg.framework or "UNKNOWN",
                        )
                        chunks = chunker.chunk_html(html)
                        new_chunks.extend(chunks)
                except Exception as e:
                    logger.warning(f"    Failed to download {reg.id}: {e}")

            # Index new chunks
            indexed = 0
            if new_chunks:
                from src.nlp.embedding.indexer import HybridIndexer

                try:
                    indexer = HybridIndexer()
                    ctx_chunker = ContextualChunker()

                    enriched = []
                    for chunk in new_chunks:
                        ctx = ctx_chunker.enrich_single(
                            text=chunk.text,
                            framework=chunk.metadata.get("framework", ""),
                            article=chunk.metadata.get("article_number", ""),
                            section=chunk.metadata.get("section_title", ""),
                        )
                        ctx.metadata.update(chunk.metadata)
                        enriched.append(ctx)

                    indexed = indexer.index_contextual_chunks(enriched)
                except Exception as e:
                    logger.warning(f"    Indexing failed: {e}")

            return {
                "regulations_found": len(new_regs),
                "chunks_indexed": indexed,
            }

        except Exception as e:
            logger.error(f"Normattiva acquisition error: {e}", exc_info=True)
            return {"regulations_found": 0, "chunks_indexed": 0, "error": str(e)}

    async def run_once(self, source: str = "all") -> dict:
        """
        Manual trigger for a single acquisition cycle.

        Args:
            source: "all", "eurlex", or "normattiva"

        Returns:
            Statistics from the cycle
        """
        logger.info(f"Manual acquisition trigger (source={source})")

        stats = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": source,
        }

        if source in ("all", "eurlex"):
            stats["eurlex"] = await self._acquire_eurlex()

        if source in ("all", "normattiva"):
            stats["normattiva"] = await self._acquire_normattiva()

        return stats

    def get_stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "interval_hours": self.interval_hours,
        }
