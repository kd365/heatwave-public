"""Structured JSON logging for CloudWatch Logs Insights.

Usage:
    from backend.utils.logging_config import configure_logging
    configure_logging()

Every log record becomes a single JSON line:
    {
        "timestamp": "2026-03-26T18:33:28.537Z",
        "level": "INFO",
        "logger": "backend.handler",
        "message": "pipeline.complete",
        "run_id": "24a63566-...",
        "duration_ms": 552315,
        "tokens_used": 878788
    }

CloudWatch Logs Insights query example:
    fields @timestamp, level, message, run_id, duration_ms, tokens_used
    | filter message = "pipeline.complete"
    | sort @timestamp desc
"""

import json
import logging
import os


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields passed via logger.info("...", extra={...})
        for key, value in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "message", "module", "msecs", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "taskName",
            }:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure root logger with JSON formatter.

    Call once at module import time in handler.py. Safe to call multiple
    times (idempotent — checks if handler already attached).
    """
    root = logging.getLogger()
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    # Avoid duplicate handlers on Lambda warm starts
    if not any(isinstance(h, logging.StreamHandler) and isinstance(getattr(h, "formatter", None), _JsonFormatter) for h in root.handlers):
        root.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
