import datetime
import json
import logging
import re
from contextvars import ContextVar
from typing import Any, Dict, Optional

# Context variables for request tracing across async and sync call chains
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id_ctx", default=None)
merchant_id_ctx: ContextVar[Optional[str]] = ContextVar("merchant_id_ctx", default=None)

SENSITIVE_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.]+", re.IGNORECASE), r"\1[MASKED_TOKEN]"),
    (re.compile(r'(["\']?(?:client_secret|paypal_client_secret|oidc_jwt_secret|session_secret|password|secret)["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r"\1[MASKED]\3"),
    (re.compile(r"(\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?)(\d{4}\b)"), r"[MASKED_CARD]"),
]


def mask_sensitive_data(message: str) -> str:
    """
    Masks credentials, bearer tokens, passwords, and sensitive identifiers
    from raw text before emission to stdout or persistent logs.
    """
    if not isinstance(message, str):
        message = str(message)

    masked = message
    for pattern, replacement in SENSITIVE_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


class StructuredJsonFormatter(logging.Formatter):
    """
    Custom JSON formatter emitting structured log events with ISO 8601 timestamps,
    correlation IDs, tenant metadata, and automatic sensitive data scrubbing.
    """

    def format(self, record: logging.LogRecord) -> str:
        raw_message = record.getMessage()
        safe_message = mask_sensitive_data(raw_message)

        log_record: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": safe_message,
        }

        # Add correlation ID from contextvar or record attribute
        cid = getattr(record, "correlation_id", None) or correlation_id_ctx.get()
        if cid:
            log_record["correlation_id"] = cid

        # Add merchant tenancy from contextvar or record attribute
        mid = getattr(record, "merchant_id", None) or merchant_id_ctx.get()
        if mid:
            log_record["merchant_id"] = mid

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_logging(level: int = logging.INFO) -> None:
    """Configures root logger with structured JSON formatting."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers
    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(StructuredJsonFormatter())
        root.addHandler(stream_handler)
    else:
        for existing_handler in root.handlers:
            existing_handler.setFormatter(StructuredJsonFormatter())
