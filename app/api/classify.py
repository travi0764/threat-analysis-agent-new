"""
FastAPI endpoints for classification operations.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.classification.classifier import ThreatClassifier
from app.logging_config import get_logger
from app.storage.db import get_db_session
from app.storage.models import RiskLevel
from app.storage.repository import ClassificationRepository, IndicatorRepository

logger = get_logger(__name__)
router = APIRouter(prefix="/api/classify", tags=["classification"])


# Pydantic models
class ClassificationResponse(BaseModel):
    """Response model for classification."""

    indicator_id: int
    indicator_value: str
    risk_level: str
    risk_score: float
    confidence: float
    reasoning: str
    key_factors: list[str]
    model_name: Optional[str]
    classified_at: str

    class Config:
        from_attributes = True


class ClassificationStatsResponse(BaseModel):
    """Response model for classification statistics."""

    total_classified: int
    by_risk_level: dict


@router.post("/{indicator_id}", response_model=ClassificationResponse)
async def classify_indicator(
    indicator_id: int,
    force: bool = Query(
        default=False, description="Force reclassification if already classified"
    ),
    db: Session = Depends(get_db_session),
):
    """
    Classify a specific indicator using the LangGraph agent.

    Args:
        indicator_id: ID of indicator to classify
        force: Force reclassification even if already classified

    Returns:
        Classification result
    """
    try:
        repo = IndicatorRepository(db)
        classification_repo = ClassificationRepository(db)

        # Get indicator
        indicator = repo.get_by_id(indicator_id)
        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Indicator {indicator_id} not found",
            )

        # Check if already classified
        existing = classification_repo.get_by_indicator(indicator_id)
        if existing and not force:
            logger.info(
                f"Indicator {indicator_id} already classified, returning existing"
            )
            return ClassificationResponse(
                indicator_id=indicator.id,
                indicator_value=indicator.value,
                risk_level=existing.risk_level.value,
                risk_score=existing.risk_score,
                confidence=existing.confidence,
                reasoning=existing.reasoning,
                key_factors=existing.factors or [],
                model_name=existing.model_name,
                classified_at=existing.classified_at.isoformat(),
            )

        # Classify
        logger.info(f"Classifying indicator {indicator_id}: {indicator.value}")
        classifier = ThreatClassifier(db)
        classification = await classifier.classify_indicator(indicator, store=True)

        if not classification:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Classification failed",
            )

        return ClassificationResponse(
            indicator_id=indicator.id,
            indicator_value=indicator.value,
            risk_level=classification.risk_level.value,
            risk_score=classification.risk_score,
            confidence=classification.confidence,
            reasoning=classification.reasoning,
            key_factors=classification.factors or [],
            model_name=classification.model_name,
            classified_at=classification.classified_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to classify indicator {indicator_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Classification failed: {str(e)}",
        )


@router.post("/batch", response_model=dict)
async def classify_batch(
    indicator_ids: list[int],
    force: bool = Query(default=False, description="Force reclassification"),
    db: Session = Depends(get_db_session),
):
    """
    Classify multiple indicators in batch.

    Args:
        indicator_ids: List of indicator IDs to classify
        force: Force reclassification

    Returns:
        Batch classification results
    """
    try:
        if len(indicator_ids) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 50 indicators per batch",
            )

        repo = IndicatorRepository(db)

        # Get indicators
        indicators = [repo.get_by_id(iid) for iid in indicator_ids]
        indicators = [i for i in indicators if i is not None]

        if not indicators:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No valid indicators found",
            )

        logger.info(f"Batch classifying {len(indicators)} indicators")

        # Classify
        classifier = ThreatClassifier(db)
        results = await classifier.classify_batch(indicators, store=True)

        # Format response
        successful = sum(1 for c in results.values() if c is not None)
        failed = len(results) - successful

        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": {
                iid: {
                    "success": c is not None,
                    "risk_level": c.risk_level.value if c else None,
                    "risk_score": c.risk_score if c else None,
                }
                for iid, c in results.items()
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch classification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch classification failed: {str(e)}",
        )


@router.get("/stats", response_model=ClassificationStatsResponse)
async def get_classification_stats(db: Session = Depends(get_db_session)):
    """
    Get classification statistics.

    Returns:
        Statistics about classifications
    """
    try:
        repo = ClassificationRepository(db)

        by_risk = repo.count_by_risk()
        total = sum(by_risk.values())

        return ClassificationStatsResponse(
            total_classified=total, by_risk_level=by_risk
        )

    except Exception as e:
        logger.error(f"Failed to get classification stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}",
        )


@router.get("/risk/{risk_level}")
async def get_by_risk_level(
    risk_level: RiskLevel,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
):
    """
    Get indicators by risk level.

    Args:
        risk_level: Risk level to filter (high, medium, low, unknown)
        limit: Maximum results

    Returns:
        List of indicators with specified risk level
    """
    try:
        classification_repo = ClassificationRepository(db)
        indicator_repo = IndicatorRepository(db)

        classifications = classification_repo.get_by_risk_level(risk_level, limit=limit)

        results = []
        for classification in classifications:
            indicator = indicator_repo.get_by_id(classification.indicator_id)
            if indicator:
                results.append(
                    {
                        "indicator_id": indicator.id,
                        "indicator_value": indicator.value,
                        "indicator_type": indicator.indicator_type.value,
                        "risk_level": classification.risk_level.value,
                        "risk_score": classification.risk_score,
                        "confidence": classification.confidence,
                        "classified_at": classification.classified_at.isoformat(),
                    }
                )

        return {
            "risk_level": risk_level.value,
            "count": len(results),
            "indicators": results,
        }

    except Exception as e:
        logger.error(f"Failed to get indicators by risk level: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve indicators: {str(e)}",
        )
