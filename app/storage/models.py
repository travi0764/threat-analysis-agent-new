"""
Database models for Threat Analysis Agent.
Defines ORM models for indicators, enrichments, classifications, and feedback.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class IndicatorType(str, enum.Enum):
    """Enumeration for indicator types."""

    DOMAIN = "domain"
    IP = "ip"
    HASH = "hash"
    URL = "url"
    EMAIL = "email"


class RiskLevel(str, enum.Enum):
    """Enumeration for risk levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class SourceType(str, enum.Enum):
    """Enumeration for data source types."""

    CSV_UPLOAD = "csv_upload"
    JSON_UPLOAD = "json_upload"
    FEED = "feed"
    API_PHISHTANK = "api_phishtank"
    API_ABUSEIPDB = "api_abuseipdb"
    API_MALWAREBAZAAR = "api_malwarebazaar"
    API_OPENPHISH = "api_openphish"
    MANUAL = "manual"


class FeedbackType(str, enum.Enum):
    """Enumeration for feedback types."""

    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    TRUE_NEGATIVE = "true_negative"
    FALSE_NEGATIVE = "false_negative"
    UNCERTAIN = "uncertain"


class Indicator(Base):
    """
    Main table for threat indicators.
    Stores the core indicator information.
    """

    __tablename__ = "indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core indicator data
    indicator_type = Column(Enum(IndicatorType), nullable=False, index=True)
    value = Column(String(500), nullable=False, index=True, unique=True)

    # Source information
    source_type = Column(Enum(SourceType), nullable=False)
    source_name = Column(String(100))
    source_url = Column(String(500))

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Metadata
    raw_data = Column(JSON)  # Store original raw data
    tags = Column(JSON)  # List of tags
    notes = Column(Text)

    # Status
    is_active = Column(Boolean, default=True)

    # Relationships
    enrichments = relationship(
        "Enrichment", back_populates="indicator", cascade="all, delete-orphan"
    )
    classifications = relationship(
        "Classification", back_populates="indicator", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="indicator", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Indicator(type={self.indicator_type.value}, value={self.value[:30]})>"


class Enrichment(Base):
    """
    Stores enrichment data for indicators.
    Multiple enrichments can exist per indicator from different sources.
    """

    __tablename__ = "enrichments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(
        Integer,
        ForeignKey("indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Enrichment metadata
    enrichment_type = Column(
        String(50), nullable=False
    )  # whois, ip_reputation, hash_lookup
    provider = Column(String(100))  # Service provider name

    # Enrichment results
    data = Column(JSON, nullable=False)  # Enrichment data as JSON
    score = Column(Float)  # Normalized risk score (0-10)

    # Timestamps
    enriched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Error handling
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    # Relationship
    indicator = relationship("Indicator", back_populates="enrichments")

    def __repr__(self):
        return f"<Enrichment(type={self.enrichment_type}, provider={self.provider})>"


class Classification(Base):
    """
    Stores classification results for indicators.
    Includes risk level and reasoning.
    """

    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(
        Integer,
        ForeignKey("indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Classification results
    risk_level = Column(Enum(RiskLevel), nullable=False, index=True)
    risk_score = Column(Float, nullable=False)  # Normalized score (0-10)
    confidence = Column(Float)  # Confidence in classification (0-1)

    # Reasoning
    reasoning = Column(Text, nullable=False)  # Structured reasoning steps
    factors = Column(JSON)  # Key factors that influenced classification

    # Model information
    model_name = Column(String(100))
    model_version = Column(String(50))

    # Timestamps
    classified_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    indicator = relationship("Indicator", back_populates="classifications")

    def __repr__(self):
        return (
            f"<Classification(risk={self.risk_level.value}, score={self.risk_score})>"
        )


class Feedback(Base):
    """
    Stores user feedback on classifications.
    Used for model improvement and metrics calculation.
    """

    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(
        Integer,
        ForeignKey("indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Original classification
    original_risk_level = Column(Enum(RiskLevel))

    # User feedback
    feedback_type = Column(Enum(FeedbackType), nullable=False, index=True)
    corrected_risk_level = Column(Enum(RiskLevel))

    # Additional context
    comment = Column(Text)
    user_id = Column(String(100))  # Optional user identifier

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    indicator = relationship("Indicator", back_populates="feedbacks")

    def __repr__(self):
        return f"<Feedback(type={self.feedback_type.value}, indicator_id={self.indicator_id})>"


class AgentRun(Base):
    """
    Tracks autonomous agent runs for monitoring and debugging.
    """

    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Run metadata
    run_type = Column(String(50), nullable=False)  # autonomous, manual
    status = Column(String(50), nullable=False)  # running, completed, failed

    # Statistics
    indicators_processed = Column(Integer, default=0)
    indicators_new = Column(Integer, default=0)
    indicators_updated = Column(Integer, default=0)
    enrichments_performed = Column(Integer, default=0)
    classifications_created = Column(Integer, default=0)

    # Error tracking
    errors_count = Column(Integer, default=0)
    error_details = Column(JSON)

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    # Configuration snapshot
    config_snapshot = Column(JSON)

    def __repr__(self):
        return f"<AgentRun(type={self.run_type}, status={self.status})>"
