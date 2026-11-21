# Copyright Advanced Software and AI Solutions LLC
"""Environment defaults and tiny .env loader (no python-dotenv)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
STATIC_DIR = ROOT_DIR / "static"
ENV_PATH = ROOT_DIR / ".env"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3000
DEFAULT_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL_ID = "LightOnOCR-3-0.8B"
DEFAULT_LMSTUDIO_TIMEOUT_S = 180
DEFAULT_MAX_UPLOAD_MB = 50
DEFAULT_MAX_PAGES = 200
DEFAULT_RENDER_DPI = 200
DEFAULT_RENDER_MAX_EDGE = 2048
DEFAULT_TEXT_LAYER_MIN_CHARS = 40
EXTRACT_LOCK_WAIT_S = 30


def load_dotenv(path: Path = ENV_PATH) -> dict[str, str]:
    """Load KEY=VALUE pairs from a .env file into os.environ if unset."""
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        if key not in os.environ:
            os.environ[key] = value
    return loaded


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def parse_allowed_hosts(raw: str | None) -> tuple[str, ...]:
    """Parse comma-separated hostnames for Host/Origin checks."""
    if raw is None or str(raw).strip() == "":
        return ()
    names: list[str] = []
    seen: set[str] = set()
    for part in str(raw).split(","):
        item = part.strip().strip('"').strip("'")
        if not item:
            continue
        # Allow optional :port; Host checks add the app port themselves.
        if item.count(":") == 1 and not item.startswith("["):
            host_part, _, maybe_port = item.partition(":")
            if maybe_port.isdigit():
                item = host_part
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return tuple(names)


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    allowed_hosts: tuple[str, ...]
    lmstudio_base_url: str
    model_id: str
    lmstudio_timeout_s: int
    max_upload_mb: int
    max_pages: int
    render_dpi: int
    render_max_edge: int
    text_layer_min_chars: int

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        host=_env_str("HOST", DEFAULT_HOST),
        port=_env_int("PORT", DEFAULT_PORT),
        allowed_hosts=parse_allowed_hosts(os.environ.get("ALLOWED_HOSTS")),
        lmstudio_base_url=_env_str("LMSTUDIO_BASE_URL", DEFAULT_LMSTUDIO_BASE_URL).rstrip("/"),
        model_id=_env_str("MODEL_ID", DEFAULT_MODEL_ID),
        lmstudio_timeout_s=_env_int("LMSTUDIO_TIMEOUT_S", DEFAULT_LMSTUDIO_TIMEOUT_S),
        max_upload_mb=_env_int("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB),
        max_pages=_env_int("MAX_PAGES", DEFAULT_MAX_PAGES),
        render_dpi=_env_int("RENDER_DPI", DEFAULT_RENDER_DPI),
        render_max_edge=_env_int("RENDER_MAX_EDGE", DEFAULT_RENDER_MAX_EDGE),
        text_layer_min_chars=_env_int("TEXT_LAYER_MIN_CHARS", DEFAULT_TEXT_LAYER_MIN_CHARS),
    )
