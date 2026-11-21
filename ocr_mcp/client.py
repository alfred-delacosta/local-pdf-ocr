# Copyright Advanced Software and AI Solutions LLC
"""Async HTTP client for the Phase 1 OCR API (NDJSON extract)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.logging_safe import get_logger, short_id
from ocr_mcp.config import (
    CONNECT_TIMEOUT_S,
    DEFAULT_LMSTUDIO_TIMEOUT_S,
    DEFAULT_MAX_UPLOAD_MB,
    busy_retries,
)

log = get_logger(__name__)

ProgressCallback = Callable[[int, int | None, str], Awaitable[None]]


class ApiClientError(Exception):
    """Mapped API or transport failure for tool errors."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PageMeta:
    page: int
    source: str
    error: str | None = None

    def to_public(self) -> dict[str, Any]:
        out: dict[str, Any] = {"page": self.page, "source": self.source}
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class ExtractResult:
    text: str
    pages: list[PageMeta]
    model: str
    duration_ms: int
    file: dict[str, Any]
    error: dict[str, str] | None = None

    def to_structured(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "text": self.text,
            "pages": [p.to_public() for p in self.pages],
            "model": self.model,
            "durationMs": self.duration_ms,
            "file": self.file,
        }
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class ApiLimits:
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    lmstudio_timeout_s: int = DEFAULT_LMSTUDIO_TIMEOUT_S


def _map_transport_error(exc: Exception) -> ApiClientError:
    if isinstance(exc, httpx.ConnectError):
        return ApiClientError(
            "api_unreachable",
            "API not running: start it with python tasks.py start",
        )
    if isinstance(exc, httpx.TimeoutException):
        return ApiClientError("timeout", "Request to the OCR API timed out.")
    return ApiClientError("api_error", "OCR API request failed.")


def _error_from_body(status: int, body: Any) -> ApiClientError:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "api_error")
            message = str(err.get("message") or "OCR API request failed.")
            if code == "forbidden_host":
                return ApiClientError(
                    code,
                    (
                        "Host header was rejected. Point OCR_API_URL at "
                        "http://127.0.0.1:<port> or the configured HOST value."
                    ),
                )
            if code == "busy":
                return ApiClientError(code, "OCR is busy. Try again shortly.")
            return ApiClientError(code, message)
    return ApiClientError("api_error", f"OCR API returned HTTP {status}.")


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


async def _read_error_body(resp: httpx.Response) -> Any:
    try:
        raw = await resp.aread()
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


async def parse_ndjson_lines(
    lines: list[str],
    *,
    on_progress: ProgressCallback | None = None,
    page_total_hint: int | None = None,
) -> ExtractResult:
    """Parse NDJSON event lines into an ExtractResult (also used by tests)."""
    pages: list[PageMeta] = []
    done: dict[str, Any] | None = None

    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ApiClientError("bad_stream", "NDJSON stream contained invalid JSON.") from exc
        if not isinstance(event, dict):
            raise ApiClientError("bad_stream", "NDJSON stream event was not an object.")
        etype = event.get("type")
        if etype == "page":
            page_no = int(event.get("page") or 0)
            source = str(event.get("source") or "ocr")
            err = event.get("error")
            err_s = str(err) if err else None
            pages.append(PageMeta(page=page_no, source=source, error=err_s))
            if on_progress is not None and page_no > 0:
                total = page_total_hint
                if total:
                    msg = f"page {page_no} of {total}"
                else:
                    msg = f"page {page_no}"
                await on_progress(page_no, total, msg)
        elif etype == "done":
            done = event

    if done is None:
        raise ApiClientError(
            "bad_stream",
            "OCR stream ended without a done event.",
        )

    err_obj = done.get("error")
    if isinstance(err_obj, dict) and err_obj.get("code"):
        raise ApiClientError(
            str(err_obj.get("code")),
            str(err_obj.get("message") or "Extraction failed."),
        )

    if not pages and isinstance(done.get("pages"), list):
        for item in done["pages"]:
            if not isinstance(item, dict):
                continue
            pages.append(
                PageMeta(
                    page=int(item.get("page") or 0),
                    source=str(item.get("source") or "ocr"),
                    error=str(item["error"]) if item.get("error") else None,
                )
            )

    file_meta = done.get("file") if isinstance(done.get("file"), dict) else {}
    return ExtractResult(
        text=str(done.get("text") or ""),
        pages=pages,
        model=str(done.get("model") or ""),
        duration_ms=int(done.get("durationMs") or 0),
        file={
            "name": str(file_meta.get("name") or "upload"),
            "type": str(file_meta.get("type") or "unknown"),
            "pageCount": int(file_meta.get("pageCount") or 0),
        },
    )


class OcrApiClient:
    def __init__(self, base_url: str, *, retries: int | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = busy_retries() if retries is None else retries

    def _client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        # Do not set Origin. Let httpx set Host from the URL.
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    async def get_health(self) -> dict[str, Any]:
        timeout = httpx.Timeout(CONNECT_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
        try:
            async with self._client(timeout) as client:
                resp = await client.get("/api/health")
        except Exception as exc:
            raise _map_transport_error(exc) from exc
        if resp.status_code != 200:
            raise _error_from_body(resp.status_code, _safe_json(resp))
        data = _safe_json(resp)
        if not isinstance(data, dict):
            raise ApiClientError("api_error", "Health response was not JSON.")
        return data

    async def list_models(self) -> dict[str, Any]:
        timeout = httpx.Timeout(CONNECT_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
        try:
            async with self._client(timeout) as client:
                resp = await client.get("/api/models")
        except Exception as exc:
            raise _map_transport_error(exc) from exc
        body = _safe_json(resp)
        if resp.status_code != 200:
            raise _error_from_body(resp.status_code, body)
        if not isinstance(body, dict) or "models" not in body:
            raise ApiClientError("api_error", "Models response was invalid.")
        return {"models": body["models"]}

    async def get_limits(self) -> ApiLimits:
        timeout = httpx.Timeout(CONNECT_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
        try:
            async with self._client(timeout) as client:
                resp = await client.get("/api/settings")
        except Exception:
            log.info("settings_unavailable id=%s falling back to defaults", short_id())
            return ApiLimits()
        if resp.status_code != 200:
            log.info("settings_http id=%s status=%s", short_id(), resp.status_code)
            return ApiLimits()
        body = _safe_json(resp)
        if not isinstance(body, dict):
            return ApiLimits()
        defaults = body.get("defaults")
        if not isinstance(defaults, dict):
            defaults = body
        max_mb = defaults.get("maxUploadMb", DEFAULT_MAX_UPLOAD_MB)
        timeout_s = defaults.get("lmstudioTimeoutS", DEFAULT_LMSTUDIO_TIMEOUT_S)
        try:
            max_mb_i = int(max_mb)
        except (TypeError, ValueError):
            max_mb_i = DEFAULT_MAX_UPLOAD_MB
        try:
            timeout_i = int(timeout_s)
        except (TypeError, ValueError):
            timeout_i = DEFAULT_LMSTUDIO_TIMEOUT_S
        return ApiLimits(max_upload_mb=max_mb_i, lmstudio_timeout_s=timeout_i)

    async def extract_file(
        self,
        *,
        filename: str,
        data: bytes,
        pages: str | None = None,
        force_ocr: bool | None = None,
        on_progress: ProgressCallback | None = None,
        page_total_hint: int | None = None,
    ) -> ExtractResult:
        limits = await self.get_limits()
        read_timeout = float(limits.lmstudio_timeout_s + 60)
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT_S,
            read=read_timeout,
            write=CONNECT_TIMEOUT_S,
            pool=CONNECT_TIMEOUT_S,
        )
        attempts = self.retries + 1
        last_busy: ApiClientError | None = None
        req_id = short_id()

        for attempt in range(attempts):
            try:
                result = await self._extract_once(
                    filename=filename,
                    data=data,
                    pages=pages,
                    force_ocr=force_ocr,
                    timeout=timeout,
                    on_progress=on_progress,
                    page_total_hint=page_total_hint,
                    req_id=req_id,
                )
            except ApiClientError as exc:
                if exc.code == "busy" and attempt + 1 < attempts:
                    last_busy = exc
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise
            log.info(
                "extract_done id=%s pages=%s durationMs=%s",
                req_id,
                result.file.get("pageCount"),
                result.duration_ms,
            )
            return result

        assert last_busy is not None
        raise last_busy

    async def _extract_once(
        self,
        *,
        filename: str,
        data: bytes,
        pages: str | None,
        force_ocr: bool | None,
        timeout: httpx.Timeout,
        on_progress: ProgressCallback | None,
        page_total_hint: int | None,
        req_id: str,
    ) -> ExtractResult:
        files = {"file": (filename, data, "application/octet-stream")}
        fields: dict[str, str] = {}
        if pages:
            fields["pages"] = pages
        if force_ocr is True:
            fields["forceOcr"] = "true"
        elif force_ocr is False:
            fields["forceOcr"] = "false"

        log.info("extract_start id=%s", req_id)
        try:
            async with self._client(timeout) as client:
                async with client.stream(
                    "POST",
                    "/api/extract",
                    files=files,
                    data=fields or None,
                    headers={"Accept": "application/x-ndjson"},
                ) as resp:
                    if resp.status_code == 503:
                        body = await _read_error_body(resp)
                        raise _error_from_body(resp.status_code, body)
                    if resp.status_code >= 400:
                        body = await _read_error_body(resp)
                        raise _error_from_body(resp.status_code, body)
                    lines: list[str] = []
                    async for line in resp.aiter_lines():
                        lines.append(line)
                    return await parse_ndjson_lines(
                        lines,
                        on_progress=on_progress,
                        page_total_hint=page_total_hint,
                    )
        except ApiClientError:
            raise
        except Exception as exc:
            raise _map_transport_error(exc) from exc
