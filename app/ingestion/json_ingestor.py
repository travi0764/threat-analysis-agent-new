"""
JSON Ingestor for Threat Analysis Agent.
Handles JSON file parsing, validation, and normalization.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.ingestion.ingestor import BaseIngestor, IndicatorData, IngestionResult
from app.logging_config import get_logger
from app.storage.models import Indicator, IndicatorType, SourceType
from app.utils.exceptions import IngestionError, ValidationError
from app.utils.helpers import (
    detect_indicator_type,
    extract_indicator_value_and_type,
    normalize_indicator,
    sanitize_string,
    supported_indicator_fields,
)

logger = get_logger(__name__)


class JSONIngestor(BaseIngestor):
    """
    Ingestor for JSON files containing threat indicators.

    Expected JSON formats:

    1. Array of objects:
    [
        {
            "indicator_type": "domain",
            "value": "evil-domain.com",
            "source": "manual",
            "tags": ["phishing", "malware"],
            "notes": "Reported by user"
        }
    ]

    2. Single object:
    {
        "indicator_type": "ip",
        "value": "192.0.2.1",
        "source": "feed",
        "tags": ["suspicious"]
    }

    3. Nested structure:
    {
        "indicators": [...]
    }
    """

    # Maximum indicators to process
    MAX_INDICATORS = 10000

    def __init__(
        self,
        source_name: str = "json_upload",
        auto_detect_type: bool = True,
        skip_duplicates: bool = True,
    ):
        """
        Initialize JSON ingestor.

        Args:
            source_name: Name of the JSON source
            auto_detect_type: Auto-detect indicator type if not provided
            skip_duplicates: Skip duplicate indicators
        """
        super().__init__(SourceType.JSON_UPLOAD, source_name)
        self.auto_detect_type = auto_detect_type
        self.skip_duplicates = skip_duplicates

    def ingest(self, file_content: Any, db_session: Any) -> IngestionResult:
        """
        Ingest indicators from JSON file.

        Args:
            file_content: File content (bytes, str, or dict)
            db_session: Database session for storing indicators

        Returns:
            IngestionResult with statistics
        """
        result = IngestionResult(
            success=False,
            indicators_processed=0,
            indicators_created=0,
            indicators_updated=0,
            indicators_failed=0,
            errors=[],
            metadata={"source": self.source_name},
        )

        try:
            # Parse JSON content
            data = self._parse_json(file_content)

            if not data:
                raise IngestionError("JSON file is empty or has no valid data")

            # Extract indicators array
            indicators_data = self._extract_indicators(data)

            if not indicators_data:
                raise IngestionError("No indicators found in JSON")

            logger.info(f"Parsed {len(indicators_data)} indicators from JSON")

            # Check limit
            if len(indicators_data) > self.MAX_INDICATORS:
                logger.warning(
                    f"JSON has {len(indicators_data)} indicators, limiting to {self.MAX_INDICATORS}"
                )
                indicators_data = indicators_data[: self.MAX_INDICATORS]

            # Process each indicator
            for idx, indicator_dict in enumerate(indicators_data, start=1):
                result.indicators_processed += 1

                try:
                    # Normalize the indicator
                    indicator_data = self.normalize_indicator(indicator_dict)

                    if not indicator_data:
                        result.indicators_failed += 1
                        result.add_error(
                            idx,
                            "Failed to normalize indicator",
                            indicator_dict,
                        )
                        continue

                    # Check for duplicates
                    if self.skip_duplicates:
                        existing = (
                            db_session.query(Indicator)
                            .filter_by(value=indicator_data.value)
                            .first()
                        )

                        if existing:
                            existing.last_seen = datetime.utcnow()
                            db_session.commit()
                            result.indicators_updated += 1
                            logger.debug(
                                f"Updated existing indicator: {indicator_data.value}"
                            )
                            continue

                    # Create new indicator
                    indicator = Indicator(**indicator_data.to_dict())
                    db_session.add(indicator)
                    db_session.commit()

                    result.indicators_created += 1
                    logger.debug(
                        f"Created indicator: {indicator.value} ({indicator.indicator_type.value})"
                    )

                except Exception as e:
                    result.indicators_failed += 1
                    result.add_error(idx, str(e), indicator_dict)
                    logger.error(f"Error processing indicator {idx}: {e}")
                    db_session.rollback()
                    continue

            # Mark as successful if at least one indicator was created
            result.success = result.indicators_created > 0

            logger.info(
                f"JSON ingestion complete: {result.indicators_created} created, "
                f"{result.indicators_updated} updated, {result.indicators_failed} failed"
            )

        except Exception as e:
            result.success = False
            result.add_error(0, f"JSON ingestion failed: {str(e)}")
            logger.error(f"JSON ingestion failed: {e}")

        return result

    def validate(self, file_content: Any) -> bool:
        """
        Validate JSON file format.

        Args:
            file_content: File content to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            data = self._parse_json(file_content)

            if not data:
                return False

            # Extract indicators
            indicators = self._extract_indicators(data)

            # Check at least one indicator exists
            return len(indicators) > 0

        except Exception as e:
            logger.error(f"JSON validation failed: {e}")
            return False

    def normalize_indicator(
        self, raw_indicator: Dict[str, Any]
    ) -> Optional[IndicatorData]:
        """
        Normalize a JSON object into IndicatorData.

        Args:
            raw_indicator: Dictionary representing an indicator

        Returns:
            IndicatorData object or None if normalization fails
        """
        try:
            value, implied_type, value_field = extract_indicator_value_and_type(
                raw_indicator
            )

            if not value:
                supported = ", ".join(supported_indicator_fields())
                raise ValidationError(
                    f"Missing indicator value. Expected one of: {supported}"
                )

            # Sanitize indicator
            value = sanitize_string(value)

            detected_type = None
            detection_error = None
            if self.auto_detect_type:
                try:
                    detected_type = detect_indicator_type(value)
                except ValidationError as exc:
                    detection_error = exc

            # Determine indicator type
            indicator_type = None
            if "indicator_type" in raw_indicator and raw_indicator["indicator_type"]:
                try:
                    indicator_type = IndicatorType(
                        raw_indicator["indicator_type"].lower()
                    )
                except ValueError:
                    if self.auto_detect_type:
                        if detected_type:
                            indicator_type = detected_type
                        elif detection_error:
                            raise ValidationError(
                                f"Invalid indicator_type '{raw_indicator['indicator_type']}' "
                                f"and auto-detect failed: {detection_error}"
                            )
                        else:
                            raise ValidationError(
                                f"Invalid indicator_type: {raw_indicator['indicator_type']}"
                            )
                    else:
                        raise ValidationError(
                            f"Invalid indicator_type: {raw_indicator['indicator_type']}"
                        )
            elif implied_type:
                indicator_type = implied_type
            elif detected_type:
                indicator_type = detected_type
            else:
                if detection_error:
                    raise ValidationError(str(detection_error)) from detection_error
                raise ValidationError(
                    "indicator_type is required when auto-detect is disabled "
                    "or when indicator type cannot be inferred from the data"
                )

            if (
                indicator_type
                and detected_type
                and implied_type
                and indicator_type != detected_type
            ):
                logger.debug(
                    "Indicator type inferred from field '%s' as %s but auto-detect suggested %s",
                    value_field,
                    indicator_type.value,
                    detected_type.value,
                )

            # Normalize the value based on type
            value = normalize_indicator(value, indicator_type)

            # Extract other fields
            source_name = raw_indicator.get("source", self.source_name)
            source_url = raw_indicator.get("source_url")
            notes = raw_indicator.get("notes")

            # Parse tags (can be array or comma-separated string)
            tags = []
            if "tags" in raw_indicator and raw_indicator["tags"]:
                tags_data = raw_indicator["tags"]
                if isinstance(tags_data, list):
                    tags = [str(tag).strip() for tag in tags_data if tag]
                elif isinstance(tags_data, str):
                    tags = [tag.strip() for tag in tags_data.split(",") if tag.strip()]

            # Parse first_seen timestamp
            first_seen = None
            if "first_seen" in raw_indicator and raw_indicator["first_seen"]:
                try:
                    first_seen = datetime.fromisoformat(raw_indicator["first_seen"])
                except (ValueError, TypeError):
                    first_seen = None

            # Create IndicatorData
            return IndicatorData(
                indicator_type=indicator_type,
                value=value,
                source_type=self.source_type,
                source_name=source_name,
                source_url=source_url,
                raw_data=raw_indicator,
                tags=tags,
                notes=notes,
                first_seen=first_seen,
            )

        except Exception as e:
            logger.error(f"Failed to normalize indicator: {e}")
            return None

    def _parse_json(self, file_content: Any) -> Any:
        """
        Parse JSON file content.

        Args:
            file_content: File content (bytes, str, or dict)

        Returns:
            Parsed JSON data
        """
        # If already a dict, return as-is
        if isinstance(file_content, dict) or isinstance(file_content, list):
            return file_content

        # Convert bytes to string
        if isinstance(file_content, bytes):
            file_content = file_content.decode("utf-8")

        # If file-like object, read it
        if hasattr(file_content, "read"):
            content = file_content.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            file_content = content

        # Parse JSON string
        if isinstance(file_content, str):
            try:
                return json.loads(file_content)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON: {str(e)}")

        raise ValidationError("Unsupported file content type")

    def _extract_indicators(self, data: Any) -> List[Dict[str, Any]]:
        """
        Extract indicators array from various JSON structures.

        Args:
            data: Parsed JSON data

        Returns:
            List of indicator dictionaries
        """
        indicators = []

        # Case 1: Already an array of indicators
        if isinstance(data, list):
            indicators = data

        # Case 2: Single indicator object
        elif isinstance(data, dict):
            # Check if it has an 'indicators' key
            if "indicators" in data:
                indicators = data["indicators"]
                if not isinstance(indicators, list):
                    indicators = [indicators]
            # Check if it has 'data' key
            elif "data" in data:
                indicators = data["data"]
                if not isinstance(indicators, list):
                    indicators = [indicators]
            # Otherwise treat the whole dict as a single indicator
            elif "value" in data:
                indicators = [data]

        # Filter out invalid entries
        valid_indicators = []
        for item in indicators:
            if not isinstance(item, dict):
                continue
            value, _, _ = extract_indicator_value_and_type(item)
            if value:
                valid_indicators.append(item)

        return valid_indicators
