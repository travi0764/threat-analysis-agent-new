"""
Enrichment orchestrator for managing the enrichment workflow.
Handles async execution, concurrency control, and result storage.
"""

import asyncio
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.enrichment.base import BaseEnricher, EnrichmentResult, get_enricher_registry
from app.logging_config import get_logger
from app.storage.models import Indicator
from app.storage.repository import EnrichmentRepository

logger = get_logger(__name__)


class EnrichmentOrchestrator:
    """
    Orchestrates the enrichment process for indicators.
    Manages async execution, concurrency, and result storage.
    """

    def __init__(
        self,
        db_session: Any,
        max_concurrent: Optional[int] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[int] = None,
    ):
        """
        Initialize the enrichment orchestrator.

        Args:
            db_session: Database session
            max_concurrent: Max concurrent enrichment tasks (from config if None)
            timeout: Enrichment timeout in seconds (from config if None)
            max_retries: Max retry attempts (from config if None)
            retry_delay: Delay between retries in seconds (from config if None)
        """
        self.db_session = db_session
        self.enrichment_repo = EnrichmentRepository(db_session)
        self.registry = get_enricher_registry()

        # Load settings
        settings = get_settings()
        self.max_concurrent = max_concurrent or settings.enrichment.concurrent_limit
        self.timeout = timeout or settings.enrichment.timeout
        self.max_retries = max_retries or settings.enrichment.max_retries
        self.retry_delay = retry_delay or settings.enrichment.retry_delay

        # Semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        logger.info(
            f"Enrichment orchestrator initialized: "
            f"concurrent={self.max_concurrent}, timeout={self.timeout}s"
        )

    async def enrich_indicator(
        self, indicator: Indicator, enrichers: Optional[List[BaseEnricher]] = None
    ) -> Dict[str, EnrichmentResult]:
        """
        Enrich a single indicator with all applicable enrichers.

        Args:
            indicator: Indicator to enrich
            enrichers: List of enrichers to use (auto-detect if None)

        Returns:
            Dictionary mapping enricher key to EnrichmentResult
        """
        if enrichers is None:
            enrichers = self.registry.get_enrichers_for_type(indicator.indicator_type)

        if not enrichers:
            logger.warning(
                f"No enrichers available for {indicator.indicator_type.value}: {indicator.value}"
            )
            return {}

        logger.info(
            f"Enriching {indicator.indicator_type.value} '{indicator.value}' "
            f"with {len(enrichers)} enrichers"
        )

        # Create enrichment tasks
        tasks = []
        for enricher in enrichers:
            task = self._enrich_with_enricher(indicator, enricher)
            tasks.append(task)

        # Execute all enrichments concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        enrichment_results = {}
        for enricher, result in zip(enrichers, results):
            key = f"{enricher.enrichment_type}:{enricher.provider}"

            if isinstance(result, Exception):
                logger.error(f"Enrichment failed for {key}: {result}")
                enrichment_results[key] = enricher._create_error_result(str(result))
            else:
                enrichment_results[key] = result

                # Store in database
                try:
                    self._store_enrichment(indicator.id, result)
                except Exception as e:
                    logger.error(f"Failed to store enrichment {key}: {e}")

        return enrichment_results

    async def enrich_indicators_batch(
        self,
        indicators: List[Indicator],
        enrichers: Optional[List[BaseEnricher]] = None,
    ) -> Dict[int, Dict[str, EnrichmentResult]]:
        """
        Enrich multiple indicators in parallel.

        Args:
            indicators: List of indicators to enrich
            enrichers: List of enrichers to use (auto-detect if None)

        Returns:
            Dictionary mapping indicator ID to enrichment results
        """
        logger.info(f"Batch enriching {len(indicators)} indicators")

        # Create tasks for each indicator
        tasks = []
        for indicator in indicators:
            task = self.enrich_indicator(indicator, enrichers)
            tasks.append(task)

        # Execute with concurrency control
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results to indicator IDs
        batch_results = {}
        for indicator, result in zip(indicators, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Batch enrichment failed for indicator {indicator.id}: {result}"
                )
                batch_results[indicator.id] = {}
            else:
                batch_results[indicator.id] = result

        logger.info(f"Batch enrichment complete for {len(indicators)} indicators")

        return batch_results

    async def _enrich_with_enricher(
        self, indicator: Indicator, enricher: BaseEnricher
    ) -> EnrichmentResult:
        """
        Enrich an indicator with a single enricher.
        Handles timeout, retries, and concurrency control.

        Args:
            indicator: Indicator to enrich
            enricher: Enricher to use

        Returns:
            EnrichmentResult
        """
        async with self.semaphore:
            try:
                # Execute enrichment with timeout
                result = await asyncio.wait_for(
                    enricher.enrich_with_retry(
                        indicator.value,
                        indicator.indicator_type,
                        max_retries=self.max_retries,
                        retry_delay=self.retry_delay,
                    ),
                    timeout=self.timeout,
                )

                if result.success:
                    logger.debug(
                        f"Enrichment successful: {enricher.enrichment_type}:"
                        f"{enricher.provider} for {indicator.value} (score={result.score})"
                    )
                else:
                    logger.warning(
                        f"Enrichment failed: {enricher.enrichment_type}:"
                        f"{enricher.provider} for {indicator.value} - {result.error_message}"
                    )

                return result

            except asyncio.TimeoutError:
                logger.error(
                    f"Enrichment timeout: {enricher.enrichment_type}:"
                    f"{enricher.provider} for {indicator.value}"
                )
                return enricher._create_error_result(
                    f"Enrichment timeout after {self.timeout}s"
                )
            except Exception as e:
                logger.error(
                    f"Enrichment exception: {enricher.enrichment_type}:"
                    f"{enricher.provider} for {indicator.value} - {e}"
                )
                return enricher._create_error_result(str(e))

    def _store_enrichment(self, indicator_id: int, result: EnrichmentResult) -> None:
        """
        Store enrichment result in database.

        Args:
            indicator_id: Indicator ID
            result: Enrichment result
        """
        enrichment_data = {
            "indicator_id": indicator_id,
            "enrichment_type": result.enrichment_type,
            "provider": result.provider,
            "data": result.data,
            "score": result.score,
            "success": result.success,
            "error_message": result.error_message,
            "enriched_at": result.enriched_at,
        }

        self.enrichment_repo.create(enrichment_data)
        logger.debug(f"Stored enrichment for indicator {indicator_id}")

    def get_enrichment_summary(self, indicator_id: int) -> Dict[str, Any]:
        """
        Get a summary of all enrichments for an indicator.

        Args:
            indicator_id: Indicator ID

        Returns:
            Summary dictionary with enrichment statistics
        """
        enrichments = self.enrichment_repo.get_by_indicator(indicator_id)

        summary = {
            "total_enrichments": len(enrichments),
            "successful": sum(1 for e in enrichments if e.success),
            "failed": sum(1 for e in enrichments if not e.success),
            "average_score": 0.0,
            "max_score": 0.0,
            "enrichment_types": [],
        }

        if enrichments:
            scores = [e.score for e in enrichments if e.success and e.score is not None]
            if scores:
                summary["average_score"] = sum(scores) / len(scores)
                summary["max_score"] = max(scores)

            summary["enrichment_types"] = list(
                set(e.enrichment_type for e in enrichments)
            )

        return summary


async def enrich_new_indicator(
    indicator: Indicator, db_session: Any
) -> Dict[str, EnrichmentResult]:
    """
    Convenience function to enrich a newly created indicator.

    Args:
        indicator: Newly created indicator
        db_session: Database session

    Returns:
        Dictionary of enrichment results
    """
    orchestrator = EnrichmentOrchestrator(db_session)
    return await orchestrator.enrich_indicator(indicator)
