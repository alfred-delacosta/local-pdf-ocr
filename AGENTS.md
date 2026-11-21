# Agent rules (Phase 1)

Copyright Advanced Software and AI Solutions LLC.

## Stack

- Python + FastAPI + uvicorn + httpx + pypdfium2 + Pillow + python-multipart.
- Static HTML/CSS/JS only (no build step, no CDN, no framework).
- Dev: pytest, respx, ruff. Ask before adding any other dependency.

## Do

- Process uploads in memory or a temp dir deleted in a `finally` block.
- Check magic bytes, not just MIME or extension. Enforce `MAX_UPLOAD_MB` while reading.
- One extraction at a time (lock; wait 30s then 503).
- Empty text prompt for LightOnOCR. PDFs: text layer when healthy, else render PNG and OCR one page at a time.
- Settings in `data/settings.json` override `.env`. Reset deletes the override.
- Visible copy and docs: no em or en dashes. Run `lint:copy` via `python tasks.py lint`.
- Host/Origin must match the app. No CORS. Security headers on every response.

## Do not

- No Docker, compose, or container docs.
- No Python or Node version pins, `.python-version`, or `requires-python`.
- No MCP server or `.cursor/mcp.json` in Phase 1.
- No auth, job queue, Docling, GLM-OCR switch, or GitHub Actions in Phase 1.
- Never commit secrets, personal paths, usernames, or IPs.
- Never log file contents, extracted text, base64, or full filenames.

## Commands

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python tasks.py lint
python tasks.py test
python tasks.py build
python tasks.py start
```
