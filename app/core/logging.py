"""Structured JSON logging configuration."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Format application logs as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        reserved = set(logging.makeLogRecord({}).__dict__)
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": settings.app_name,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in reserved and key != "color_message" and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure root logging for API and worker processes."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
