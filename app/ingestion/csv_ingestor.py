"""
CSV Ingestor for Threat Analysis Agent.
Handles CSV file parsing, validation, and normalization.
"""

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.ingestion.ingestor import BaseIngestor, IndicatorData, IngestionResult
from app.logging_config import get_logger
from app.storage.models import Indicator, IndicatorType, SourceType
from app.utils.exceptions import IngestionError, ValidationError
from app.utils.helpers import (
    detect_indicator_type,
    normalize_indicator,
    sanitize_string,
)

logger = get_logger(__name__)


class CSVIngestor(BaseIngestor):
    """
    Ingestor for CSV files containing threat indicators.

    Expected CSV format:
        indicator_type,value,source,tags,notes
        domain,evil-domain.com,manual,"phishing,malware",Reported by user
        ip,192.0.2.1,feed,suspicious,High traffic

    Or simplified format (auto-detect type):
        value,source,tags,notes
        evil-domain.com,manual,phishing,Reported by user
    """

    # Required fields (at minimum, we need 'value')
    REQUIRED_FIELDS = ["value"]

    # Optional fields
    OPTIONAL_FIELDS = [
        "indicator_type",
        "source",
        "source_url",
        "tags",
        "notes",
        "first_seen",
    ]

    # Maximum rows to process in a single file
    MAX_ROWS = 10000

    def __init__(
        self,
        source_name: str = "csv_upload",
        auto_detect_type: bool = True,
        skip_duplicates: bool = True,
    ):
        """
        Initialize CSV ingestor.

        Args:
            source_name: Name of the CSV source
            auto_detect_type: Auto-detect indicator type if not provided
            skip_duplicates: Skip duplicate indicators
        """
        super().__init__(SourceType.CSV_UPLOAD, source_name)
        self.auto_detect_type = auto_detect_type
        self.skip_duplicates = skip_duplicates

    def ingest(self, file_content: Any, db_session: Any) -> IngestionResult:
        """
        Ingest indicators from CSV file.

        Args:
            file_content: File content (BinaryIO, TextIO, or string)
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
            # Parse CSV content
            rows = self._parse_csv(file_content)

            if not rows:
                raise IngestionError("CSV file is empty or has no valid data")

            logger.info(f"Parsed {len(rows)} rows from CSV")

            # Validate header
            if rows and not self._validate_header(rows[0]):
                raise IngestionError(
                    f"CSV must contain at least 'value' column. "
                    f"Found columns: {list(rows[0].keys())}"
                )

            # Check row limit
            if len(rows) > self.MAX_ROWS:
                logger.warning(f"CSV has {len(rows)} rows, limiting to {self.MAX_ROWS}")
                rows = rows[: self.MAX_ROWS]

            # Process each row
            for idx, row in enumerate(rows, start=1):
                result.indicators_processed += 1

                try:
                    # Normalize the row into IndicatorData
                    indicator_data = self.normalize_indicator(row)

                    if not indicator_data:
                        result.indicators_failed += 1
                        result.add_error(idx, "Failed to normalize indicator", row)
                        continue

                    # Check for duplicates
                    if self.skip_duplicates:
                        existing = (
                            db_session.query(Indicator)
                            .filter_by(value=indicator_data.value)
                            .first()
                        )

                        if existing:
                            # Update last_seen timestamp
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
                    result.add_error(idx, str(e), row)
                    logger.error(f"Error processing row {idx}: {e}")
                    db_session.rollback()
                    continue

            # Mark as successful if at least one indicator was created
            result.success = result.indicators_created > 0

            logger.info(
                f"CSV ingestion complete: {result.indicators_created} created, "
                f"{result.indicators_updated} updated, {result.indicators_failed} failed"
            )

        except Exception as e:
            result.success = False
            result.add_error(0, f"CSV ingestion failed: {str(e)}")
            logger.error(f"CSV ingestion failed: {e}")

        return result

    def validate(self, file_content: Any) -> bool:
        """
        Validate CSV file format.

        Args:
            file_content: File content to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            rows = self._parse_csv(file_content)

            if not rows:
                return False

            # Check header
            if not self._validate_header(rows[0]):
                return False

            # Check at least one row has data
            return len(rows) > 0

        except Exception as e:
            logger.error(f"CSV validation failed: {e}")
            return False

    def normalize_indicator(
        self, raw_indicator: Dict[str, Any]
    ) -> Optional[IndicatorData]:
        """
        Normalize a CSV row into IndicatorData.

        Args:
            raw_indicator: Dictionary representing a CSV row

        Returns:
            IndicatorData object or None if normalization fails
        """
        try:
            # Extract value (required)
            value = raw_indicator.get("value", "").strip()
            if not value:
                raise ValidationError("Missing 'value' field")

            # Sanitize value
            value = sanitize_string(value)

            # Determine indicator type
            if "indicator_type" in raw_indicator and raw_indicator["indicator_type"]:
                try:
                    indicator_type = IndicatorType(
                        raw_indicator["indicator_type"].lower()
                    )
                except ValueError:
                    if self.auto_detect_type:
                        indicator_type = detect_indicator_type(value)
                    else:
                        raise ValidationError(
                            f"Invalid indicator_type: {raw_indicator['indicator_type']}"
                        )
            else:
                if self.auto_detect_type:
                    indicator_type = detect_indicator_type(value)
                else:
                    raise ValidationError(
                        "indicator_type is required when auto-detect is disabled"
                    )

            # Normalize the value based on type
            value = normalize_indicator(value, indicator_type)

            # Extract other fields
            source_name = raw_indicator.get("source", self.source_name)
            source_url = raw_indicator.get("source_url")
            notes = raw_indicator.get("notes")

            # Parse tags (comma-separated string to list)
            tags = []
            if "tags" in raw_indicator and raw_indicator["tags"]:
                tags_str = raw_indicator["tags"]
                if isinstance(tags_str, str):
                    tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                elif isinstance(tags_str, list):
                    tags = tags_str

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

    def _parse_csv(self, file_content: Any) -> List[Dict[str, Any]]:
        """
        Parse CSV file content into list of dictionaries.

        Args:
            file_content: File content (BinaryIO, TextIO, or string)

        Returns:
            List of dictionaries (one per row)
        """
        # Convert content to text stream
        if isinstance(file_content, bytes):
            text_stream = io.StringIO(file_content.decode("utf-8"))
        elif isinstance(file_content, str):
            text_stream = io.StringIO(file_content)
        elif hasattr(file_content, "read"):
            # File-like object
            content = file_content.read()
            if isinstance(content, bytes):
                text_stream = io.StringIO(content.decode("utf-8"))
            else:
                text_stream = io.StringIO(content)
        else:
            raise ValidationError("Unsupported file content type")

        # Parse CSV
        reader = csv.DictReader(text_stream)
        rows = []

        for row in reader:
            # Skip empty rows
            if not any(row.values()):
                continue
            rows.append(row)

        return rows

    def _validate_header(self, first_row: Dict[str, Any]) -> bool:
        """
        Validate CSV header has required fields.

        Args:
            first_row: First row of CSV (header)

        Returns:
            True if valid header
        """
        if not first_row:
            return False

        # Check for required fields
        for field in self.REQUIRED_FIELDS:
            if field not in first_row:
                return False

        return True
