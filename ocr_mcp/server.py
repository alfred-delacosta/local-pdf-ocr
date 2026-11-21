# Copyright Advanced Software and AI Solutions LLC
"""MCP tool registration for local PDF OCR."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from app.logging_safe import configure_logging, get_logger
from ocr_mcp.client import ApiClientError, OcrApiClient
from ocr_mcp.config import ConfigError, load_mcp_config
from ocr_mcp.paths import PathValidationError, validate_ocr_path

configure_logging()
log = get_logger(__name__)

mcp = MCPServer("local-pdf-ocr")


def _tool_error(code: str, message: str) -> ToolError:
    return ToolError(f"{code}: {message}")


def _client() -> OcrApiClient:
    try:
        cfg = load_mcp_config()
    except ConfigError as exc:
        raise _tool_error("invalid_config", exc.message) from exc
    return OcrApiClient(cfg.api_url, retries=cfg.busy_retries)


def _health_sentence(health: dict[str, Any]) -> str:
    backend = health.get("backend") if isinstance(health.get("backend"), dict) else {}
    model = health.get("model") if isinstance(health.get("model"), dict) else {}
    reachable = bool(backend.get("reachable"))
    available = bool(model.get("available"))
    if not reachable:
        return "LM Studio unreachable"
    if not available:
        return "model not loaded"
    return "OCR API and LM Studio look healthy"


def _count_pages_hint(pages: str | None) -> int | None:
    if not pages or not pages.strip():
        return None
    total = 0
    for part in pages.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            left, _, right = item.partition("-")
            try:
                start = int(left.strip())
                end = int(right.strip())
            except ValueError:
                return None
            if end < start:
                return None
            total += end - start + 1
        else:
            try:
                int(item)
            except ValueError:
                return None
            total += 1
    return total or None


@mcp.tool(name="ocr_health")
async def ocr_health() -> dict[str, Any]:
    """Check the local OCR API and LM Studio health."""
    client = _client()
    try:
        health = await client.get_health()
    except ApiClientError as exc:
        raise _tool_error(exc.code, exc.message) from exc
    sentence = _health_sentence(health)
    return {"health": health, "message": sentence}


@mcp.tool(name="ocr_list_models")
async def ocr_list_models() -> dict[str, Any]:
    """List model ids available from the local OCR API / LM Studio."""
    client = _client()
    try:
        return await client.list_models()
    except ApiClientError as exc:
        raise _tool_error(exc.code, exc.message) from exc


@mcp.tool(name="ocr_file")
async def ocr_file(
    path: Annotated[
        str,
        Field(
            description=(
                "Absolute filesystem path to a local .pdf, .png, .jpg, .jpeg, or .webp file. "
                "Relative paths are rejected. Example: C:\\Users\\me\\Documents\\scan.pdf"
            ),
        ),
    ],
    ctx: Context,
    pages: Annotated[
        str | None,
        Field(
            description='Optional page selection using API syntax (for example "1-3,5").',
        ),
    ] = None,
    forceOcr: Annotated[
        bool | None,
        Field(
            description="When true, skip the PDF text layer and OCR every selected page.",
        ),
    ] = None,
) -> CallToolResult:
    """OCR a local PDF or image. Requires an absolute filesystem path.

    path must be an absolute filesystem path. Relative paths are rejected.
    Optional pages uses the same syntax as the API (for example "1-3,5").
    Set forceOcr true to skip the PDF text layer.
    """
    client = _client()
    try:
        limits = await client.get_limits()
        resolved, data = validate_ocr_path(path, max_upload_mb=limits.max_upload_mb)
    except PathValidationError as exc:
        raise _tool_error(exc.code, exc.message) from exc
    except ApiClientError as exc:
        raise _tool_error(exc.code, exc.message) from exc

    async def on_progress(progress: int, total: int | None, message: str) -> None:
        try:
            await ctx.report_progress(float(progress), float(total) if total else None, message)
        except Exception:
            # Progress is best-effort when the client does not support it.
            return

    try:
        result = await client.extract_file(
            filename=resolved.name,
            data=data,
            pages=pages,
            force_ocr=forceOcr,
            on_progress=on_progress,
            page_total_hint=_count_pages_hint(pages),
        )
    except ApiClientError as exc:
        raise _tool_error(exc.code, exc.message) from exc

    structured = result.to_structured()
    return CallToolResult(
        content=[TextContent(type="text", text=result.text)],
        structuredContent=structured,
    )


def create_server() -> MCPServer:
    return mcp
