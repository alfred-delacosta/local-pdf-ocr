# local-pdf-ocr

Private, offline OCR for images and PDFs on your Windows PC. A FastAPI HTTP API and a small web UI talk to your local LM Studio model (LightOnOCR-3-0.8B).

Copyright Advanced Software and AI Solutions LLC.

This UI is not a replacement for the API. Both share the same extraction core.

## LM Studio setup

1. Install and open LM Studio.
2. Download LightOnOCR-3-0.8B and load it.
3. If the model needs a multimodal projector, the mmproj file name must start with `mmproj`.
4. Start the local server (OpenAI-compatible API). Default base URL: `http://127.0.0.1:1234/v1`.
5. Eject other models so VRAM stays free (RTX 2080 Super, 8 GB).

## Install and run (Windows PowerShell)

```powershell
git clone https://github.com/alfred-delacosta/local-pdf-ocr.git
cd local-pdf-ocr
git checkout main
git pull
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python tasks.py start
```

Open `http://127.0.0.1:3000` in your browser.

### Linux / macOS (same app)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python tasks.py start
```

### Task runner

| Command | What it does |
| --- | --- |
| `python tasks.py dev` | uvicorn with reload |
| `python tasks.py start` | uvicorn on HOST and PORT from `.env` |
| `python tasks.py test` | pytest |
| `python tasks.py lint` | ruff check, ruff format --check, lint:copy |
| `python tasks.py build` | lint, test, compileall, static file check |

## Environment

Copy `.env.example` to `.env`. Defaults:

| Key | Default | Notes |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Binding `0.0.0.0` or a LAN IP exposes the app with no login |
| `PORT` | `3000` | Example: set `PORT=4000` then start again |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | Trailing slash trimmed |
| `MODEL_ID` | `LightOnOCR-3-0.8B` | UI can list and pick from `/api/models` |
| `LMSTUDIO_TIMEOUT_S` | `180` | Per page |
| `MAX_UPLOAD_MB` | `50` | Enforced while reading the upload |
| `MAX_PAGES` | `200` | Per request |
| `RENDER_DPI` | `200` | Lower this if VRAM is tight |
| `RENDER_MAX_EDGE` | `2048` | Longest side after render, aspect kept |
| `TEXT_LAYER_MIN_CHARS` | `40` | Below this, page goes to OCR |

## Settings

The UI Settings panel can change LM Studio URL and model id. Save writes `data/settings.json` (gitignored), which overrides `.env`. Reset to defaults deletes that file. Restart keeps the saved override.

## How extraction works

- Images (PNG, JPEG, WebP): shrink if needed, then OCR via LM Studio.
- PDFs: each selected page uses the text layer when it looks healthy; otherwise the page is rendered to PNG and OCR'd. One page at a time.
- `forceOcr=true` skips the text layer.
- Empty LightOn text prompt (no instructions added).

## API reference

Base URL examples use `http://127.0.0.1:3000`.

### Health

```powershell
curl.exe -s http://127.0.0.1:3000/api/health
```

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/health
```

Always HTTP 200. `ok` is false when LM Studio is down.

### Models

```powershell
curl.exe -s http://127.0.0.1:3000/api/models
```

### Settings

```powershell
curl.exe -s http://127.0.0.1:3000/api/settings
curl.exe -s -X PUT http://127.0.0.1:3000/api/settings -H "Content-Type: application/json" -d "{\"lmstudioBaseUrl\":\"http://127.0.0.1:1234/v1\",\"modelId\":\"LightOnOCR-3-0.8B\"}"
curl.exe -s -X DELETE http://127.0.0.1:3000/api/settings
```

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/settings
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:3000/api/settings -ContentType "application/json" -Body '{"lmstudioBaseUrl":"http://127.0.0.1:1234/v1","modelId":"LightOnOCR-3-0.8B"}'
Invoke-RestMethod -Method Delete -Uri http://127.0.0.1:3000/api/settings
```

### Extract (JSON)

PowerShell 7+ (`-Form`):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:3000/api/extract -Form @{ file = Get-Item .\sample.pdf }
```

Windows PowerShell 5.1 (use curl.exe):

```powershell
curl.exe -s -X POST http://127.0.0.1:3000/api/extract -F "file=@sample.pdf"
curl.exe -s -X POST http://127.0.0.1:3000/api/extract -F "file=@scan.pdf" -F "pages=1-3,5" -F "forceOcr=true"
curl.exe -s -X POST http://127.0.0.1:3000/api/extract -F "file=@page.png"
```

### Extract (NDJSON progress)

```powershell
curl.exe -s -X POST http://127.0.0.1:3000/api/extract -H "Accept: application/x-ndjson" -F "file=@scan.pdf"
```

One JSON object per page (`type=page`), then a final `type=done` object with the full result.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Health shows LM Studio unreachable | Start the LM Studio server; confirm URL in Settings |
| Timeouts on large scans | Raise `LMSTUDIO_TIMEOUT_S`, or OCR fewer pages |
| VRAM / out of memory | Eject other models; lower `RENDER_DPI` (for example 150) |
| Wrong Host / Origin errors | Use the same host and port the app binds to |
| Upload rejected | Check magic bytes (real PNG/JPEG/WebP/PDF) and `MAX_UPLOAD_MB` |

## Security notes

- No login. Keep `HOST=127.0.0.1` unless you accept LAN exposure.
- Host and Origin must match the app. No CORS.
- Uploads are size-limited and typed by magic bytes. Temp files are cleaned up.
- Logs never include extracted text, base64, or full filenames.

## Phase 2: MCP

After this API is confirmed working, Phase 2 adds a thin Cursor MCP server (`ocr_file`, `ocr_health`) that wraps these endpoints. Not included in Phase 1.
