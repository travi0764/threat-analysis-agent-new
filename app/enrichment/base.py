"""
Base enricher interface for Threat Analysis Agent.
All enrichers must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from app.logging_config import get_logger
from app.storage.models import IndicatorType

logger = get_logger(__name__)


@dataclass
class EnrichmentResult:
    """
    Result of an enrichment operation.
    """

    success: bool
    enrichment_type: str
    provider: str
    data: Dict[str, Any]
    score: Optional[float] = None  # Risk score (0-10)
    error_message: Optional[str] = None
    enriched_at: datetime = None

    def __post_init__(self):
        if self.enriched_at is None:
            self.enriched_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "enrichment_type": self.enrichment_type,
            "provider": self.provider,
            "data": self.data,
            "score": self.score,
            "success": self.success,
            "error_message": self.error_message,
            "enriched_at": self.enriched_at,
        }


class BaseEnricher(ABC):
    """
    Abstract base class for all enrichers.
    Enrichers add context and threat intelligence to indicators.
    """

    def __init__(self, enrichment_type: str, provider: str):
        """
        Initialize the enricher.

        Args:
            enrichment_type: Type of enrichment (e.g., "whois", "ip_reputation")
            provider: Provider name (e.g., "whois_api", "abuseipdb")
        """
        self.enrichment_type = enrichment_type
        self.provider = provider
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """
        Enrich an indicator with additional data.

        Args:
            indicator_value: The indicator value to enrich
            indicator_type: Type of the indicator

        Returns:
            EnrichmentResult with enrichment data
        """
        pass

    @abstractmethod
    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        """
        Check if this enricher is applicable for the given indicator type.

        Args:
            indicator_type: Type of indicator

        Returns:
            True if this enricher can process this type
        """
        pass

    def calculate_risk_score(self, data: Dict[str, Any]) -> float:
        """
        Calculate a normalized risk score (0-10) from enrichment data.
        Should be overridden by subclasses with specific logic.

        Args:
            data: Enrichment data

        Returns:
            Risk score between 0.0 and 10.0
        """
        return 0.0

    def _create_success_result(
        self, data: Dict[str, Any], score: Optional[float] = None
    ) -> EnrichmentResult:
        """
        Create a successful enrichment result.

        Args:
            data: Enrichment data
            score: Optional risk score

        Returns:
            EnrichmentResult
        """
        if score is None:
            score = self.calculate_risk_score(data)

        return EnrichmentResult(
            success=True,
            enrichment_type=self.enrichment_type,
            provider=self.provider,
            data=data,
            score=score,
        )

    def _create_error_result(self, error_message: str) -> EnrichmentResult:
        """
        Create an error enrichment result.

        Args:
            error_message: Error description

        Returns:
            EnrichmentResult with error
        """
        return EnrichmentResult(
            success=False,
            enrichment_type=self.enrichment_type,
            provider=self.provider,
            data={},
            error_message=error_message,
        )

    async def enrich_with_retry(
        self,
        indicator_value: str,
        indicator_type: IndicatorType,
        max_retries: int = 3,
        retry_delay: int = 2,
    ) -> EnrichmentResult:
        """
        Enrich with automatic retry on failure.

        Args:
            indicator_value: Indicator value
            indicator_type: Indicator type
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries (seconds)

        Returns:
            EnrichmentResult
        """
        import asyncio

        for attempt in range(max_retries):
            try:
                result = await self.enrich(indicator_value, indicator_type)

                if result.success:
                    return result

                # If not successful but no exception, return the result
                if attempt == max_retries - 1:
                    return result

                self.logger.warning(
                    f"Enrichment attempt {attempt + 1} failed: {result.error_message}"
                )
                await asyncio.sleep(retry_delay)

            except Exception as e:
                self.logger.error(f"Enrichment attempt {attempt + 1} failed: {e}")

                if attempt == max_retries - 1:
                    return self._create_error_result(
                        f"Failed after {max_retries} attempts: {str(e)}"
                    )

                await asyncio.sleep(retry_delay)

        return self._create_error_result("Unexpected error in retry logic")


class EnricherRegistry:
    """
    Registry for managing enrichers.
    Allows dynamic registration and lookup of enrichers.
    """

    def __init__(self):
        self._enrichers: Dict[str, BaseEnricher] = {}
        self.logger = get_logger(__name__)

    def register(self, enricher: BaseEnricher) -> None:
        """
        Register an enricher.

        Args:
            enricher: Enricher instance to register
        """
        key = f"{enricher.enrichment_type}:{enricher.provider}"
        self._enrichers[key] = enricher
        self.logger.info(f"Registered enricher: {key}")

    def get_enrichers_for_type(
        self, indicator_type: IndicatorType
    ) -> list[BaseEnricher]:
        """
        Get all applicable enrichers for an indicator type.

        Args:
            indicator_type: Type of indicator

        Returns:
            List of applicable enrichers
        """
        return [
            enricher
            for enricher in self._enrichers.values()
            if enricher.is_applicable(indicator_type)
        ]

    def get_enricher(
        self, enrichment_type: str, provider: str
    ) -> Optional[BaseEnricher]:
        """
        Get a specific enricher by type and provider.

        Args:
            enrichment_type: Enrichment type
            provider: Provider name

        Returns:
            Enricher instance or None
        """
        key = f"{enrichment_type}:{provider}"
        return self._enrichers.get(key)

    def list_enrichers(self) -> list[tuple[str, str]]:
        """
        List all registered enrichers.

        Returns:
            List of (enrichment_type, provider) tuples
        """
        return [
            (enricher.enrichment_type, enricher.provider)
            for enricher in self._enrichers.values()
        ]


# Global registry instance
_registry: Optional[EnricherRegistry] = None


def get_enricher_registry() -> EnricherRegistry:
    """Get the global enricher registry."""
    global _registry
    if _registry is None:
        _registry = EnricherRegistry()
    return _registry
