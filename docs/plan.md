# Grand plan: local-pdf-ocr

Copyright Advanced Software and AI Solutions LLC.

## Goal

Private, offline OCR on a Windows PC using LM Studio (LightOnOCR-3-0.8B), exposed as an HTTP API and a small web UI, with a later MCP tool for Cursor.

## Phase 1 (this branch)

- FastAPI HTTP API: health, models, settings, extract (JSON and NDJSON).
- Static web UI for drop/upload, progress, copy, and settings.
- pypdfium2 for text layer and page rendering; LM Studio OpenAI-compatible chat for OCR.
- Security: Host/Origin checks, magic bytes, upload limits, extraction lock, safe logging.
- Task runner: `python tasks.py <dev|start|test|lint|build>`.

## Phase 2 (after Phase 1 is confirmed)

- Thin MCP server wrapping this API (`ocr_file`, `ocr_health`).
- No MCP work until the API is verified working.

## Out of scope for Phase 1

- Docker, auth, job queue, Docling, alternate OCR backends, CI workflows.
