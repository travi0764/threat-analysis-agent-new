# """
# FastAPI endpoints for data ingestion.
# Handles CSV uploads and manual indicator submission.
# """

# from typing import Optional, List
# from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
# from pydantic import BaseModel, Field
# from sqlalchemy.orm import Session

# from app.storage.db import get_db_session
# from app.storage.repository import IndicatorRepository
# from app.ingestion.csv_ingestor import CSVIngestor
# from app.storage.models import IndicatorType, SourceType
# from app.utils.helpers import detect_indicator_type, normalize_indicator
# from app.enrichment.orchestrator import EnrichmentOrchestrator
# from app.classification.classifier import ThreatClassifier
# from app.logging_config import get_logger
# import asyncio

# logger = get_logger(__name__)
# router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


# # Pydantic models for request/response
# class ManualIndicatorRequest(BaseModel):
#     """Request model for manual indicator submission."""
#     value: str = Field(..., description="Indicator value")
#     indicator_type: Optional[IndicatorType] = Field(None, description="Type of indicator")
#     source: str = Field(default="manual", description="Source name")
#     source_url: Optional[str] = Field(None, description="Source URL")
#     tags: Optional[List[str]] = Field(default=[], description="Tags")
#     notes: Optional[str] = Field(None, description="Additional notes")


# class IndicatorResponse(BaseModel):
#     """Response model for indicator."""
#     id: int
#     indicator_type: str
#     value: str
#     source_type: str
#     source_name: Optional[str]
#     created_at: str

#     class Config:
#         from_attributes = True


# class IngestionResponse(BaseModel):
#     """Response model for ingestion operations."""
#     success: bool
#     message: str
#     indicators_processed: int
#     indicators_created: int
#     indicators_updated: int
#     indicators_failed: int
#     errors: List[dict] = []


# @router.post("/upload-csv", response_model=IngestionResponse)
# async def upload_csv(
#     file: UploadFile = File(..., description="CSV file with threat indicators"),
#     enrich: bool = True,
#     classify: bool = True,
#     db: Session = Depends(get_db_session)
# ):
#     """
#     Upload a CSV file with threat indicators.

#     Expected CSV format:
#     ```
#     value,indicator_type,source,tags,notes
#     evil-domain.com,domain,manual,phishing,Reported by user
#     192.0.2.1,ip,feed,suspicious,High traffic
#     ```

#     Or simplified format (auto-detect type):
#     ```
#     value,source,tags,notes
#     evil-domain.com,manual,phishing,Reported by user
#     ```

#     Args:
#         file: CSV file to upload
#         enrich: Whether to enrich indicators after ingestion (default: True)
#         classify: Whether to classify indicators after enrichment (default: True)
#         db: Database session

#     Returns statistics about the ingestion process.
#     """
#     logger.info(f"Received CSV upload: {file.filename}")

#     # Validate file type
#     if not file.filename.endswith('.csv'):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="File must be a CSV file (.csv extension)"
#         )

#     # Validate file size (max 10MB)
#     MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
#     content = await file.read()

#     if len(content) > MAX_FILE_SIZE:
#         raise HTTPException(
#             status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
#             detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / 1024 / 1024}MB"
#         )

#     try:
#         # Create CSV ingestor
#         ingestor = CSVIngestor(
#             source_name=file.filename,
#             auto_detect_type=True,
#             skip_duplicates=True
#         )

#         # Validate CSV format
#         if not ingestor.validate(content):
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Invalid CSV format. Must contain at least 'value' column."
#             )

#         # Ingest the data
#         result = ingestor.ingest(content, db)

#         # Trigger enrichment and classification for newly created indicators
#         if result.indicators_created > 0:
#             # Get newly created indicators
#             repo = IndicatorRepository(db)
#             recent_indicators = repo.get_all(limit=result.indicators_created, order_by="created_at", order_dir="desc")

#             if enrich:
#                 logger.info(f"Triggering enrichment for {result.indicators_created} new indicators")

#                 try:
#                     # Enrich
#                     orchestrator = EnrichmentOrchestrator(db)
#                     await orchestrator.enrich_indicators_batch(recent_indicators)
#                     logger.info(f"Enrichment complete for {len(recent_indicators)} indicators")

#                     # Classify if requested
#                     if classify:
#                         logger.info(f"Triggering classification for {len(recent_indicators)} indicators")
#                         try:
#                             classifier = ThreatClassifier(db)
#                             await classifier.classify_batch(recent_indicators, store=True)
#                             logger.info(f"Classification complete for {len(recent_indicators)} indicators")
#                         except Exception as e:
#                             logger.error(f"Failed to classify indicators: {e}")
#                             # Don't fail the whole operation

#                 except Exception as e:
#                     logger.error(f"Failed to enrich/classify indicators: {e}")
#                     # Don't fail the whole operation if enrichment fails

#         # Prepare response
#         response = IngestionResponse(
#             success=result.success,
#             message=f"Processed {result.indicators_processed} indicators from {file.filename}",
#             indicators_processed=result.indicators_processed,
#             indicators_created=result.indicators_created,
#             indicators_updated=result.indicators_updated,
#             indicators_failed=result.indicators_failed,
#             errors=result.errors[:10]  # Limit errors in response
#         )

#         logger.info(
#             f"CSV ingestion complete: {result.indicators_created} created, "
#             f"{result.indicators_updated} updated, {result.indicators_failed} failed"
#         )

#         return response

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"CSV ingestion failed: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to process CSV file: {str(e)}"
#         )


# @router.post("/manual", response_model=IndicatorResponse, status_code=status.HTTP_201_CREATED)
# async def submit_manual_indicator(
#     request: ManualIndicatorRequest,
#     db: Session = Depends(get_db_session)
# ):
#     """
#     Submit a single indicator manually.

#     Useful for quick indicator submission without uploading a CSV file.
#     """
#     logger.info(f"Received manual indicator: {request.value}")

#     try:
#         # Detect indicator type if not provided
#         if request.indicator_type is None:
#             try:
#                 indicator_type = detect_indicator_type(request.value)
#             except Exception as e:
#                 raise HTTPException(
#                     status_code=status.HTTP_400_BAD_REQUEST,
#                     detail=f"Could not detect indicator type: {str(e)}"
#                 )
#         else:
#             indicator_type = request.indicator_type

#         # Normalize the indicator value
#         normalized_value = normalize_indicator(request.value, indicator_type)

#         # Check for duplicates
#         repo = IndicatorRepository(db)
#         existing = repo.get_by_value(normalized_value)

#         if existing:
#             raise HTTPException(
#                 status_code=status.HTTP_409_CONFLICT,
#                 detail=f"Indicator already exists with ID: {existing.id}"
#             )

#         # Create indicator
#         indicator_data = {
#             "indicator_type": indicator_type,
#             "value": normalized_value,
#             "source_type": SourceType.MANUAL,
#             "source_name": request.source,
#             "source_url": request.source_url,
#             "tags": request.tags,
#             "notes": request.notes,
#         }

#         indicator = repo.create(indicator_data)

#         logger.info(f"Created manual indicator: {indicator.value} (ID: {indicator.id})")

#         return IndicatorResponse(
#             id=indicator.id,
#             indicator_type=indicator.indicator_type.value,
#             value=indicator.value,
#             source_type=indicator.source_type.value,
#             source_name=indicator.source_name,
#             created_at=indicator.created_at.isoformat()
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Failed to create manual indicator: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to create indicator: {str(e)}"
#         )


# @router.get("/stats")
# async def get_ingestion_stats(db: Session = Depends(get_db_session)):
#     """
#     Get ingestion statistics.

#     Returns counts by indicator type and source type.
#     """
#     try:
#         repo = IndicatorRepository(db)

#         # Count by indicator type
#         type_counts = {}
#         for itype in IndicatorType:
#             count = repo.count(indicator_type=itype)
#             type_counts[itype.value] = count

#         # Count by source type
#         source_counts = {}
#         for stype in SourceType:
#             count = repo.count(source_type=stype)
#             source_counts[stype.value] = count

#         # Total count
#         total = repo.count()

#         return {
#             "total_indicators": total,
#             "by_type": type_counts,
#             "by_source": source_counts
#         }

#     except Exception as e:
#         logger.error(f"Failed to get ingestion stats: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to retrieve statistics: {str(e)}"
#         )


# =====================================================================
# =====================================================================
# =====================================================================


"""
FastAPI endpoints for data ingestion.
Handles CSV/JSON uploads and manual indicator submission.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.classification.classifier import ThreatClassifier
from app.enrichment.orchestrator import EnrichmentOrchestrator
from app.ingestion.csv_ingestor import CSVIngestor
from app.ingestion.json_ingestor import JSONIngestor
from app.logging_config import get_logger
from app.storage.db import get_db_session
from app.storage.models import IndicatorType, SourceType
from app.storage.repository import IndicatorRepository
from app.utils.helpers import detect_indicator_type, normalize_indicator

logger = get_logger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


# Pydantic models for request/response
class ManualIndicatorRequest(BaseModel):
    """Request model for manual indicator submission."""

    value: str = Field(..., description="Indicator value")
    indicator_type: Optional[str] = Field(
        None, description="Type of indicator (auto-detect if not provided)"
    )
    source: str = Field(default="manual", description="Source name")
    source_url: Optional[str] = Field(None, description="Source URL")
    tags: Optional[List[str]] = Field(default=[], description="Tags")
    notes: Optional[str] = Field(None, description="Additional notes")


class IndicatorResponse(BaseModel):
    """Response model for indicator."""

    id: int
    indicator_type: str
    value: str
    source_type: str
    source_name: Optional[str]
    created_at: str
    enriched: bool = False
    classified: bool = False
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None

    class Config:
        from_attributes = True


class IngestionResponse(BaseModel):
    """Response model for ingestion operations."""

    success: bool
    message: str
    indicators_processed: int
    indicators_created: int
    indicators_updated: int
    indicators_failed: int
    errors: List[dict] = []


@router.post("/upload-csv", response_model=IngestionResponse)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with threat indicators"),
    enrich: bool = True,
    classify: bool = True,
    db: Session = Depends(get_db_session),
):
    """
    Upload a CSV file with threat indicators.

    Expected CSV format:
    ```
    value,indicator_type,source,tags,notes
    evil-domain.com,domain,manual,phishing,Reported by user
    192.0.2.1,ip,feed,suspicious,High traffic
    ```

    Or simplified format (auto-detect type):
    ```
    value,source,tags,notes
    evil-domain.com,manual,phishing,Reported by user
    ```

    Args:
        file: CSV file to upload
        enrich: Whether to enrich indicators after ingestion (default: True)
        classify: Whether to classify indicators after enrichment (default: True)
        db: Database session

    Returns statistics about the ingestion process.
    """
    logger.info(f"Received CSV upload: {file.filename}")

    # Validate file type
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file (.csv extension)",
        )

    # Validate file size (max 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / 1024 / 1024}MB",
        )

    try:
        # Create CSV ingestor
        ingestor = CSVIngestor(
            source_name=file.filename, auto_detect_type=True, skip_duplicates=True
        )

        # Validate CSV format
        if not ingestor.validate(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CSV format. Must contain at least 'value' column.",
            )

        # Ingest the data
        result = ingestor.ingest(content, db)

        # Trigger enrichment and classification for newly created indicators
        if result.indicators_created > 0:
            # Get newly created indicators
            repo = IndicatorRepository(db)
            recent_indicators = repo.get_all(
                limit=result.indicators_created, order_by="created_at", order_dir="desc"
            )

            if enrich:
                logger.info(
                    f"Triggering enrichment for {result.indicators_created} new indicators"
                )

                try:
                    # Enrich
                    orchestrator = EnrichmentOrchestrator(db)
                    await orchestrator.enrich_indicators_batch(recent_indicators)
                    logger.info(
                        f"Enrichment complete for {len(recent_indicators)} indicators"
                    )

                    # Classify if requested
                    if classify:
                        logger.info(
                            f"Triggering classification for {len(recent_indicators)} indicators"
                        )
                        try:
                            classifier = ThreatClassifier(db)
                            await classifier.classify_batch(
                                recent_indicators, store=True
                            )
                            logger.info(
                                f"Classification complete for {len(recent_indicators)} indicators"
                            )
                        except Exception as e:
                            logger.error(f"Failed to classify indicators: {e}")
                            # Don't fail the whole operation

                except Exception as e:
                    logger.error(f"Failed to enrich/classify indicators: {e}")
                    # Don't fail the whole operation if enrichment fails

        # Prepare response
        response = IngestionResponse(
            success=result.success,
            message=f"Processed {result.indicators_processed} indicators from {file.filename}",
            indicators_processed=result.indicators_processed,
            indicators_created=result.indicators_created,
            indicators_updated=result.indicators_updated,
            indicators_failed=result.indicators_failed,
            errors=result.errors[:10],  # Limit errors in response
        )

        logger.info(
            f"CSV ingestion complete: {result.indicators_created} created, "
            f"{result.indicators_updated} updated, {result.indicators_failed} failed"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process CSV file: {str(e)}",
        )


@router.post("/upload-json", response_model=IngestionResponse)
async def upload_json(
    file: UploadFile = File(..., description="JSON file with threat indicators"),
    enrich: bool = True,
    classify: bool = True,
    db: Session = Depends(get_db_session),
):
    """
    Upload a JSON file with threat indicators.

    Expected JSON formats:

    1. Array of objects:
    ```json
    [
        {
            "value": "evil-domain.com",
            "indicator_type": "domain",
            "source": "manual",
            "tags": ["phishing", "malware"],
            "notes": "Reported by user"
        }
    ]
    ```

    2. Single object:
    ```json
    {
        "value": "192.0.2.1",
        "indicator_type": "ip",
        "source": "feed"
    }
    ```

    3. Nested structure:
    ```json
    {
        "indicators": [...]
    }
    ```

    Args:
        file: JSON file to upload
        enrich: Whether to enrich indicators after ingestion
        classify: Whether to classify indicators after enrichment
        db: Database session

    Returns statistics about the ingestion process.
    """
    logger.info(f"Received JSON upload: {file.filename}")

    # Validate file type
    if not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a JSON file (.json extension)",
        )

    # Validate file size (max 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / 1024 / 1024}MB",
        )

    try:
        # Create JSON ingestor
        ingestor = JSONIngestor(
            source_name=file.filename, auto_detect_type=True, skip_duplicates=True
        )

        # Validate JSON format
        if not ingestor.validate(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON format. Must contain at least one indicator with 'value' field.",
            )

        # Ingest the data
        result = ingestor.ingest(content, db)

        # Trigger enrichment and classification for newly created indicators
        if result.indicators_created > 0:
            # Get newly created indicators
            repo = IndicatorRepository(db)
            recent_indicators = repo.get_all(
                limit=result.indicators_created, order_by="created_at", order_dir="desc"
            )

            if enrich:
                logger.info(
                    f"Triggering enrichment for {result.indicators_created} new indicators"
                )

                try:
                    # Enrich
                    orchestrator = EnrichmentOrchestrator(db)
                    await orchestrator.enrich_indicators_batch(recent_indicators)
                    logger.info(
                        f"Enrichment complete for {len(recent_indicators)} indicators"
                    )

                    # Classify if requested
                    if classify:
                        logger.info(
                            f"Triggering classification for {len(recent_indicators)} indicators"
                        )
                        try:
                            classifier = ThreatClassifier(db)
                            await classifier.classify_batch(
                                recent_indicators, store=True
                            )
                            logger.info(
                                f"Classification complete for {len(recent_indicators)} indicators"
                            )
                        except Exception as e:
                            logger.error(f"Failed to classify indicators: {e}")
                            # Don't fail the whole operation

                except Exception as e:
                    logger.error(f"Failed to enrich/classify indicators: {e}")
                    # Don't fail the whole operation if enrichment fails

        # Prepare response
        response = IngestionResponse(
            success=result.success,
            message=f"Processed {result.indicators_processed} indicators from {file.filename}",
            indicators_processed=result.indicators_processed,
            indicators_created=result.indicators_created,
            indicators_updated=result.indicators_updated,
            indicators_failed=result.indicators_failed,
            errors=result.errors[:10],  # Limit errors in response
        )

        logger.info(
            f"JSON ingestion complete: {result.indicators_created} created, "
            f"{result.indicators_updated} updated, {result.indicators_failed} failed"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JSON ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process JSON file: {str(e)}",
        )


@router.post(
    "/submit", response_model=IndicatorResponse, status_code=status.HTTP_201_CREATED
)
async def submit_single_indicator(
    request: ManualIndicatorRequest,
    enrich: bool = True,
    classify: bool = True,
    db: Session = Depends(get_db_session),
):
    """
    Submit a single indicator manually.

    Useful for quick indicator submission without uploading a file.
    Supports auto-enrichment and auto-classification.

    Args:
        request: Indicator data
        enrich: Whether to enrich the indicator
        classify: Whether to classify the indicator
        db: Database session
    """
    logger.info(f"Received single indicator: {request.value}")

    try:
        # Detect indicator type if not provided or if "auto"
        if request.indicator_type is None or request.indicator_type.lower() == "auto":
            try:
                indicator_type = detect_indicator_type(request.value)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not detect indicator type: {str(e)}. Please specify the type explicitly.",
                )
        else:
            try:
                indicator_type = IndicatorType(request.indicator_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid indicator type: {request.indicator_type}. Must be one of: domain, ip, hash, url, email",
                )

        # Normalize the indicator value
        normalized_value = normalize_indicator(request.value, indicator_type)

        # Check for duplicates
        repo = IndicatorRepository(db)
        existing = repo.get_by_value(normalized_value)

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Indicator already exists with ID: {existing.id}",
            )

        # Create indicator
        indicator_data = {
            "indicator_type": indicator_type,
            "value": normalized_value,
            "source_type": SourceType.MANUAL,
            "source_name": request.source,
            "source_url": request.source_url,
            "tags": request.tags if request.tags else [],
            "notes": request.notes,
        }

        indicator = repo.create(indicator_data)
        logger.info(f"Created manual indicator: {indicator.value} (ID: {indicator.id})")

        # Initialize response
        response_data = {
            "id": indicator.id,
            "indicator_type": indicator.indicator_type.value,
            "value": indicator.value,
            "source_type": indicator.source_type.value,
            "source_name": indicator.source_name,
            "created_at": indicator.created_at.isoformat(),
            "enriched": False,
            "classified": False,
            "risk_level": None,
            "risk_score": None,
        }

        # Enrich if requested
        if enrich:
            try:
                logger.info(f"Enriching indicator {indicator.id}")
                orchestrator = EnrichmentOrchestrator(db)
                await orchestrator.enrich_indicator(indicator)
                response_data["enriched"] = True
                logger.info(f"Enrichment complete for indicator {indicator.id}")
            except Exception as e:
                logger.error(f"Failed to enrich indicator {indicator.id}: {e}")
                # Continue even if enrichment fails

        # Classify if requested
        if classify:
            try:
                logger.info(f"Classifying indicator {indicator.id}")
                classifier = ThreatClassifier(db)
                classification = await classifier.classify_indicator(
                    indicator, store=True
                )

                if classification:
                    response_data["classified"] = True
                    response_data["risk_level"] = classification.risk_level.value
                    response_data["risk_score"] = classification.risk_score
                    logger.info(
                        f"Classification complete for indicator {indicator.id}: "
                        f"{classification.risk_level.value} (score={classification.risk_score})"
                    )
            except Exception as e:
                logger.error(f"Failed to classify indicator {indicator.id}: {e}")
                # Continue even if classification fails

        return IndicatorResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create indicator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create indicator: {str(e)}",
        )


@router.get("/stats")
async def get_ingestion_stats(db: Session = Depends(get_db_session)):
    """
    Get ingestion statistics.

    Returns counts by indicator type and source type.
    """
    try:
        repo = IndicatorRepository(db)

        # Count by indicator type
        type_counts = {}
        for itype in IndicatorType:
            count = repo.count(indicator_type=itype)
            type_counts[itype.value] = count

        # Count by source type
        source_counts = {}
        for stype in SourceType:
            count = repo.count(source_type=stype)
            source_counts[stype.value] = count

        # Total count
        total = repo.count()

        return {
            "total_indicators": total,
            "by_type": type_counts,
            "by_source": source_counts,
        }

    except Exception as e:
        logger.error(f"Failed to get ingestion stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}",
        )
