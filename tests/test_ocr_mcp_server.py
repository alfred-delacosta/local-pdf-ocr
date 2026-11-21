# Copyright Advanced Software and AI Solutions LLC
"""MCP server tool listing and stdio smoke behavior."""

from __future__ import annotations

import asyncio
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import respx

from ocr_mcp.server import create_server, mcp


def test_tools_listed_with_stable_names():
    async def _run():
        tools = await mcp.list_tools()
        return sorted(t.name for t in tools)

    names = asyncio.run(_run())
    assert names == ["ocr_file", "ocr_health", "ocr_list_models"]


@respx.mock
def test_ocr_health_tool_via_in_memory_call(monkeypatch):
    monkeypatch.setenv("OCR_API_URL", "http://127.0.0.1:3000")
    respx.get("http://127.0.0.1:3000/api/health").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "backend": {
                    "url": "http://127.0.0.1:1234/v1",
                    "reachable": True,
                    "latencyMs": 2,
                },
                "model": {"id": "LightOnOCR-3-0.8B", "available": True},
            },
        )
    )

    async def _run():
        server = create_server()
        return await server.call_tool("ocr_health", {})

    result = asyncio.run(_run())
    assert result.is_error is False
    text = "".join(getattr(block, "text", "") or "" for block in result.content)
    assert "healthy" in text.lower() or "LightOnOCR" in text


@respx.mock
def test_ocr_health_api_down_is_tool_error(monkeypatch):
    monkeypatch.setenv("OCR_API_URL", "http://127.0.0.1:3000")
    respx.get("http://127.0.0.1:3000/api/health").mock(side_effect=httpx.ConnectError("down"))

    async def _run():
        try:
            await mcp.call_tool("ocr_health", {})
            return None
        except Exception as exc:
            return str(exc)

    message = asyncio.run(_run())
    assert message is not None
    assert "API not running" in message
    assert "Traceback" not in message


def test_importing_server_writes_nothing_to_stdout():
    buf = io.StringIO()
    with redirect_stdout(buf):

        async def _run():
            server = create_server()
            await server.list_tools()

        asyncio.run(_run())
    assert buf.getvalue() == ""


def test_module_sources_have_no_print():
    import ocr_mcp.client as client_mod
    import ocr_mcp.config as config_mod
    import ocr_mcp.main as main_mod
    import ocr_mcp.paths as paths_mod
    import ocr_mcp.server as server_mod

    for mod in (client_mod, config_mod, main_mod, paths_mod, server_mod):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "print(" not in source


def test_package_does_not_shadow_mcp_sdk():
    import mcp as mcp_sdk

    assert "ocr_mcp" != "mcp"
    assert hasattr(mcp_sdk, "server")
    assert "mcp" in sys.modules
