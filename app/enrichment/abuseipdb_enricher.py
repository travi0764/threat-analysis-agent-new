"""
AbuseIPDB enricher for IP reputation checks.
Requires ABUSEIPDB_API_KEY in environment/config.
"""

import ssl
from typing import Any, Dict

import aiohttp
import certifi

from app.enrichment.base import BaseEnricher, EnrichmentResult
from app.storage.models import IndicatorType


class AbuseIPDBEnricher(BaseEnricher):
    """
    AbuseIPDB API enricher for IP addresses.
    Provides IP reputation and abuse intelligence.
    """

    def __init__(self, api_key: str):
        super().__init__(enrichment_type="ip_reputation", provider="abuseipdb")
        self.api_key = api_key
        self.base_url = "https://api.abuseipdb.com/api/v2/check"

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        return indicator_type == IndicatorType.IP

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """Fetch IP reputation from AbuseIPDB."""

        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                f"AbuseIPDB enrichment not applicable for {indicator_type.value}"
            )

        if not self.api_key:
            self.logger.warning("AbuseIPDB API key not configured")
            return self._create_error_result("AbuseIPDB API key not configured")

        try:
            headers = {"Key": self.api_key, "Accept": "application/json"}
            params = {"ipAddress": indicator_value, "maxAgeInDays": 90, "verbose": ""}

            # Create SSL context with certifi certificates
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            self.logger.debug(f"AbuseIPDB request for {indicator_value}")

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    self.base_url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        api_data = result.get("data", {})

                        data = {
                            "ip_address": api_data.get("ipAddress"),
                            "abuse_confidence_score": api_data.get(
                                "abuseConfidenceScore"
                            ),
                            "country_code": api_data.get("countryCode"),
                            "country_name": api_data.get("countryName"),
                            "usage_type": api_data.get("usageType"),
                            "isp": api_data.get("isp"),
                            "domain": api_data.get("domain"),
                            "is_whitelisted": api_data.get("isWhitelisted"),
                            "is_tor": api_data.get("isTor"),
                            "total_reports": api_data.get("totalReports"),
                            "num_distinct_users": api_data.get("numDistinctUsers"),
                            "last_reported_at": api_data.get("lastReportedAt"),
                        }

                        confidence = data.get("abuse_confidence_score")
                        total_reports = data.get("total_reports")
                        if confidence is not None:
                            data["message"] = (
                                f"Abuse confidence score {confidence}% with {total_reports or 0} total reports"
                            )
                        else:
                            data["message"] = "No recent abuse reports for this IP"

                        score = self.calculate_risk_score(data)

                        self.logger.debug(
                            f"AbuseIPDB enrichment for {indicator_value}: score={score}, confidence={confidence}%"
                        )

                        return self._create_success_result(data, score)

                    else:
                        # Log response body to help troubleshoot 401/4xx/5xx
                        try:
                            error_text = await response.text()
                        except Exception:
                            error_text = "<unreadable response>"

                        if response.status == 429:
                            self.logger.warning(
                                f"AbuseIPDB rate limit for {indicator_value}"
                            )
                            return self._create_error_result("API rate limit exceeded")
                        elif response.status == 401:
                            self.logger.warning(
                                f"AbuseIPDB unauthorized for {indicator_value}"
                            )
                            return self._create_error_result("Invalid API key")
                        else:
                            self.logger.warning(
                                f"AbuseIPDB API error {response.status} for {indicator_value}: {error_text[:200]}"
                            )
                            return self._create_error_result(
                                f"API error {response.status}"
                            )

        except aiohttp.ClientError as e:
            self.logger.warning(
                f"AbuseIPDB API request failed for {indicator_value}: {str(e)}"
            )
            return self._create_error_result(f"API request failed: {str(e)}")
        except Exception as e:
            self.logger.error(
                f"AbuseIPDB enrichment error for {indicator_value}: {str(e)}"
            )
            return self._create_error_result(f"Enrichment failed: {str(e)}")

    def calculate_risk_score(self, data: Dict[str, Any]) -> float:
        """Calculate risk score based on AbuseIPDB data."""
        score = 0.0

        # Main factor: abuse confidence score
        abuse_score = data.get("abuse_confidence_score", 0)
        if abuse_score is not None and abuse_score > 0:
            # Scale abuse score to our risk score more aggressively
            score += (abuse_score / 100.0) * 8.5  # Up to 8.5 points for high confidence

        # Additional risk factors
        if data.get("is_tor"):
            score += 1.5

        if data.get("is_whitelisted"):
            score = max(0, score - 2.0)  # Reduce score if whitelisted

        # Total reports indicate history of abuse
        total_reports = data.get("total_reports", 0)
        if total_reports and total_reports > 100:
            score += 1.0
        elif total_reports and total_reports > 50:
            score += 0.5

        # Usage type
        usage_type = data.get("usage_type", "")
        if usage_type == "Data Center":
            score += 0.5  # Data centers can be more suspicious

        # Number of distinct reporting users
        distinct_users = data.get("num_distinct_users", 0)
        if distinct_users and distinct_users > 10:
            score += 0.5

        # Clamp to 0-10 range
        return max(0.0, min(10.0, score))
