# Copyright Advanced Software and AI Solutions LLC
"""Resolve OCR API base URL and MCP-related environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import DEFAULT_HOST, DEFAULT_PORT, load_dotenv

DEFAULT_API_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
DEFAULT_BUSY_RETRIES = 2
DEFAULT_MAX_UPLOAD_MB = 50
DEFAULT_LMSTUDIO_TIMEOUT_S = 180
CONNECT_TIMEOUT_S = 5.0


class ConfigError(Exception):
    """Invalid MCP / API URL configuration."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _normalize_host(host: str) -> str:
    cleaned = (host or "").strip()
    if cleaned in {"", "0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    if cleaned.startswith("[") and cleaned.endswith("]"):
        return cleaned[1:-1]
    return cleaned


def validate_api_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ConfigError("OCR API URL is empty.")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ConfigError("OCR API URL must use http or https.")
    if parsed.username or parsed.password:
        raise ConfigError("OCR API URL must not include credentials.")
    if parsed.query:
        raise ConfigError("OCR API URL must not include a query string.")
    if not parsed.hostname:
        raise ConfigError("OCR API URL must include a host.")
    path = parsed.path.rstrip("/")
    if path not in {"", "/"}:
        raise ConfigError("OCR API URL must not include a path.")
    netloc = parsed.netloc
    return f"{parsed.scheme}://{netloc}"


def build_api_url(
    *,
    ocr_api_url: str | None = None,
    host: str | None = None,
    port: str | int | None = None,
    load_env_file: bool = True,
) -> str:
    """Build the API base URL. OCR_API_URL wins when set."""
    if load_env_file:
        load_dotenv()

    env_url = ocr_api_url if ocr_api_url is not None else os.environ.get("OCR_API_URL")
    if env_url is not None and str(env_url).strip():
        return validate_api_url(str(env_url))

    env_host = host if host is not None else os.environ.get("HOST", DEFAULT_HOST)
    env_port = port if port is not None else os.environ.get("PORT", DEFAULT_PORT)
    try:
        port_i = int(str(env_port).strip() or DEFAULT_PORT)
    except ValueError as exc:
        raise ConfigError("PORT must be an integer.") from exc
    if port_i < 1 or port_i > 65535:
        raise ConfigError("PORT must be between 1 and 65535.")
    normalized = _normalize_host(str(env_host) if env_host is not None else DEFAULT_HOST)
    if ":" in normalized and not normalized.startswith("["):
        # IPv6 literal without brackets
        return validate_api_url(f"http://[{normalized}]:{port_i}")
    return validate_api_url(f"http://{normalized}:{port_i}")


def busy_retries() -> int:
    raw = os.environ.get("OCR_BUSY_RETRIES")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_BUSY_RETRIES
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ConfigError("OCR_BUSY_RETRIES must be an integer.") from exc
    if value < 0:
        raise ConfigError("OCR_BUSY_RETRIES must be >= 0.")
    return value


@dataclass(frozen=True)
class McpRuntimeConfig:
    api_url: str
    busy_retries: int


def load_mcp_config() -> McpRuntimeConfig:
    return McpRuntimeConfig(api_url=build_api_url(), busy_retries=busy_retries())
