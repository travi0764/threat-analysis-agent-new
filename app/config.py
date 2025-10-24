"""
Configuration management for Threat Analysis Agent.
Loads settings from config.yaml and environment variables.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AppConfig(BaseModel):
    """Application configuration."""

    name: str
    version: str
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000


class DatabaseConfig(BaseModel):
    """Database configuration."""

    type: str = "sqlite"
    path: str = "threat_intelligence.db"
    echo: bool = False


class OpenAIConfig(BaseModel):
    """OpenAI configuration."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2000


class ClassificationConfig(BaseModel):
    """Classification thresholds configuration."""

    high_risk_threshold: float = 7.0
    medium_risk_threshold: float = 4.0
    concurrent_limit: int = 10


class EnrichmentConfig(BaseModel):
    """Enrichment configuration."""

    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 2
    concurrent_limit: int = 5


class DataSourceConfig(BaseModel):
    """Data source configuration."""

    url: str
    enabled: bool = True
    api_key: Optional[str] = None
    rate_limit: int = 60


class SchedulerConfig(BaseModel):
    """Scheduler configuration for autonomous mode."""

    enabled: bool = False
    interval_minutes: int = 60
    max_indicators_per_run: int = 100


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file: str = "logs/threat_agent.log"
    max_bytes: int = 10485760
    backup_count: int = 5


class CORSConfig(BaseModel):
    """CORS configuration."""

    enabled: bool = True
    origins: List[str] = Field(default_factory=list)


class Settings(BaseSettings):
    """Main settings class that loads all configurations."""

    # API Keys from environment
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    abuseipdb_api_key: str = Field(default="", env="ABUSEIPDB_API_KEY")
    malshare_api_key: str = Field(default="", env="MALSHARE_API_KEY")

    # Configuration sections
    app: AppConfig
    database: DatabaseConfig
    openai: OpenAIConfig
    classification: ClassificationConfig
    enrichment: EnrichmentConfig
    data_sources: Dict[str, DataSourceConfig]
    scheduler: SchedulerConfig
    logging: LoggingConfig
    cors: CORSConfig

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_config(config_path: str = "config.yaml") -> Settings:
    """
    Load configuration from YAML file and environment variables.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Settings object with all configurations
    """
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    config_file = project_root / config_path

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    # Load YAML configuration
    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)

    # Replace environment variable placeholders
    config_data = _replace_env_vars(config_data)

    # Create Settings object
    settings = Settings(**config_data)

    # Create logs directory if it doesn't exist
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    return settings


def _replace_env_vars(config: Any) -> Any:
    """
    Recursively replace environment variable placeholders in config.
    Placeholders should be in format: ${VAR_NAME}
    """
    if isinstance(config, dict):
        return {key: _replace_env_vars(value) for key, value in config.items()}
    elif isinstance(config, list):
        return [_replace_env_vars(item) for item in config]
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        var_name = config[2:-1]
        return os.getenv(var_name, "")
    else:
        return config


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance.
    Creates it if it doesn't exist.
    """
    global _settings
    if _settings is None:
        _settings = load_config()
    return _settings


# Convenience function to reload settings
def reload_settings(config_path: str = "config.yaml") -> Settings:
    """Reload settings from configuration file."""
    global _settings
    _settings = load_config(config_path)
    return _settings
