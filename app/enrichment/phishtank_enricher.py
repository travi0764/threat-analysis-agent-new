"""
Async PhishTank enricher.

Uses the PhishTank downloadable feed at:
  https://data.phishtank.com/data/online-valid.csv

- The CSV feed is cached in-memory for `feed_ttl_seconds`.
- URL lookups check feed data using multiple normalizations (exact, lowercase, no-query-string).
- Verified phishing URLs receive higher risk scores.

Expose `ensure_feed()` so the application can preload the feed at startup and
conditionally register this enricher only if the feed loads successfully.
"""

from __future__ import annotations

import csv
import io
import logging
import ssl
import time
from typing import Any, Dict, Optional

import aiohttp
import certifi

from app.config import get_settings
from app.enrichment.base import BaseEnricher, EnrichmentResult
from app.storage.models import IndicatorType

logger = logging.getLogger(__name__)
settings = get_settings()


class PhishTankEnricher(BaseEnricher):
    """Async PhishTank enricher using aiohttp.

    Public methods:
    - is_applicable(indicator_type)
    - async enrich(value, indicator_type)
    - async ensure_feed() -> bool  # preload feed at startup
    """

    def __init__(self, feed_ttl_seconds: int = 3600):
        super().__init__(enrichment_type="phishing_check", provider="phishtank")

        # Request headers to identify ourselves to PhishTank
        self._headers = {
            "User-Agent": "ThreatAnalysisAgent/1.0 (Research/Education Use)",
            "Accept": "text/csv,text/plain,*/*",
        }

        # Feed settings
        self.feed_ttl_seconds = max(int(feed_ttl_seconds), 60)
        self._feed_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._feed_cache_at: float = 0.0

        # aiohttp ClientSession parameters
        self._client_timeout = aiohttp.ClientTimeout(total=30)
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def is_applicable(self, indicator_type: IndicatorType) -> bool:
        return indicator_type == IndicatorType.URL

    async def enrich(
        self, indicator_value: str, indicator_type: IndicatorType
    ) -> EnrichmentResult:
        if not self.is_applicable(indicator_type):
            return self._create_error_result(
                f"PhishTank enrichment not applicable for {indicator_type.value}"
            )

        url = indicator_value.strip()

        try:
            feed = await self._ensure_feed()  # This loads or refreshes the feed
        except Exception as exc:
            return self._create_error_result(f"Failed to load PhishTank feed: {exc}")

        if not feed:
            return self._create_error_result("PhishTank feed unavailable")

        lookup = await self._lookup_in_feed(url)
        if lookup is None:
            return self._create_error_result("PhishTank lookup failed")

        if lookup.get("found") is False:
            return self._create_success_result(lookup, score=None)

        score = 9.0 if lookup.get("verified") else 8.0
        return self._create_success_result(lookup, score=score)

    # Public preload API used by startup
    async def ensure_feed(self) -> bool:
        """Ensure feed is loaded and fresh. Returns True on success, False on failure."""
        try:
            res = await self._ensure_feed()
            return bool(res)
        except Exception:
            return False

    # -------------------------
    # Internal helpers
    # -------------------------
    async def _lookup_in_feed(self, url: str) -> Optional[Dict[str, Any]]:
        """Lookup URL in the in-memory feed cache. Returns dict or {'found': False} if not present."""
        if self._feed_cache is None:
            return None

        key = url.strip()
        entry = self._feed_cache.get(key)
        if not entry:
            key_lower = key.lower()
            entry = self._feed_cache.get(key_lower)
            if not entry:
                # try without query string
                try:
                    from urllib.parse import urlsplit, urlunsplit

                    parts = urlsplit(key_lower)
                    no_q = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                    entry = self._feed_cache.get(no_q) or self._feed_cache.get(
                        no_q.lower()
                    )
                except Exception:
                    entry = None

        if not entry:
            return {"provider": self.provider, "found": False}

        phish_id = entry.get("phish_id") or entry.get("id")
        phish_url = entry.get("url") or entry.get("phish_url") or url
        target = entry.get("target")
        verified = str(entry.get("verified", "")).lower() in ("yes", "true", "1")
        submitted_at = (
            entry.get("submission_time")
            or entry.get("submission_at")
            or entry.get("submission_date")
        )
        detail_page = (
            f"https://phishtank.org/phish_detail.php?phish_id={phish_id}"
            if phish_id
            else None
        )

        return {
            "provider": self.provider,
            "found": True,
            "phish_id": phish_id,
            "url": phish_url,
            "target": target,
            "verified": verified,
            "submitted_at": submitted_at,
            "phish_detail_page": detail_page,
            "raw": entry,
        }

    async def _ensure_feed(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Download and cache the PhishTank CSV feed if TTL expired. Returns the feed map or None."""
        now = time.time()
        if (
            self._feed_cache is not None
            and (now - self._feed_cache_at) < self.feed_ttl_seconds
        ):
            return self._feed_cache

        csv_url = getattr(
            settings,
            "phishtank_csv_url",
            "https://data.phishtank.com/data/online-valid.csv",
        )
        connector = aiohttp.TCPConnector(ssl=self._ssl_context)
        async with aiohttp.ClientSession(
            connector=connector, timeout=self._client_timeout
        ) as session:
            try:
                async with session.get(csv_url, headers=self._headers) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "PhishTankEnricher: feed download returned status %s",
                            resp.status,
                        )
                        return None
                    text = await resp.text()
            except Exception as e:
                logger.exception("PhishTankEnricher: failed to download feed: %s", e)
                return None

        # Parse CSV into dict keyed by multiple normalized URL forms
        reader = csv.DictReader(io.StringIO(text))
        feed_map: Dict[str, Dict[str, Any]] = {}
        for row in reader:
            url_val = (
                row.get("url") or row.get("phish_url") or row.get("phish") or ""
            ).strip()
            if not url_val:
                continue

            feed_map[url_val] = row
            feed_map[url_val.lower()] = row
            try:
                from urllib.parse import urlsplit, urlunsplit

                p = urlsplit(url_val)
                no_q = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
                feed_map[no_q] = row
                feed_map[no_q.lower()] = row
            except Exception:
                pass

        self._feed_cache = feed_map
        self._feed_cache_at = now
        logger.info("✓ PhishTankEnricher: loaded %d entries from feed", len(feed_map))
        return self._feed_cache
