"""
Helper utilities for Threat Analysis Agent.
"""

import hashlib
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import tldextract
import validators

from app.storage.models import IndicatorType
from app.utils.exceptions import ValidationError


def detect_indicator_type(value: str) -> IndicatorType:
    """
    Detect the type of indicator based on its value.

    Args:
        value: The indicator value

    Returns:
        IndicatorType enum value

    Raises:
        ValidationError: If indicator type cannot be determined
    """
    value = value.strip().lower()

    # Check for hash (MD5, SHA1, SHA256)
    if re.match(r"^[a-f0-9]{32}$", value):
        return IndicatorType.HASH  # MD5
    elif re.match(r"^[a-f0-9]{40}$", value):
        return IndicatorType.HASH  # SHA1
    elif re.match(r"^[a-f0-9]{64}$", value):
        return IndicatorType.HASH  # SHA256

    # Check for IP address
    if validators.ipv4(value) or validators.ipv6(value):
        return IndicatorType.IP

    # Check for email
    if validators.email(value):
        return IndicatorType.EMAIL

    # Check for URL
    if validators.url(value):
        return IndicatorType.URL

    # Check for domain
    if validators.domain(value):
        return IndicatorType.DOMAIN

    raise ValidationError(f"Could not determine indicator type for: {value}")


def normalize_indicator(value: str, indicator_type: IndicatorType) -> str:
    """
    Normalize an indicator value based on its type.

    Args:
        value: The indicator value
        indicator_type: The type of indicator

    Returns:
        Normalized indicator value
    """
    value = value.strip()

    if indicator_type == IndicatorType.HASH:
        return value.lower()

    elif indicator_type == IndicatorType.IP:
        return value.lower()

    elif indicator_type == IndicatorType.DOMAIN:
        # Remove protocol if present
        if "://" in value:
            value = urlparse(value).netloc or value
        return value.lower().rstrip(".")

    elif indicator_type == IndicatorType.URL:
        return value.lower()

    elif indicator_type == IndicatorType.EMAIL:
        return value.lower()

    return value


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract domain from a URL.

    Args:
        url: The URL

    Returns:
        Domain name or None
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        return domain.lower().rstrip(".")
    except Exception:
        return None


def get_tld_info(domain: str) -> dict:
    """
    Extract TLD information from a domain.

    Args:
        domain: Domain name

    Returns:
        Dictionary with subdomain, domain, and suffix
    """
    try:
        ext = tldextract.extract(domain)
        return {
            "subdomain": ext.subdomain,
            "domain": ext.domain,
            "suffix": ext.suffix,
            "registered_domain": ext.registered_domain,
        }
    except Exception:
        return {}


def calculate_hash(data: str, algorithm: str = "sha256") -> str:
    """
    Calculate hash of data.

    Args:
        data: Data to hash
        algorithm: Hash algorithm (md5, sha1, sha256)

    Returns:
        Hexadecimal hash string
    """
    if algorithm == "md5":
        return hashlib.md5(data.encode()).hexdigest()
    elif algorithm == "sha1":
        return hashlib.sha1(data.encode()).hexdigest()
    elif algorithm == "sha256":
        return hashlib.sha256(data.encode()).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def validate_csv_row(row: dict, required_fields: list) -> bool:
    """
    Validate a CSV row has all required fields.

    Args:
        row: Dictionary representing a CSV row
        required_fields: List of required field names

    Returns:
        True if valid, False otherwise
    """
    return all(field in row and row[field] for field in required_fields)


def sanitize_string(value: str, max_length: int = 500) -> str:
    """
    Sanitize a string value.

    Args:
        value: String to sanitize
        max_length: Maximum length

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        value = str(value)

    # Remove null bytes and control characters
    value = value.replace("\x00", "")
    value = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")

    # Truncate if too long
    if len(value) > max_length:
        value = value[:max_length]

    return value.strip()


def parse_risk_score(score: any) -> float:
    """
    Parse and normalize a risk score to 0-10 scale.

    Args:
        score: Score value (can be string, int, float)

    Returns:
        Normalized float score between 0 and 10
    """
    try:
        score = float(score)
        # Clamp to 0-10 range
        return max(0.0, min(10.0, score))
    except (ValueError, TypeError):
        return 0.0


def format_timestamp(dt) -> str:
    """
    Format a datetime object to ISO 8601 string.

    Args:
        dt: datetime object

    Returns:
        ISO 8601 formatted string
    """
    if dt is None:
        return None
    return dt.isoformat()


PRIMARY_INDICATOR_FIELDS = [
    "value",
    "indicator",
    "indicator_value",
    "observable",
    "ioc",
    "artifact",
]

# Aliases that imply both the value and the indicator type
INDICATOR_FIELD_ALIASES = {
    IndicatorType.URL: ["url", "uri", "link", "landing_url"],
    IndicatorType.DOMAIN: ["domain", "domain_name", "hostname", "host"],
    IndicatorType.IP: ["ip", "ip_address", "ipv4", "ipv6"],
    IndicatorType.HASH: [
        "hash",
        "file_hash",
        "sha256",
        "sha256_hash",
        "sha1",
        "sha1_hash",
        "md5",
        "md5_hash",
        "sha512",
        "sha512_hash",
    ],
    IndicatorType.EMAIL: ["email", "email_address"],
}

# Pre-computed lookup for fast case-insensitive comparisons
_ALIAS_TO_TYPE = {
    alias: indicator_type
    for indicator_type, aliases in INDICATOR_FIELD_ALIASES.items()
    for alias in aliases
}
_SUPPORTED_INDICATOR_FIELDS = {
    *PRIMARY_INDICATOR_FIELDS,
    *_ALIAS_TO_TYPE.keys(),
}


def _normalize_raw_value(value: any) -> Optional[str]:
    """Normalize a raw value extracted from ingestion sources."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    # Convert non-string values (e.g., numbers) to string but ignore empty results
    stringified = str(value).strip()
    return stringified or None


def extract_indicator_value_and_type(
    raw_indicator: dict,
) -> Tuple[Optional[str], Optional[IndicatorType], Optional[str]]:
    """
    Extract the indicator value and type from a raw ingestion record.

    Args:
        raw_indicator: Parsed row/object from CSV or JSON

    Returns:
        Tuple of (value, implied_type, source_field)
    """
    if not isinstance(raw_indicator, dict):
        return None, None, None

    # Build a case-insensitive mapping of keys -> original key
    lower_key_map = {}
    for key in raw_indicator.keys():
        if isinstance(key, str):
            lower_key_map[key.lower()] = key

    # First, look for explicit value columns
    for field in PRIMARY_INDICATOR_FIELDS:
        original_key = lower_key_map.get(field)
        if not original_key:
            continue
        value = _normalize_raw_value(raw_indicator.get(original_key))
        if value:
            return value, None, original_key

    # Next, check indicator-type specific aliases
    for alias, indicator_type in _ALIAS_TO_TYPE.items():
        original_key = lower_key_map.get(alias)
        if not original_key:
            continue
        value = _normalize_raw_value(raw_indicator.get(original_key))
        if value:
            return value, indicator_type, original_key

    # Heuristic: any other *_hash field should be treated as a hash
    for lower_key, original_key in lower_key_map.items():
        if "hash" in lower_key and lower_key not in _ALIAS_TO_TYPE:
            value = _normalize_raw_value(raw_indicator.get(original_key))
            if value:
                return value, IndicatorType.HASH, original_key

    return None, None, None


def supported_indicator_fields() -> Tuple[str, ...]:
    """
    Return tuple of supported column/field names for indicator extraction.
    """
    return tuple(sorted(_SUPPORTED_INDICATOR_FIELDS))
