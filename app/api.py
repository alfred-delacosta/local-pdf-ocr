# Copyright Advanced Software and AI Solutions LLC
"""HTTP API routes for health, models, settings, and extract."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import AppConfig, load_config
from app.extract import run_extract, run_extract_events
from app.lmstudio import LMStudioClient, LMStudioError
from app.logging_safe import get_logger
from app.security import UploadValidationError, extract_lock, read_upload_limited
from app.settings_store import (
    SettingsValidationError,
    get_runtime_settings,
    reset_settings,
    save_settings,
)

log = get_logger(__name__)
router = APIRouter(prefix="/api")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def get_cfg(request: Request) -> AppConfig:
    return getattr(request.app.state, "config", None) or load_config()


def make_client(request: Request) -> LMStudioClient:
    cfg = get_cfg(request)
    settings = get_runtime_settings(cfg)
    return LMStudioClient(
        base_url=settings.lmstudio_base_url,
        model_id=settings.model_id,
        timeout_s=cfg.lmstudio_timeout_s,
    )


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    client = make_client(request)
    result = client.health()
    # Always HTTP 200; ok false when backend down
    public = result.to_public()
    public["ok"] = bool(result.reachable)
    return public


@router.get("/models", response_model=None)
def models(request: Request) -> JSONResponse | dict[str, Any]:
    client = make_client(request)
    try:
        ids = client.list_models()
    except LMStudioError as exc:
        return error_response(exc.status, exc.code, exc.message)
    return {"models": ids}


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    cfg = get_cfg(request)
    return get_runtime_settings(cfg).to_public()


@router.put("/settings", response_model=None)
async def put_settings(request: Request) -> JSONResponse | dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return error_response(
            415,
            "unsupported_media",
            "Settings PUT requires Content-Type application/json.",
        )
    try:
        payload = await request.json()
    except Exception:
        return error_response(400, "invalid_json", "Request body must be valid JSON.")
    if not isinstance(payload, dict):
        return error_response(400, "invalid_json", "Request body must be a JSON object.")
    url = payload.get("lmstudioBaseUrl")
    model = payload.get("modelId")
    if not isinstance(url, str) or not isinstance(model, str):
        return error_response(
            422,
            "invalid_settings",
            "lmstudioBaseUrl and modelId are required strings.",
        )
    try:
        saved = save_settings(url, model)
    except SettingsValidationError as exc:
        return error_response(422, exc.code, exc.message)
    return saved.to_public()


@router.delete("/settings")
def settings_delete() -> dict[str, Any]:
    return reset_settings().to_public()


def _parse_force_ocr(raw: str | bool | None) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@router.post("/extract", response_model=None)
async def extract(
    request: Request,
    file: Annotated[UploadFile, File()],
    pages: Annotated[str | None, Form()] = None,
    forceOcr: Annotated[str | None, Form()] = None,
    accept: Annotated[str | None, Header(alias="Accept")] = None,
) -> JSONResponse | StreamingResponse:
    cfg = get_cfg(request)
    acquired = await extract_lock.acquire()
    if not acquired:
        return error_response(
            503,
            "busy",
            "Another extraction is in progress. Try again shortly.",
        )

    wants_ndjson = accept is not None and "application/x-ndjson" in accept.lower()
    stream_owns_lock = False

    try:
        data = await read_upload_limited(file, cfg.max_upload_bytes)
        force = _parse_force_ocr(forceOcr)
        client = make_client(request)
        filename = file.filename

        if wants_ndjson:

            def event_stream():
                try:
                    for event in run_extract_events(data, filename, pages, force, cfg, client):
                        yield json.dumps(event, ensure_ascii=False) + "\n"
                except UploadValidationError as exc:
                    yield (
                        json.dumps(
                            {
                                "type": "done",
                                "text": "",
                                "pages": [],
                                "model": client.model_id,
                                "durationMs": 0,
                                "file": {
                                    "name": filename or "upload",
                                    "type": "unknown",
                                    "pageCount": 0,
                                },
                                "error": {"code": exc.code, "message": exc.message},
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                finally:
                    extract_lock.release()

            stream_owns_lock = True
            return StreamingResponse(
                event_stream(),
                media_type="application/x-ndjson",
            )

        try:
            result = run_extract(data, filename, pages, force, cfg, client)
        except UploadValidationError as exc:
            return error_response(exc.status, exc.code, exc.message)
        except LMStudioError as exc:
            return error_response(exc.status, exc.code, exc.message)
        return JSONResponse(content=result.to_public())
    except UploadValidationError as exc:
        return error_response(exc.status, exc.code, exc.message)
    except Exception:
        log.exception("extract_unhandled id=error")
        return error_response(500, "internal_error", "Unexpected server error.")
    finally:
        if not stream_owns_lock:
            extract_lock.release()
