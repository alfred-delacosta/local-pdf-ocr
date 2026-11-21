# Copyright Advanced Software and AI Solutions LLC
"""LM Studio OpenAI-compatible client for health, models, and OCR."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.logging_safe import get_logger

log = get_logger(__name__)


class LMStudioError(Exception):
    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class HealthResult:
    url: str
    reachable: bool
    latency_ms: int | None
    model_id: str
    model_available: bool

    def to_public(self) -> dict[str, Any]:
        return {
            "ok": self.reachable and (self.model_available or not self.model_id),
            "backend": {
                "url": self.url,
                "reachable": self.reachable,
                "latencyMs": self.latency_ms,
            },
            "model": {
                "id": self.model_id,
                "available": self.model_available,
            },
        }


def build_data_url(png_bytes: bytes, mime: str = "image/png") -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class LMStudioClient:
    def __init__(self, base_url: str, model_id: str, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout_s = timeout_s

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(timeout=timeout if timeout is not None else self.timeout_s)

    def list_models(self) -> list[str]:
        url = f"{self.base_url}/models"
        try:
            with self._client(timeout=min(30.0, self.timeout_s)) as client:
                resp = client.get(url)
        except httpx.TimeoutException as exc:
            raise LMStudioError("timeout", "Timed out listing models from LM Studio.", 504) from exc
        except httpx.HTTPError as exc:
            raise LMStudioError(
                "backend_unreachable",
                "Could not reach LM Studio to list models.",
                502,
            ) from exc
        if resp.status_code >= 400:
            raise LMStudioError(
                "backend_error",
                f"LM Studio models request failed with status {resp.status_code}.",
                502,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise LMStudioError("backend_error", "LM Studio returned invalid JSON.", 502) from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        models: list[str] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
        return models

    def health(self) -> HealthResult:
        started = time.perf_counter()
        reachable = False
        latency_ms: int | None = None
        available = False
        try:
            models = self.list_models()
            reachable = True
            latency_ms = int((time.perf_counter() - started) * 1000)
            available = self.model_id in models if self.model_id else False
        except LMStudioError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            log.info("health_check_failed id=%s", "backend")
        return HealthResult(
            url=self.base_url,
            reachable=reachable,
            latency_ms=latency_ms,
            model_id=self.model_id,
            model_available=available,
        )

    def ocr_image(self, image_bytes: bytes, mime: str = "image/png") -> str:
        data_url = build_data_url(image_bytes, mime=mime)
        body = {
            "model": self.model_id,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": ""},
                    ],
                }
            ],
        }
        url = f"{self.base_url}/chat/completions"
        try:
            with self._client() as client:
                resp = client.post(url, json=body)
        except httpx.TimeoutException as exc:
            raise LMStudioError(
                "timeout",
                "LM Studio OCR request timed out.",
                504,
            ) from exc
        except httpx.HTTPError as exc:
            raise LMStudioError(
                "backend_unreachable",
                "Could not reach LM Studio for OCR.",
                502,
            ) from exc
        if resp.status_code >= 500:
            raise LMStudioError(
                "backend_error",
                f"LM Studio returned status {resp.status_code}.",
                502,
            )
        if resp.status_code >= 400:
            raise LMStudioError(
                "backend_error",
                f"LM Studio rejected the OCR request ({resp.status_code}).",
                502,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise LMStudioError("backend_error", "LM Studio returned invalid JSON.", 502) from exc
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise LMStudioError("backend_error", "LM Studio response had no choices.", 502)
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LMStudioError("backend_error", "LM Studio response had no text content.", 502)
        return content
