"""
MalShare enricher for file hash lookups.
Requires MALSHARE_API_KEY environment variable.
"""

from typing import Any, Dict

import aiohttp

from app.config import get_settings
from app.enrichment.base import BaseEnricher, EnrichmentResult
from app.logging_config import get_logger
from app.storage.models import IndicatorType

logger = get_logger(__name__)


class MalShareEnricher(BaseEnricher):
    """
    MalShare enricher for file hash lookups.
    Provides malware detection and file information.
    """

    def __init__(self, api_key: str = None):
        super().__init__(enrichment_type="hash_lookup", provider="malshare")
        settings = get_settings()
        self.api_key = api_key or settings.malshare_api_key
        self.base_url = "https://malshare.com/api.php"

        if not self.api_key:
            logger.warning("MalShare API key not configured")

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        return indicator_type == IndicatorType.HASH and self.api_key is not None

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """Enrich a file hash using MalShare API."""

        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                "MalShare enrichment not applicable or API key not configured"
            )

        # Validate hash format
        hash_length = len(indicator_value)
        if hash_length not in [32, 40, 64]:  # MD5, SHA1, SHA256
            return self._create_error_result("Invalid hash format")

        try:
            # Determine hash type
            hash_type = {32: "md5", 40: "sha1", 64: "sha256"}.get(
                hash_length, "unknown"
            )

            # Create SSL context that doesn't verify certificates (for malshare.com)
            import ssl

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                # Query MalShare API
                params = {
                    "api_key": self.api_key,
                    "action": "details",
                    "hash": indicator_value,
                }

                async with session.get(
                    self.base_url, params=params, timeout=30
                ) as response:
                    if response.status == 404:
                        # Hash not found in MalShare - This is an expected condition, not a failure
                        return self._create_success_result(
                            {
                                "hash": indicator_value,
                                "hash_type": hash_type,
                                "found": False,
                                "in_malshare": False,
                                "message": "Hash not found in MalShare database",
                            },
                            None,
                        )  # Return None instead of 0.0 to indicate "no score"
                    elif response.status == 200:
                        response_data = await response.json()

                        # MalShare found the hash (indicates malware)
                        data = {
                            "hash": indicator_value,
                            "hash_type": hash_type,
                            "found": True,
                            "in_malshare": True,
                            "md5": response_data.get("MD5"),
                            "sha1": response_data.get("SHA1"),
                            "sha256": response_data.get("SHA256"),
                            "file_type": response_data.get("F_TYPE"),
                            "source": response_data.get("SOURCE", []),
                            "added_date": response_data.get("ADDED"),
                            "is_malware": True,  # Present in MalShare = malware
                        }
                        score = 9.0  # High score for confirmed malware
                    else:
                        error_text = await response.text()
                        return self._create_error_result(
                            f"MalShare API error: {response.status} - {error_text}"
                        )

                self.logger.info(
                    f"MalShare lookup for {indicator_value}: "
                    f"found={data.get('found')}, score={score}"
                )

                return self._create_success_result(data, score)

        except aiohttp.ClientError as e:
            logger.error(f"MalShare API connection error: {e}")
            return self._create_error_result(f"Connection error: {str(e)}")
        except Exception as e:
            logger.error(f"MalShare enrichment failed: {e}")
            return self._create_error_result(f"Enrichment failed: {str(e)}")

    def calculate_risk_score(self, data: Dict[str, Any]) -> float:
        """Calculate risk score based on MalShare data."""
        score = 0.0

        # If found in MalShare, it's malware
        if data.get("in_malshare") or data.get("is_malware"):
            score = 9.0  # Very high risk
        elif not data.get("found"):
            score = 0.0  # Not found = unknown/safe

        return score
