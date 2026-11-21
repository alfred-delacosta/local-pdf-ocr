# Copyright Advanced Software and AI Solutions LLC
"""Persistent settings override stored in data/settings.json."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_MODEL_ID,
    SETTINGS_PATH,
    AppConfig,
    load_config,
)

_PRINTABLE_RE = re.compile(r"^[\x20-\x7E]+$")


class SettingsValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RuntimeSettings:
    lmstudio_base_url: str
    model_id: str
    defaults: dict[str, Any]

    def to_public(self) -> dict[str, Any]:
        return {
            "lmstudioBaseUrl": self.lmstudio_base_url,
            "modelId": self.model_id,
            "defaults": self.defaults,
        }


def validate_base_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise SettingsValidationError("invalid_url", "LM Studio base URL is required.")
    cleaned = url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise SettingsValidationError(
            "invalid_url",
            "LM Studio base URL must use http or https only.",
        )
    if parsed.username is not None or parsed.password is not None:
        raise SettingsValidationError(
            "invalid_url",
            "LM Studio base URL must not include credentials.",
        )
    if parsed.query or parsed.fragment:
        raise SettingsValidationError(
            "invalid_url",
            "LM Studio base URL must not include a query or fragment.",
        )
    if not parsed.netloc:
        raise SettingsValidationError("invalid_url", "LM Studio base URL is missing a host.")
    return cleaned


def validate_model_id(model_id: str) -> str:
    if not isinstance(model_id, str):
        raise SettingsValidationError("invalid_model", "Model id must be a string.")
    cleaned = model_id.strip()
    if not cleaned or len(cleaned) > 200 or not _PRINTABLE_RE.match(cleaned):
        raise SettingsValidationError(
            "invalid_model",
            "Model id must be 1 to 200 printable characters.",
        )
    return cleaned


def _defaults_from_config(cfg: AppConfig) -> dict[str, Any]:
    return {
        "host": cfg.host,
        "port": cfg.port,
        "allowedHosts": list(cfg.allowed_hosts),
        "lmstudioBaseUrl": cfg.lmstudio_base_url,
        "modelId": cfg.model_id,
        "lmstudioTimeoutS": cfg.lmstudio_timeout_s,
        "maxUploadMb": cfg.max_upload_mb,
        "maxPages": cfg.max_pages,
        "renderDpi": cfg.render_dpi,
        "renderMaxEdge": cfg.render_max_edge,
        "textLayerMinChars": cfg.text_layer_min_chars,
    }


def _read_override(path: Path | None = None) -> dict[str, Any] | None:
    target = path if path is not None else SETTINGS_PATH
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def get_runtime_settings(cfg: AppConfig | None = None) -> RuntimeSettings:
    base = cfg or load_config()
    override = _read_override() or {}
    url = override.get("lmstudioBaseUrl", base.lmstudio_base_url)
    model = override.get("modelId", base.model_id)
    try:
        url = validate_base_url(str(url))
        model = validate_model_id(str(model))
    except SettingsValidationError:
        url = validate_base_url(base.lmstudio_base_url)
        model = validate_model_id(base.model_id)
    return RuntimeSettings(
        lmstudio_base_url=url,
        model_id=model,
        defaults=_defaults_from_config(base),
    )


def save_settings(
    lmstudio_base_url: str,
    model_id: str,
    path: Path | None = None,
) -> RuntimeSettings:
    target = path if path is not None else SETTINGS_PATH
    url = validate_base_url(lmstudio_base_url)
    model = validate_model_id(model_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"lmstudioBaseUrl": url, "modelId": model}
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return get_runtime_settings()


def reset_settings(path: Path | None = None) -> RuntimeSettings:
    target = path if path is not None else SETTINGS_PATH
    if target.is_file():
        target.unlink()
    return get_runtime_settings()


def env_defaults_dict() -> dict[str, str]:
    return {
        "LMSTUDIO_BASE_URL": DEFAULT_LMSTUDIO_BASE_URL,
        "MODEL_ID": DEFAULT_MODEL_ID,
    }


def settings_as_dict(settings: RuntimeSettings) -> dict[str, Any]:
    return asdict(settings)
