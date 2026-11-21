# Copyright Advanced Software and AI Solutions LLC
"""FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import router as api_router
from app.config import STATIC_DIR, load_config
from app.logging_safe import configure_logging, get_logger
from app.security import host_allowed, origin_allowed

configure_logging()
log = get_logger(__name__)

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        return response


class HostOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cfg = request.app.state.config
        host = request.headers.get("host")
        origin = request.headers.get("origin")
        if not host_allowed(host, cfg.host, cfg.port):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "forbidden_host",
                        "message": "Request Host header is not allowed.",
                    }
                },
                headers=SECURITY_HEADERS,
            )
        if not origin_allowed(origin, cfg.host, cfg.port):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "forbidden_origin",
                        "message": "Request Origin header is not allowed.",
                    }
                },
                headers=SECURITY_HEADERS,
            )
        return await call_next(request)


def create_app() -> FastAPI:
    cfg = load_config()
    application = FastAPI(title="local-pdf-ocr", docs_url=None, redoc_url=None)
    application.state.config = cfg
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(HostOriginMiddleware)
    application.include_router(api_router)

    static_path = Path(STATIC_DIR)
    if static_path.is_dir():
        application.mount("/static", StaticFiles(directory=str(static_path)), name="static")

        @application.get("/")
        async def index() -> FileResponse:
            return FileResponse(static_path / "index.html")

    return application


app = create_app()
