"""
Custom exceptions for Threat Analysis Agent.
"""


class ThreatAgentException(Exception):
    """Base exception for all Threat Agent errors."""

    pass


class ConfigurationError(ThreatAgentException):
    """Raised when there's a configuration error."""

    pass


class IngestionError(ThreatAgentException):
    """Raised when data ingestion fails."""

    pass


class EnrichmentError(ThreatAgentException):
    """Raised when enrichment fails."""

    pass


class ClassificationError(ThreatAgentException):
    """Raised when classification fails."""

    pass


class DatabaseError(ThreatAgentException):
    """Raised when database operations fail."""

    pass


class ValidationError(ThreatAgentException):
    """Raised when data validation fails."""

    pass


class APIError(ThreatAgentException):
    """Raised when external API calls fail."""

    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded."""

    pass


class TimeoutError(ThreatAgentException):
    """Raised when an operation times out."""

    pass
