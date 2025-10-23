"""
Repository layer for database operations.
Provides clean interface for CRUD operations on indicators and related entities.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.storage.models import (
    AgentRun,
    Classification,
    Enrichment,
    Feedback,
    FeedbackType,
    Indicator,
    IndicatorType,
    RiskLevel,
    SourceType,
)

logger = get_logger(__name__)


class BaseRepository:
    """Base repository class with common functionality."""

    def __init__(self, session: Session):
        self.session = session


class IndicatorRepository(BaseRepository):
    """Repository for Indicator operations."""

    def create(self, indicator_data: Dict[str, Any]) -> Indicator:
        """
        Create a new indicator.

        Args:
            indicator_data: Dictionary with indicator fields

        Returns:
            Created Indicator object
        """
        indicator = Indicator(**indicator_data)
        self.session.add(indicator)
        self.session.commit()
        self.session.refresh(indicator)
        logger.debug(f"Created indicator: {indicator.value}")
        return indicator

    def get_by_id(self, indicator_id: int) -> Optional[Indicator]:
        """Get indicator by ID."""
        return self.session.query(Indicator).filter_by(id=indicator_id).first()

    def get_by_value(self, value: str) -> Optional[Indicator]:
        """Get indicator by value."""
        return self.session.query(Indicator).filter_by(value=value).first()

    def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        indicator_type: Optional[IndicatorType] = None,
        source_type: Optional[SourceType] = None,
        is_active: bool = True,
        order_by: str = "created_at",
        order_dir: str = "desc",
    ) -> List[Indicator]:
        """
        Get all indicators with filters and pagination.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            indicator_type: Filter by indicator type
            source_type: Filter by source type
            is_active: Filter by active status
            order_by: Field to order by
            order_dir: Order direction ('asc' or 'desc')

        Returns:
            List of Indicator objects
        """
        query = self.session.query(Indicator)

        # Apply filters
        if indicator_type:
            query = query.filter_by(indicator_type=indicator_type)
        if source_type:
            query = query.filter_by(source_type=source_type)
        if is_active is not None:
            query = query.filter_by(is_active=is_active)

        # Apply ordering
        order_column = getattr(Indicator, order_by, Indicator.created_at)
        if order_dir == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))

        # Apply pagination
        return query.limit(limit).offset(offset).all()

    def search(self, search_term: str, limit: int = 100) -> List[Indicator]:
        """
        Search indicators by value.

        Args:
            search_term: Search term
            limit: Maximum results

        Returns:
            List of matching Indicator objects
        """
        return (
            self.session.query(Indicator)
            .filter(Indicator.value.like(f"%{search_term}%"))
            .limit(limit)
            .all()
        )

    def update(self, indicator_id: int, updates: Dict[str, Any]) -> Optional[Indicator]:
        """
        Update an indicator.

        Args:
            indicator_id: Indicator ID
            updates: Dictionary of fields to update

        Returns:
            Updated Indicator or None
        """
        indicator = self.get_by_id(indicator_id)
        if not indicator:
            return None

        for key, value in updates.items():
            if hasattr(indicator, key):
                setattr(indicator, key, value)

        indicator.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(indicator)
        return indicator

    def delete(self, indicator_id: int) -> bool:
        """
        Delete an indicator.

        Args:
            indicator_id: Indicator ID

        Returns:
            True if deleted, False if not found
        """
        indicator = self.get_by_id(indicator_id)
        if not indicator:
            return False

        self.session.delete(indicator)
        self.session.commit()
        logger.info(f"Deleted indicator: {indicator.value}")
        return True

    def count(
        self,
        indicator_type: Optional[IndicatorType] = None,
        source_type: Optional[SourceType] = None,
    ) -> int:
        """
        Count indicators with filters.

        Args:
            indicator_type: Filter by type
            source_type: Filter by source

        Returns:
            Count of indicators
        """
        query = self.session.query(Indicator)

        if indicator_type:
            query = query.filter_by(indicator_type=indicator_type)
        if source_type:
            query = query.filter_by(source_type=source_type)

        return query.count()


class EnrichmentRepository(BaseRepository):
    """Repository for Enrichment operations."""

    def create(self, enrichment_data: Dict[str, Any]) -> Enrichment:
        """Create a new enrichment."""
        enrichment = Enrichment(**enrichment_data)
        self.session.add(enrichment)
        self.session.commit()
        self.session.refresh(enrichment)
        return enrichment

    def get_by_indicator(self, indicator_id: int) -> List[Enrichment]:
        """Get all enrichments for an indicator."""
        return self.session.query(Enrichment).filter_by(indicator_id=indicator_id).all()

    def get_latest_by_type(
        self, indicator_id: int, enrichment_type: str
    ) -> Optional[Enrichment]:
        """Get latest enrichment of a specific type for an indicator."""
        return (
            self.session.query(Enrichment)
            .filter_by(indicator_id=indicator_id, enrichment_type=enrichment_type)
            .order_by(desc(Enrichment.enriched_at))
            .first()
        )


class ClassificationRepository(BaseRepository):
    """Repository for Classification operations."""

    def create(self, classification_data: Dict[str, Any]) -> Classification:
        """Create a new classification."""
        classification = Classification(**classification_data)
        self.session.add(classification)
        self.session.commit()
        self.session.refresh(classification)
        return classification

    def get_by_indicator(self, indicator_id: int) -> Optional[Classification]:
        """Get latest classification for an indicator."""
        return (
            self.session.query(Classification)
            .filter_by(indicator_id=indicator_id)
            .order_by(desc(Classification.classified_at))
            .first()
        )

    def get_by_risk_level(
        self, risk_level: RiskLevel, limit: int = 100
    ) -> List[Classification]:
        """Get classifications by risk level."""
        return (
            self.session.query(Classification)
            .filter_by(risk_level=risk_level)
            .order_by(desc(Classification.classified_at))
            .limit(limit)
            .all()
        )

    def count_by_risk(self) -> Dict[str, int]:
        """Count classifications by risk level."""
        results = {}
        for risk_level in RiskLevel:
            count = (
                self.session.query(Classification)
                .filter_by(risk_level=risk_level)
                .count()
            )
            results[risk_level.value] = count
        return results


class AgentRunRepository(BaseRepository):
    """Repository for AgentRun operations."""

    def create(self, run_data: Dict[str, Any]) -> AgentRun:
        """Create a new agent run record."""
        run = AgentRun(**run_data)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def update(self, run_id: int, updates: Dict[str, Any]) -> Optional[AgentRun]:
        """Update an agent run."""
        run = self.session.query(AgentRun).filter_by(id=run_id).first()
        if not run:
            return None

        for key, value in updates.items():
            if hasattr(run, key):
                setattr(run, key, value)

        self.session.commit()
        self.session.refresh(run)
        return run

    def get_recent(self, limit: int = 10) -> List[AgentRun]:
        """Get recent agent runs."""
        return (
            self.session.query(AgentRun)
            .order_by(desc(AgentRun.started_at))
            .limit(limit)
            .all()
        )

    def get_by_id(self, run_id: int) -> Optional[AgentRun]:
        """Get agent run by ID."""
        return self.session.query(AgentRun).filter_by(id=run_id).first()


class FeedbackRepository(BaseRepository):
    """
    Repository for Feedback operations.
    """

    def create(self, feedback_data: Dict[str, Any]) -> Feedback:
        """Create a new feedback entry."""
        feedback = Feedback(**feedback_data)
        self.session.add(feedback)
        self.session.commit()
        self.session.refresh(feedback)
        return feedback

    def get_by_indicator(self, indicator_id: int) -> Optional[Feedback]:
        """Get feedback for an indicator."""
        return self.session.query(Feedback).filter_by(indicator_id=indicator_id).first()

    def get_all(self, limit: int = 100) -> List[Feedback]:
        """Get all feedback entries."""
        return self.session.query(Feedback).limit(limit).all()

    def count_by_type(self) -> Dict[str, int]:
        """Count feedback by type."""

        results = {}
        for feedback_type in FeedbackType:
            count = (
                self.session.query(Feedback)
                .filter_by(feedback_type=feedback_type)
                .count()
            )
            results[feedback_type.value] = count
        return results

    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Calculate precision, recall, F1 score, and confusion matrix.
        """

        # Get feedback grouped by type
        tp_feedback = (
            self.session.query(Feedback)
            .filter_by(feedback_type=FeedbackType.TRUE_POSITIVE)
            .all()
        )
        fp_feedback = (
            self.session.query(Feedback)
            .filter_by(feedback_type=FeedbackType.FALSE_POSITIVE)
            .all()
        )
        tn_feedback = (
            self.session.query(Feedback)
            .filter_by(feedback_type=FeedbackType.TRUE_NEGATIVE)
            .all()
        )
        fn_feedback = (
            self.session.query(Feedback)
            .filter_by(feedback_type=FeedbackType.FALSE_NEGATIVE)
            .all()
        )
        uncertain_feedback = (
            self.session.query(Feedback)
            .filter_by(feedback_type=FeedbackType.UNCERTAIN)
            .all()
        )

        # Aggregate confusion matrix counters from stored feedback types
        true_positives = len(tp_feedback)
        false_positives = len(fp_feedback)
        true_negatives = len(tn_feedback)
        false_negatives = len(fn_feedback)
        # uncertain_feedback is available but not counted into the main matrix

        # Calculate metrics
        total = true_positives + false_positives + true_negatives + false_negatives

        # Precision: Of all predicted threats, how many were actual threats?
        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives) > 0
            else 0
        )

        # Recall: Of all actual threats, how many did we catch?
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0
        )

        # F1 Score: Harmonic mean of precision and recall
        f1_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        # Accuracy: Overall correctness
        accuracy = (true_positives + true_negatives) / total if total > 0 else 0

        return {
            "total_feedback": total,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "true_negatives": true_negatives,
            "false_negatives": false_negatives,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "accuracy": round(accuracy, 4),
            "confusion_matrix": {
                "true_positive": true_positives,
                "false_positive": false_positives,
                "true_negative": true_negatives,
                "false_negative": false_negatives,
            },
        }
