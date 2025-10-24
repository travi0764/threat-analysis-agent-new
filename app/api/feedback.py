"""
FastAPI endpoints for feedback and metrics.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.storage.db import get_db_session
from app.storage.models import FeedbackType, RiskLevel
from app.storage.repository import (
    ClassificationRepository,
    FeedbackRepository,
    IndicatorRepository,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# Pydantic models
class FeedbackRequest(BaseModel):
    """Request model for submitting feedback."""

    indicator_id: int
    feedback_type: str = Field(description="'correct' or 'incorrect'")
    corrected_risk_level: Optional[str] = Field(
        None, description="Corrected risk level if incorrect"
    )
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    success: bool
    message: str
    feedback_id: int


class MetricsResponse(BaseModel):
    """Response model for metrics."""

    total_feedback: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    confusion_matrix: dict


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackRequest, db: Session = Depends(get_db_session)
):
    """
    Submit feedback on a classification.

    Args:
        feedback: Feedback data (thumbs up/down)

    Returns:
        Feedback confirmation
    """
    try:
        indicator_repo = IndicatorRepository(db)
        classification_repo = ClassificationRepository(db)
        feedback_repo = FeedbackRepository(db)

        # Verify indicator exists
        indicator = indicator_repo.get_by_id(feedback.indicator_id)
        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Indicator {feedback.indicator_id} not found",
            )

        # Get classification
        classification = classification_repo.get_by_indicator(feedback.indicator_id)
        if not classification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No classification found for indicator {feedback.indicator_id}",
            )

        # Parse feedback type (UI sends 'correct'/'incorrect') and map
        # to the stored FeedbackType enum (true/false positive/negative).
        #
        # Definitions used here:
        # - True Positive (TP): Model predicted a threat (HIGH/MEDIUM) and the user agrees (feedback 'correct').
        # - True Negative (TN): Model predicted benign (LOW) and the user agrees (feedback 'correct').
        # - False Positive (FP): Model predicted a threat (HIGH/MEDIUM) but the user says it's incorrect (user indicates benign).
        # - False Negative (FN): Model predicted benign (LOW) but the user says it's incorrect (user indicates it is a threat).
        #
        # Example scenarios:
        # - Model risk LOW, user clicks 'incorrect' and provides corrected_risk_level='high' -> FALSE_NEGATIVE
        #   (model missed a threat).
        # - Model risk HIGH, user clicks 'incorrect' and provides corrected_risk_level='low' -> FALSE_POSITIVE
        #   (model incorrectly flagged benign as threat).
        # - If the user clicks 'correct', we mark TP when original was HIGH/MEDIUM, TN when LOW.
        # - If no corrected_risk_level is provided with 'incorrect', we infer the direction:
        #     * original HIGH/MEDIUM -> assume user means benign -> FALSE_POSITIVE
        #     * original LOW -> assume user means threat -> FALSE_NEGATIVE
        #
        # Keep mapping logic explicit and defensive: if corrected_risk_level is provided but doesn't
        # allow a clear FP/FN decision, record as UNCERTAIN.
        feedback_type_str = feedback.feedback_type.lower()
        original_level = classification.risk_level

        # Helper to parse corrected risk level if provided
        corrected_level = None
        if feedback.corrected_risk_level:
            try:
                corrected_level = RiskLevel(feedback.corrected_risk_level.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid risk level: {feedback.corrected_risk_level}",
                )

        if feedback_type_str == "correct":
            # If model predicted HIGH/MEDIUM (threat) and user says correct -> true positive
            if original_level in [RiskLevel.HIGH, RiskLevel.MEDIUM]:
                feedback_type = FeedbackType.TRUE_POSITIVE
            else:
                feedback_type = FeedbackType.TRUE_NEGATIVE
        elif feedback_type_str == "incorrect":
            # If user marks incorrect, try to infer whether it was a false positive/negative
            if corrected_level is not None:
                # Use corrected_level to determine false positive vs false negative
                if (
                    original_level in [RiskLevel.HIGH, RiskLevel.MEDIUM]
                    and corrected_level == RiskLevel.LOW
                ):
                    feedback_type = FeedbackType.FALSE_POSITIVE
                elif original_level == RiskLevel.LOW and corrected_level in [
                    RiskLevel.HIGH,
                    RiskLevel.MEDIUM,
                ]:
                    feedback_type = FeedbackType.FALSE_NEGATIVE
                else:
                    feedback_type = FeedbackType.UNCERTAIN
            else:
                # No corrected level provided: infer from original
                if original_level in [RiskLevel.HIGH, RiskLevel.MEDIUM]:
                    feedback_type = FeedbackType.FALSE_POSITIVE
                else:
                    feedback_type = FeedbackType.FALSE_NEGATIVE
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="feedback_type must be 'correct' or 'incorrect'",
            )

        # Use corrected_level (parsed above) as the corrected risk level to store
        corrected_risk_level = corrected_level

        # Check if feedback already exists
        existing_feedback = feedback_repo.get_by_indicator(feedback.indicator_id)
        if existing_feedback:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feedback already exists for this indicator",
            )

        # Create feedback
        feedback_data = {
            "indicator_id": feedback.indicator_id,
            "original_risk_level": classification.risk_level,
            "feedback_type": feedback_type,
            "corrected_risk_level": corrected_risk_level,
            "comment": feedback.comment,
        }

        feedback_entry = feedback_repo.create(feedback_data)

        logger.info(
            f"Feedback submitted for indicator {feedback.indicator_id}: "
            f"{feedback_type.value}"
        )

        return FeedbackResponse(
            success=True,
            message="Feedback submitted successfully",
            feedback_id=feedback_entry.id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}",
        )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(db: Session = Depends(get_db_session)):
    """
    Get classification performance metrics.

    Returns:
        Precision, recall, F1 score, confusion matrix
    """
    try:
        feedback_repo = FeedbackRepository(db)
        metrics = feedback_repo.calculate_metrics()

        return MetricsResponse(**metrics)

    except Exception as e:
        logger.error(f"Failed to calculate metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate metrics: {str(e)}",
        )


@router.get("/stats")
async def get_feedback_stats(db: Session = Depends(get_db_session)):
    """
    Get feedback statistics.

    Returns:
        Counts by feedback type
    """
    try:
        feedback_repo = FeedbackRepository(db)

        counts = feedback_repo.count_by_type()
        total = sum(counts.values())

        # Compute 'correct' as TP + TN, 'incorrect' as FP + FN + UNCERTAIN
        correct_count = counts.get("true_positive", 0) + counts.get("true_negative", 0)
        incorrect_count = (
            counts.get("false_positive", 0)
            + counts.get("false_negative", 0)
            + counts.get("uncertain", 0)
        )

        return {
            "total_feedback": total,
            "by_type": counts,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "correct_percentage": (correct_count / total * 100) if total > 0 else 0,
            "incorrect_percentage": (incorrect_count / total * 100) if total > 0 else 0,
        }

    except Exception as e:
        logger.error(f"Failed to get feedback stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get feedback stats: {str(e)}",
        )


@router.get("/indicator/{indicator_id}")
async def get_indicator_feedback(
    indicator_id: int, db: Session = Depends(get_db_session)
):
    """
    Get feedback for a specific indicator.

    Args:
        indicator_id: Indicator ID

    Returns:
        Feedback data if exists
    """
    try:
        feedback_repo = FeedbackRepository(db)
        feedback = feedback_repo.get_by_indicator(indicator_id)

        if not feedback:
            return {"has_feedback": False, "indicator_id": indicator_id}

        return {
            "has_feedback": True,
            "indicator_id": indicator_id,
            "feedback_type": feedback.feedback_type.value,
            "original_risk_level": feedback.original_risk_level.value
            if feedback.original_risk_level
            else None,
            "corrected_risk_level": feedback.corrected_risk_level.value
            if feedback.corrected_risk_level
            else None,
            "comment": feedback.comment,
            "created_at": feedback.created_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get indicator feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get feedback: {str(e)}",
        )
