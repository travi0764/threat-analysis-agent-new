"""
Base ingestor interface for Threat Analysis Agent.
All ingestors (CSV, JSON, API, etc.) must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.storage.models import IndicatorType, SourceType


@dataclass
class IndicatorData:
    """
    Data class representing a raw indicator before database insertion.
    """

    indicator_type: IndicatorType
    value: str
    source_type: SourceType
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    first_seen: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "indicator_type": self.indicator_type,
            "value": self.value,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "raw_data": self.raw_data,
            "tags": self.tags if self.tags else [],
            "notes": self.notes,
            "first_seen": self.first_seen or datetime.utcnow(),
        }


@dataclass
class IngestionResult:
    """
    Result of an ingestion operation.
    """

    success: bool
    indicators_processed: int
    indicators_created: int
    indicators_updated: int
    indicators_failed: int
    errors: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None

    def add_error(self, row_number: int, error: str, data: Any = None):
        """Add an error to the result."""
        self.errors.append(
            {
                "row": row_number,
                "error": error,
                "data": data,
            }
        )


class BaseIngestor(ABC):
    """
    Abstract base class for all ingestors.
    Defines the interface that all ingestors must implement.
    """

    def __init__(self, source_type: SourceType, source_name: str):
        """
        Initialize the ingestor.

        Args:
            source_type: Type of data source
            source_name: Name of the data source
        """
        self.source_type = source_type
        self.source_name = source_name

    @abstractmethod
    def ingest(self, *args, **kwargs) -> IngestionResult:
        """
        Ingest data from the source.

        Returns:
            IngestionResult with statistics and any errors
        """
        pass

    @abstractmethod
    def validate(self, data: Any) -> bool:
        """
        Validate the input data format.

        Args:
            data: Data to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    def normalize_indicator(
        self, raw_indicator: Dict[str, Any]
    ) -> Optional[IndicatorData]:
        """
        Normalize a raw indicator into IndicatorData format.
        Should be overridden by subclasses for source-specific normalization.

        Args:
            raw_indicator: Raw indicator data

        Returns:
            IndicatorData object or None if normalization fails
        """
        pass

    def batch_normalize(
        self, raw_indicators: List[Dict[str, Any]]
    ) -> List[IndicatorData]:
        """
        Normalize a batch of raw indicators.

        Args:
            raw_indicators: List of raw indicator data

        Returns:
            List of IndicatorData objects
        """
        normalized = []
        for raw in raw_indicators:
            try:
                indicator_data = self.normalize_indicator(raw)
                if indicator_data:
                    normalized.append(indicator_data)
            except Exception:
                # Log error but continue processing
                continue

        return normalized


# DO NOT ADD ANY IMPORTS HERE - This file should not import CSVIngestor or JSONIngestor
# to avoid circular imports. Those classes import from this file.
