"""
Structured and sanitized logging for ExamForge Browser.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Any
from core.config import config

SENSITIVE_PATTERNS = [
    re.compile(r"(password\s*[:=]\s*)([^\s,]+)", re.IGNORECASE),
    re.compile(r"(cookie\s*[:=]\s*)([^\s,]+)", re.IGNORECASE),
    re.compile(r"(authorization\s*[:=]\s*Bearer\s+)([^\s,]+)", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*)([^\s,]+)", re.IGNORECASE),
    re.compile(r"(key\s*[:=]\s*)([A-Za-z0-9_-]{20,})", re.IGNORECASE),
]

class RedactingFormatter(logging.Formatter):
    """Formatter that redacts sensitive credentials and tokens."""
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        sanitized = original
        for pattern in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
        return sanitized

def setup_logger(name: str = "examforge", log_file: Path | None = None) -> logging.Logger:
    """Setup and return a configured logger."""
    config.ensure_directories()
    if log_file is None:
        log_file = config.logs_dir / "examforge.log"

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Rotating file handler (10 MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = RedactingFormatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = RedactingFormatter(
        "%(asctime)s [%(levelname)s] - %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger()
