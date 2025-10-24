"""
Centralized logging configuration for Threat Analysis Agent.
Supports both JSON and text format logging.
"""

import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Custom text formatter with color support for console."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as colored text."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname

        if self.use_colors and level in self.COLORS:
            level_colored = f"{self.COLORS[level]}{level}{self.COLORS['RESET']}"
        else:
            level_colored = level

        message = record.getMessage()
        location = f"{record.module}.{record.funcName}:{record.lineno}"

        log_line = f"{timestamp} | {level_colored:8} | {location:30} | {message}"

        # Add exception info if present
        if record.exc_info:
            log_line += "\n" + self.formatException(record.exc_info)

        return log_line


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: Optional[str] = None,
    max_bytes: int = 10485760,
    backup_count: int = 5,
) -> None:
    """
    Setup application-wide logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format ("json" or "text")
        log_file: Path to log file (optional)
        max_bytes: Max size of log file before rotation
        backup_count: Number of backup files to keep
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler with text format (colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(TextFormatter(use_colors=True))

    root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        if log_format == "json":
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(TextFormatter(use_colors=False))

        root_logger.addHandler(file_handler)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging initialized: level={log_level}, format={log_format}, file={log_file}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Convenience method for logging with extra fields
class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that supports extra fields for JSON logging."""

    def process(self, msg, kwargs):
        """Add extra fields to log record."""
        extra = kwargs.get("extra", {})
        if "extra_fields" not in extra:
            extra["extra_fields"] = {}

        # Merge any additional kwargs into extra_fields
        for key, value in kwargs.items():
            if key not in ["extra", "exc_info", "stack_info"]:
                extra["extra_fields"][key] = value

        kwargs["extra"] = extra
        return msg, kwargs


def get_adapter(name: str, **default_extra) -> LoggerAdapter:
    """
    Get a logger adapter with default extra fields.

    Args:
        name: Logger name
        **default_extra: Default extra fields to include in all logs

    Returns:
        LoggerAdapter instance
    """
    logger = get_logger(name)
    return LoggerAdapter(logger, default_extra)
