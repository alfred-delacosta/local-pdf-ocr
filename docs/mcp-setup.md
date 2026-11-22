# MCP setup for Cursor and Hermes

Copyright Advanced Software and AI Solutions LLC.

Step-by-step Windows guide for the stdio MCP server `local-pdf-ocr` (`python -m ocr_mcp`). Tools: `ocr_file`, `ocr_health`, `ocr_list_models`.

Placeholder paths use `C:\path\to\local-pdf-ocr`. Example: if the repo is at `C:\Users\<you>\Projects\local-pdf-ocr`, the command is `C:\Users\<you>\Projects\local-pdf-ocr\.venv\Scripts\python.exe`.

## 1. Prerequisites

1. Start LM Studio, load your OCR model (default id `LightOnOCR-3-0.8B`), and start its local server (default `http://127.0.0.1:1234/v1`).
2. Create the venv once, then install (or let `.\start.ps1` install into an existing `.venv`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

3. Start the API (copies `.env.example` to `.env` if missing when using `start.ps1`):

```powershell
.\start.ps1
```

Or: `python tasks.py start`. Default base URL is `http://127.0.0.1:3000`. Confirm with `http://127.0.0.1:3000/api/health`.

## 2. Cursor, project level

This repo already ships [`.cursor/mcp.json`](../.cursor/mcp.json):

```json
{
  "mcpServers": {
    "local-pdf-ocr": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "ocr_mcp"],
      "env": {
        "OCR_API_URL": "http://127.0.0.1:3000"
      }
    }
  }
}
```

1. Open this repository folder in Cursor.
2. Open **Customize** (Cursor docs) / MCP settings and enable `local-pdf-ocr`.
3. Confirm the server is green and shows 3 tools.
4. In chat: `Run ocr_health`, then `Use ocr_file on C:\path\to\sample.pdf`.
5. From a shell in the repo: `python tasks.py mcp-check` (lists tools and calls `ocr_health`).

## 3. Cursor, global

Edit `%USERPROFILE%\.cursor\mcp.json` so the tools work outside this workspace. Use an absolute path to this repo's venv Python. JSON needs doubled backslashes or forward slashes.

Official Cursor STDIO fields are `command`, `args`, `env`, and `envFile` (no `cwd`). Omit `cwd`; with an editable install, `ocr_mcp` loads the repo `.env` from the package location on its own. Process env wins; `.env` only fills unset keys.

```json
{
  "mcpServers": {
    "local-pdf-ocr": {
      "command": "C:\\path\\to\\local-pdf-ocr\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ocr_mcp"],
      "env": {
        "OCR_API_URL": "http://127.0.0.1:3000"
      }
    }
  }
}
```

## 4. Environment variables

MCP process (and repo `.env` when unset in the process):

| Name | What it does | Default |
| --- | --- | --- |
| `OCR_API_URL` | API base URL. Wins when set. `http` or `https` only; no credentials, query, or path. | Built from `HOST`/`PORT` (`0.0.0.0` or `::` becomes `127.0.0.1`); else `http://127.0.0.1:3000` |
| `OCR_ALLOWED_ROOTS` | Extra folder allowlist. Separated by `os.pathsep` (`;` on Windows, `:` on macOS/Linux). Resolved file must sit under one root. | Unset: no extra folder filter |
| `OCR_BUSY_RETRIES` | Extra attempts after HTTP 503 busy | `2` |

Fixed (not configurable): connect timeout 5 s; per-page read timeout is the API's `lmstudioTimeoutS` (default 180) plus 60.

API side that matters for MCP: `HOST`, `PORT` (default `3000`), `ALLOWED_HOSTS` (otherwise Host/Origin can yield 403 `forbidden_host`), `LMSTUDIO_BASE_URL` (default `http://127.0.0.1:1234/v1`), `MODEL_ID` (default `LightOnOCR-3-0.8B`), `LMSTUDIO_TIMEOUT_S`. Upload size for `ocr_file` follows the API `maxUploadMb` (default 50).

`ocr_file` needs an absolute path to `.pdf`, `.png`, `.jpg`, `.jpeg`, or `.webp`. UNC and device paths are refused.

## 5. Hermes CLI

In `~/.hermes/config.yaml` under `mcp_servers`:

```yaml
mcp_servers:
  local-pdf-ocr:
    command: C:/path/to/local-pdf-ocr/.venv/Scripts/python.exe
    args: ["-m", "ocr_mcp"]
    cwd: C:/path/to/local-pdf-ocr
    env:
      OCR_API_URL: http://127.0.0.1:3000
```

Then run `/reload-mcp` or start a new chat.

## 6. Hermes Desktop

Use the **Connect to a custom MCP** dialog:

1. Clear the snippet box.
2. Name: `local-pdf-ocr`
3. Type: STDIO
4. Command: `C:\path\to\local-pdf-ocr\.venv\Scripts\python.exe`
5. Arguments: `-m` and `ocr_mcp` as two separate entries
6. Env: `OCR_API_URL` = `http://127.0.0.1:3000`
7. Leave passthrough empty
8. Working directory: `C:\path\to\local-pdf-ocr`
9. Save

## 7. Troubleshooting

| Symptom | What to try |
| --- | --- |
| API not running / connection refused | Start with `.\start.ps1` or `python tasks.py start`. Check `/api/health`. |
| Wrong Python path / missing `.venv` | `python -m venv .venv`, then `pip install -e ".[dev]"`. Point command at `.venv\Scripts\python.exe` with an absolute path. |
| 403 `forbidden_host` | Point `OCR_API_URL` at `http://127.0.0.1:<port>`, the configured `HOST`, or a name listed in `ALLOWED_HOSTS`. |
| Path refused | Must be absolute; not UNC/device; allowed extension; under size limit; inside `OCR_ALLOWED_ROOTS` when that env is set. |
| OCR busy | One extraction at a time (API waits then 503). Raise `OCR_BUSY_RETRIES` only if needed. |
| LM Studio unreachable / model not loaded | Check `LMSTUDIO_BASE_URL`, `MODEL_ID`, run `ocr_health`, or use the web UI Settings. |
