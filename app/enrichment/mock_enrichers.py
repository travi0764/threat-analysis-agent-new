"""
Mock enrichers for testing without external API dependencies.
These simulate real enrichment behavior with fake data.
"""

import random
from datetime import datetime, timedelta
from typing import Any, Dict

from app.enrichment.base import BaseEnricher, EnrichmentResult
from app.storage.models import IndicatorType


class MockWhoisEnricher(BaseEnricher):
    """
    Mock WHOIS enricher for domains.
    Returns fake WHOIS data for testing.
    """

    def __init__(self):
        super().__init__(enrichment_type="whois", provider="mock")

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        return indicator_type in [IndicatorType.DOMAIN, IndicatorType.URL]

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """Generate mock WHOIS data."""

        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                f"WHOIS enrichment not applicable for {indicator_type.value}"
            )

        # Extract domain from URL if needed
        if indicator_type == IndicatorType.URL:
            from app.utils.helpers import extract_domain_from_url

            domain = extract_domain_from_url(indicator_value)
            if not domain:
                return self._create_error_result("Could not extract domain from URL")
            indicator_value = domain

        # Generate mock data
        registrars = [
            "GoDaddy",
            "Namecheap",
            "CloudFlare",
            "Google Domains",
            "Network Solutions",
        ]
        countries = ["US", "CN", "RU", "BR", "IN", "DE", "FR"]

        # Suspicious indicators get older creation dates and certain registrars
        is_suspicious = any(
            word in indicator_value.lower()
            for word in ["evil", "phish", "malware", "hack", "scam", "fake", "bad"]
        )

        created_date = datetime.utcnow() - timedelta(days=random.randint(30, 3650))
        expires_date = created_date + timedelta(days=365 * random.randint(1, 3))

        if is_suspicious:
            # Recently created domains are more suspicious
            created_date = datetime.utcnow() - timedelta(days=random.randint(1, 90))
            expires_date = created_date + timedelta(days=365)

        data = {
            "domain": indicator_value,
            "registrar": random.choice(registrars),
            "creation_date": created_date.isoformat(),
            "expiration_date": expires_date.isoformat(),
            "updated_date": (
                datetime.utcnow() - timedelta(days=random.randint(1, 365))
            ).isoformat(),
            "registrant_country": random.choice(countries),
            "name_servers": [f"ns{i}.example.com" for i in range(1, 3)],
            "status": ["clientTransferProhibited"],
            "dnssec": random.choice([True, False]),
        }

        score = self.calculate_risk_score(data)

        self.logger.debug(f"Mock WHOIS enrichment for {indicator_value}: score={score}")

        return self._create_success_result(data, score)

    def calculate_risk_score(self, data: Dict[str, Any]) -> float:
        """Calculate risk score based on WHOIS data."""
        score = 0.0

        # Check domain age (newer = more suspicious)
        try:
            creation_date = datetime.fromisoformat(data["creation_date"])
            age_days = (datetime.utcnow() - creation_date).days

            if age_days < 30:
                score += 5.0  # Very new domain
            elif age_days < 90:
                score += 3.0  # New domain
            elif age_days < 365:
                score += 1.0  # Recent domain
        except:
            score += 2.0  # Unknown age

        # Check registrant country (high-risk countries)
        high_risk_countries = ["CN", "RU", "BR"]
        if data.get("registrant_country") in high_risk_countries:
            score += 2.0

        # No DNSSEC is slightly more risky
        if not data.get("dnssec"):
            score += 0.5

        # Clamp to 0-10 range
        return max(0.0, min(10.0, score))


class MockIPReputationEnricher(BaseEnricher):
    """
    Mock IP reputation enricher.
    Returns fake reputation data for testing.
    """

    def __init__(self):
        super().__init__(enrichment_type="ip_reputation", provider="mock")

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        return indicator_type == IndicatorType.IP

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """Generate mock IP reputation data."""

        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                f"IP reputation not applicable for {indicator_type.value}"
            )

        # Check if IP looks suspicious (e.g., starts with certain octets)
        is_suspicious = False
        try:
            octets = indicator_value.split(".")
            if len(octets) == 4:
                first_octet = int(octets[0])
                # Private ranges are less suspicious
                if first_octet in [10, 172, 192]:
                    is_suspicious = False
                else:
                    is_suspicious = random.random() > 0.6
        except:
            pass

        # Generate abuse confidence score
        if is_suspicious:
            abuse_confidence = random.randint(60, 100)
            total_reports = random.randint(50, 500)
        else:
            abuse_confidence = random.randint(0, 30)
            total_reports = random.randint(0, 10)

        abuse_categories = []
        if is_suspicious:
            categories = ["Brute Force", "Port Scan", "DDoS", "Spam", "Malware"]
            abuse_categories = random.sample(categories, k=random.randint(1, 3))

        data = {
            "ip_address": indicator_value,
            "abuse_confidence_score": abuse_confidence,
            "total_reports": total_reports,
            "distinct_users": random.randint(1, 50),
            "country_code": random.choice(["US", "CN", "RU", "BR", "IN", "DE"]),
            "isp": random.choice(
                ["AWS", "Google Cloud", "DigitalOcean", "OVH", "Hetzner"]
            ),
            "usage_type": random.choice(["Data Center", "Commercial", "Residential"]),
            "abuse_categories": abuse_categories,
            "last_reported": datetime.utcnow().isoformat(),
            "is_tor": random.choice([True, False]) if is_suspicious else False,
            "is_proxy": random.choice([True, False]) if is_suspicious else False,
        }

        score = self.calculate_risk_score(data)

        self.logger.debug(f"Mock IP reputation for {indicator_value}: score={score}")

        return self._create_success_result(data, score)

    def calculate_risk_score(self, data: Dict[str, Any]) -> float:
        """Calculate risk score based on IP reputation data."""
        score = 0.0

        # Main factor: abuse confidence score
        abuse_score = data.get("abuse_confidence_score", 0)
        score += (abuse_score / 100.0) * 7.0  # Up to 7 points

        # Additional factors
        if data.get("is_tor"):
            score += 1.5
        if data.get("is_proxy"):
            score += 1.0

        # Usage type
        if data.get("usage_type") == "Data Center":
            score += 0.5

        # Number of abuse categories
        categories = data.get("abuse_categories", [])
        score += len(categories) * 0.5

        # Clamp to 0-10 range
        return max(0.0, min(10.0, score))


class MockHashEnricher(BaseEnricher):
    """
    Mock hash/malware enricher.
    Returns fake malware detection data for testing.
    """

    def __init__(self):
        super().__init__(enrichment_type="hash_lookup", provider="mock")

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        return indicator_type == IndicatorType.HASH

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        """Generate mock hash lookup data."""

        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                f"Hash lookup not applicable for {indicator_type.value}"
            )

        # Determine hash type
        hash_length = len(indicator_value)
        if hash_length == 32:
            hash_type = "MD5"
        elif hash_length == 40:
            hash_type = "SHA1"
        elif hash_length == 64:
            hash_type = "SHA256"
        else:
            hash_type = "Unknown"

        # Randomly decide if this is malware
        is_malware = random.random() > 0.4

        if is_malware:
            detection_ratio = f"{random.randint(30, 70)}/70"
            detections = random.randint(30, 70)
            total_engines = 70
            malware_families = random.sample(
                ["Trojan", "Ransomware", "Backdoor", "Worm", "Adware", "Spyware"],
                k=random.randint(1, 3),
            )
        else:
            detection_ratio = f"{random.randint(0, 5)}/70"
            detections = random.randint(0, 5)
            total_engines = 70
            malware_families = []

        data = {
            "hash": indicator_value,
            "hash_type": hash_type,
            "detection_ratio": detection_ratio,
            "detections": detections,
            "total_engines": total_engines,
            "malware_families": malware_families,
            "first_seen": (
                datetime.utcnow() - timedelta(days=random.randint(1, 365))
            ).isoformat(),
            "last_seen": (
                datetime.utcnow() - timedelta(days=random.randint(0, 30))
            ).isoformat(),
            "file_type": random.choice(["PE32", "ELF", "PDF", "Script", "Archive"]),
            "file_size": random.randint(1024, 10485760),  # 1KB to 10MB
            "is_malware": is_malware,
        }

        score = self.calculate_risk_score(data)

        self.logger.debug(f"Mock hash lookup for {indicator_value}: score={score}")

        return self._create_success_result(data, score)

    def calculate_risk_score(self, data: Dict[str, Any]) -> float:
        """Calculate risk score based on hash detection data."""
        score = 0.0

        # Main factor: detection ratio
        detections = data.get("detections", 0)
        total = data.get("total_engines", 70)

        if total > 0:
            detection_percentage = (detections / total) * 100
            score += (detection_percentage / 100.0) * 8.0  # Up to 8 points

        # Malware families
        families = data.get("malware_families", [])
        score += len(families) * 0.5

        # Is explicitly marked as malware
        if data.get("is_malware"):
            score += 1.0

        # Clamp to 0-10 range
        return max(0.0, min(10.0, score))
