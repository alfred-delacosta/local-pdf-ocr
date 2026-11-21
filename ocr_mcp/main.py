# Copyright Advanced Software and AI Solutions LLC
"""stdio entrypoint for the local PDF OCR MCP server."""

from __future__ import annotations

from app.logging_safe import configure_logging
from ocr_mcp.server import create_server


def main() -> int:
    configure_logging()
    server = create_server()
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
