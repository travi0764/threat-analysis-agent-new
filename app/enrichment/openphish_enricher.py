"""
OpenPhish enricher that consults the community feed to flag known phishing URLs.
The public feed does not require an API key. We cache the feed in-memory for a
configurable period to avoid re-downloading it for every enrichment request.
"""

import asyncio
import ssl
from datetime import datetime, timedelta
from typing import Optional, Set

import aiohttp
import certifi

from app.enrichment.base import BaseEnricher, EnrichmentResult
from app.storage.models import IndicatorType

OPENPHISH_COMMUNITY_FEED = "https://openphish.com/feed.txt"


class OpenPhishEnricher(BaseEnricher):
    """
    Enricher that checks URLs against the OpenPhish community feed.
    """

    def __init__(
        self,
        feed_url: str = OPENPHISH_COMMUNITY_FEED,
        cache_ttl_seconds: int = 15 * 60,  # 15 minutes
    ):
        super().__init__(enrichment_type="phishing_check", provider="openphish")
        self.feed_url = feed_url
        self.cache_ttl_seconds = max(cache_ttl_seconds, 60)
        self._cache_urls: Set[str] = set()
        self._cache_fetched_at: Optional[datetime] = None
        self._cache_lock = asyncio.Lock()
        self._client_timeout = aiohttp.ClientTimeout(total=30)

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        """Run for URL and domain indicators."""
        return indicator_type in (IndicatorType.URL, IndicatorType.DOMAIN)

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                f"OpenPhish enrichment not applicable for {indicator_type.value}"
            )

        try:
            await self._ensure_feed_cache()
        except Exception as exc:
            self.logger.error("OpenPhish feed refresh failed: %s", exc)
            return self._create_error_result(f"Failed to refresh OpenPhish feed: {exc}")

        # Normalize for comparison
        normalized = indicator_value.strip().lower()

        # For domains, check if any URL in the feed contains this domain
        if indicator_type == IndicatorType.DOMAIN:
            listed = any(normalized in url for url in self._cache_urls)
        else:
            # For URLs, check exact match and without trailing slash
            candidates = {normalized, normalized.rstrip("/")}
            listed = any(candidate in self._cache_urls for candidate in candidates)

        fetched_at_iso = (
            self._cache_fetched_at.isoformat()
            if self._cache_fetched_at is not None
            else None
        )

        data = {
            "indicator": indicator_value,
            "indicator_type": indicator_type.value,
            "listed": listed,
            "feed": self.feed_url,
            "cache_fetched_at": fetched_at_iso,
            "cache_size": len(self._cache_urls),
        }

        if listed:
            data["message"] = "Present in OpenPhish community phishing feed"
            # URLs that are in the feed are high risk
            return self._create_success_result(data, score=9.0)

        data["message"] = "Not present in OpenPhish community feed at last refresh"
        # Not seeing the URL is a valid finding - return successful result with no score
        return self._create_success_result(data, score=None)

    async def _ensure_feed_cache(self) -> None:
        """
        Refresh the feed cache if the TTL has elapsed.
        """
        now = datetime.utcnow()
        if self._cache_fetched_at and now - self._cache_fetched_at < timedelta(
            seconds=self.cache_ttl_seconds
        ):
            return

        # Ensure only one coroutine refreshes the cache at a time
        async with self._cache_lock:
            # Double-check after acquiring lock
            if (
                self._cache_fetched_at
                and datetime.utcnow() - self._cache_fetched_at
                < timedelta(seconds=self.cache_ttl_seconds)
            ):
                return

            # Create SSL context with certifi certificates
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(
                connector=connector, timeout=self._client_timeout
            ) as session:
                async with session.get(self.feed_url) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise RuntimeError(
                            f"HTTP {response.status} while fetching OpenPhish feed: {text[:200]}"
                        )
                    body = await response.text()

            urls = {
                line.strip().lower()
                for line in body.splitlines()
                if line.strip() and not line.startswith("#")
            }

            if not urls:
                raise RuntimeError("OpenPhish feed returned no entries")

            self._cache_urls = urls
            self._cache_fetched_at = datetime.utcnow()
            self.logger.info(
                "OpenPhish feed refreshed (%d entries) from %s",
                len(urls),
                self.feed_url,
            )
