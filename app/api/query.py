"""
FastAPI endpoints for querying indicators and enrichments.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.enrichment.orchestrator import EnrichmentOrchestrator
from app.logging_config import get_logger
from app.storage.db import get_db_session
from app.storage.models import IndicatorType, SourceType
from app.storage.repository import (
    ClassificationRepository,
    EnrichmentRepository,
    IndicatorRepository,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/indicators", tags=["indicators"])


# Pydantic models
class EnrichmentResponse(BaseModel):
    """Response model for enrichment data."""

    id: int
    enrichment_type: str
    provider: str
    score: Optional[float]
    success: bool
    enriched_at: str
    data: dict

    class Config:
        from_attributes = True


class IndicatorDetailResponse(BaseModel):
    """Detailed response model for indicator with enrichments."""

    id: int
    indicator_type: str
    value: str
    source_type: str
    source_name: Optional[str]
    created_at: str
    last_seen: str
    tags: List[str] = []
    notes: Optional[str]
    enrichments: List[EnrichmentResponse] = []
    classification: Optional[dict] = None  # Classification data if available

    class Config:
        from_attributes = True


class IndicatorListResponse(BaseModel):
    """Response model for indicator list."""

    total: int
    indicators: List[IndicatorDetailResponse]


@router.get("/", response_model=IndicatorListResponse)
async def list_indicators(
    limit: int = Query(
        default=50, ge=1, le=200, description="Maximum number of results"
    ),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    indicator_type: Optional[IndicatorType] = Query(
        default=None, description="Filter by type"
    ),
    source_type: Optional[SourceType] = Query(
        default=None, description="Filter by source"
    ),
    search: Optional[str] = Query(default=None, description="Search by value"),
    db: Session = Depends(get_db_session),
):
    """
    List all indicators with optional filtering.

    Query parameters:
    - limit: Maximum results (1-200)
    - offset: Pagination offset
    - indicator_type: Filter by type (domain, ip, hash, url, email)
    - source_type: Filter by source
    - search: Search indicators by value
    """
    try:
        repo = IndicatorRepository(db)
        enrichment_repo = EnrichmentRepository(db)
        classification_repo = ClassificationRepository(db)

        # Search or list
        if search:
            indicators = repo.search(search, limit=limit)
            total = len(indicators)
        else:
            indicators = repo.get_all(
                limit=limit,
                offset=offset,
                indicator_type=indicator_type,
                source_type=source_type,
            )
            total = repo.count(indicator_type=indicator_type, source_type=source_type)

        # Build response with enrichments and classifications
        result = []
        for indicator in indicators:
            enrichments = enrichment_repo.get_by_indicator(indicator.id)
            classification = classification_repo.get_by_indicator(indicator.id)

            enrichment_data = [
                EnrichmentResponse(
                    id=e.id,
                    enrichment_type=e.enrichment_type,
                    provider=e.provider,
                    score=e.score,
                    success=e.success,
                    enriched_at=e.enriched_at.isoformat(),
                    data=e.data,
                )
                for e in enrichments
            ]

            classification_data = None
            if classification:
                classification_data = {
                    "risk_level": classification.risk_level.value,
                    "risk_score": classification.risk_score,
                    "confidence": classification.confidence,
                    "classified_at": classification.classified_at.isoformat(),
                }

            result.append(
                IndicatorDetailResponse(
                    id=indicator.id,
                    indicator_type=indicator.indicator_type.value,
                    value=indicator.value,
                    source_type=indicator.source_type.value,
                    source_name=indicator.source_name,
                    created_at=indicator.created_at.isoformat(),
                    last_seen=indicator.last_seen.isoformat()
                    if indicator.last_seen
                    else indicator.created_at.isoformat(),
                    tags=indicator.tags or [],
                    notes=indicator.notes,
                    enrichments=enrichment_data,
                    classification=classification_data,
                )
            )

        return IndicatorListResponse(total=total, indicators=result)

    except Exception as e:
        logger.error(f"Failed to list indicators: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve indicators: {str(e)}",
        )


@router.get("/{indicator_id}", response_model=IndicatorDetailResponse)
async def get_indicator(indicator_id: int, db: Session = Depends(get_db_session)):
    """
    Get a specific indicator by ID with all enrichment data.
    """
    try:
        repo = IndicatorRepository(db)
        enrichment_repo = EnrichmentRepository(db)
        classification_repo = ClassificationRepository(db)

        indicator = repo.get_by_id(indicator_id)

        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Indicator {indicator_id} not found",
            )

        # Get enrichments
        enrichments = enrichment_repo.get_by_indicator(indicator.id)

        enrichment_data = [
            EnrichmentResponse(
                id=e.id,
                enrichment_type=e.enrichment_type,
                provider=e.provider,
                score=e.score,
                success=e.success,
                enriched_at=e.enriched_at.isoformat(),
                data=e.data,
            )
            for e in enrichments
        ]
        # Attach classification data if available (so UI can show feedback buttons)
        classification_data = None
        classification = classification_repo.get_by_indicator(indicator.id)
        if classification:
            classification_data = {
                "risk_level": classification.risk_level.value,
                "risk_score": classification.risk_score,
                "confidence": classification.confidence,
                "classified_at": classification.classified_at.isoformat(),
            }

        return IndicatorDetailResponse(
            id=indicator.id,
            indicator_type=indicator.indicator_type.value,
            value=indicator.value,
            source_type=indicator.source_type.value,
            source_name=indicator.source_name,
            created_at=indicator.created_at.isoformat(),
            last_seen=indicator.last_seen.isoformat()
            if indicator.last_seen
            else indicator.created_at.isoformat(),
            tags=indicator.tags or [],
            notes=indicator.notes,
            enrichments=enrichment_data,
            classification=classification_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get indicator {indicator_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve indicator: {str(e)}",
        )


@router.post("/{indicator_id}/enrich")
async def enrich_indicator(indicator_id: int, db: Session = Depends(get_db_session)):
    """
    Manually trigger enrichment for a specific indicator.
    Useful for re-enriching or enriching indicators that were ingested without enrichment.
    """
    try:
        repo = IndicatorRepository(db)
        indicator = repo.get_by_id(indicator_id)

        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Indicator {indicator_id} not found",
            )

        # Create orchestrator and enrich
        orchestrator = EnrichmentOrchestrator(db)
        results = await orchestrator.enrich_indicator(indicator)

        # Get summary
        summary = orchestrator.get_enrichment_summary(indicator_id)

        return {
            "success": True,
            "message": f"Enriched indicator {indicator_id}",
            "indicator_value": indicator.value,
            "indicator_type": indicator.indicator_type.value,
            "enrichments_performed": len(results),
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enrich indicator {indicator_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enrich indicator: {str(e)}",
        )


@router.get("/{indicator_id}/enrichments")
async def get_indicator_enrichments(
    indicator_id: int, db: Session = Depends(get_db_session)
):
    """
    Get all enrichments for a specific indicator.
    """
    try:
        repo = IndicatorRepository(db)
        indicator = repo.get_by_id(indicator_id)

        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Indicator {indicator_id} not found",
            )

        enrichment_repo = EnrichmentRepository(db)
        enrichments = enrichment_repo.get_by_indicator(indicator_id)

        orchestrator = EnrichmentOrchestrator(db)
        summary = orchestrator.get_enrichment_summary(indicator_id)

        enrichment_data = [
            {
                "id": e.id,
                "enrichment_type": e.enrichment_type,
                "provider": e.provider,
                "score": e.score,
                "success": e.success,
                "enriched_at": e.enriched_at.isoformat(),
                "data": e.data,
                "error_message": e.error_message,
            }
            for e in enrichments
        ]

        return {
            "indicator_id": indicator_id,
            "indicator_value": indicator.value,
            "enrichments": enrichment_data,
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get enrichments for indicator {indicator_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve enrichments: {str(e)}",
        )
