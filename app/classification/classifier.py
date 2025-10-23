"""
Classification module for threat indicators.
Integrates LangGraph agent with storage and enrichment layers.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import get_settings
from app.langchain_graph.graph_builder import ThreatAnalysisAgent
from app.logging_config import get_logger
from app.storage.models import Classification, Indicator, RiskLevel
from app.storage.repository import ClassificationRepository, EnrichmentRepository

logger = get_logger(__name__)


class ThreatClassifier:
    """
    Classifier for threat indicators.
    Uses LangGraph agent to classify based on enrichment data.
    """

    def __init__(self, db_session: Any, model_name: Optional[str] = None):
        """
        Initialize the threat classifier.

        Args:
            db_session: Database session
            model_name: OpenAI model name (optional)
        """
        self.db_session = db_session
        self.classification_repo = ClassificationRepository(db_session)
        self.enrichment_repo = EnrichmentRepository(db_session)
        self.agent = ThreatAnalysisAgent(model_name=model_name)

        logger.info("Threat classifier initialized")

    async def classify_indicator(
        self, indicator: Indicator, store: bool = True
    ) -> Optional[Classification]:
        """
        Classify a threat indicator.

        Args:
            indicator: Indicator to classify
            store: Whether to store classification in database

        Returns:
            Classification object or None if classification fails
        """
        logger.info(f"Classifying indicator {indicator.id}: {indicator.value}")

        # Get enrichment data
        enrichments = self.enrichment_repo.get_by_indicator(indicator.id)

        if not enrichments:
            logger.warning(f"No enrichments found for indicator {indicator.id}")
            # Can still classify, but with limited data

        # Convert enrichments to dict format
        enrichment_data = [
            {
                "enrichment_type": e.enrichment_type,
                "provider": e.provider,
                "score": e.score,
                "success": e.success,
                "data": e.data,
                "error_message": e.error_message,
            }
            for e in enrichments
        ]

        # Run agent classification
        classification_result = await self.agent.classify_indicator(
            indicator, enrichment_data
        )

        if not classification_result:
            logger.error(f"Classification failed for indicator {indicator.id}")
            return None

        # Parse risk level (handle formats like "medium", "medium risk", "MEDIUM", etc.)
        risk_level_str = (
            classification_result.get("risk_level", "unknown").lower().strip()
        )
        # Remove " risk" suffix if present
        risk_level_str = risk_level_str.replace(" risk", "").replace("_risk", "")
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            logger.warning(
                f"Invalid risk level '{risk_level_str}', defaulting to UNKNOWN"
            )
            risk_level = RiskLevel.UNKNOWN

        # Create classification object
        classification = Classification(
            indicator_id=indicator.id,
            risk_level=risk_level,
            risk_score=classification_result.get("risk_score", 0.0),
            confidence=classification_result.get("confidence", 0.0),
            reasoning=classification_result.get("reasoning", ""),
            factors=classification_result.get("key_factors", []),
            model_name=classification_result.get("model"),
            model_version="1.0",
            classified_at=datetime.utcnow(),
        )

        # Store in database if requested
        if store:
            try:
                self.db_session.add(classification)
                self.db_session.commit()
                self.db_session.refresh(classification)
                logger.info(
                    f"Stored classification for indicator {indicator.id}: "
                    f"{risk_level.value} (score={classification.risk_score})"
                )
            except Exception as e:
                logger.error(f"Failed to store classification: {e}")
                self.db_session.rollback()
                return None

        return classification

    async def classify_batch(
        self, indicators: list[Indicator], store: bool = True
    ) -> Dict[int, Optional[Classification]]:
        """
        Classify multiple indicators.

        Args:
            indicators: List of indicators to classify
            store: Whether to store classifications

        Returns:
            Dictionary mapping indicator ID to Classification
        """
        logger.info(f"Batch classifying {len(indicators)} indicators")

        # Determine concurrency limit from settings (classification.concurrent_limit)
        try:
            settings = get_settings()
            limit = max(1, int(settings.classification.concurrent_limit))
        except Exception:
            limit = 10

        semaphore = asyncio.Semaphore(limit)

        async def _classify_task(ind: Indicator):
            async with semaphore:
                try:
                    # Run agent classification but avoid DB writes here to keep session safe
                    return ind, await self.classify_indicator(ind, store=False)
                except Exception as e:
                    logger.error(f"Failed to classify indicator {ind.id} (agent): {e}")
                    return ind, None

        # Launch tasks concurrently for agent calls
        tasks = [asyncio.create_task(_classify_task(ind)) for ind in indicators]
        gathered = await asyncio.gather(*tasks, return_exceptions=False)

        results: Dict[int, Optional[Classification]] = {}

        # If storage requested, perform DB writes sequentially using the classifier's session
        for ind, classification in gathered:
            if classification and store:
                try:
                    # Persist classification using the same DB session as before
                    self.db_session.add(classification)
                    self.db_session.commit()
                    self.db_session.refresh(classification)
                    results[ind.id] = classification
                    logger.info(
                        f"Stored classification for indicator {ind.id}: {classification.risk_level.value} (score={classification.risk_score})"
                    )
                except Exception as e:
                    logger.error(f"Failed to store classification for {ind.id}: {e}")
                    try:
                        self.db_session.rollback()
                    except Exception:
                        pass
                    results[ind.id] = None
            else:
                results[ind.id] = classification

        successful = sum(1 for c in results.values() if c is not None)
        logger.info(
            f"Batch classification complete: {successful}/{len(indicators)} successful"
        )

        return results

    def get_classification_summary(self, indicator_id: int) -> Dict[str, Any]:
        """
        Get classification summary for an indicator.

        Args:
            indicator_id: Indicator ID

        Returns:
            Summary dictionary
        """
        classification = self.classification_repo.get_by_indicator(indicator_id)

        if not classification:
            return {
                "has_classification": False,
                "risk_level": None,
                "risk_score": None,
            }

        return {
            "has_classification": True,
            "risk_level": classification.risk_level.value,
            "risk_score": classification.risk_score,
            "confidence": classification.confidence,
            "classified_at": classification.classified_at.isoformat(),
            "reasoning": classification.reasoning,
            "key_factors": classification.factors,
        }


async def classify_new_indicator(
    indicator: Indicator, db_session: Any
) -> Optional[Classification]:
    """
    Convenience function to classify a newly created indicator.

    Args:
        indicator: Newly created indicator
        db_session: Database session

    Returns:
        Classification object or None
    """
    classifier = ThreatClassifier(db_session)
    return await classifier.classify_indicator(indicator)
