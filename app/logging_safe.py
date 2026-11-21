# Copyright Advanced Software and AI Solutions LLC
"""Logging helpers that avoid leaking PII or extracted content."""

from __future__ import annotations

import logging
import re
import uuid

_BASE64_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_LONG_B64_RE = re.compile(r"[A-Za-z0-9+/=]{80,}")


def short_id() -> str:
    return uuid.uuid4().hex[:8]


def redact(message: str) -> str:
    text = _BASE64_RE.sub("[redacted-data-url]", message)
    text = _LONG_B64_RE.sub("[redacted]", text)
    return text


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact(original)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(SafeFormatter("%(levelname)s %(name)s: %(message)s"))
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
