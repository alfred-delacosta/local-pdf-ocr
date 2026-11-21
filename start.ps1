# Copyright Advanced Software and AI Solutions LLC
# Install deps (if needed), ensure .env, and start the app using the existing .venv.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Error "Missing .venv. Run once: python -m venv .venv"
  exit 1
}

& $python -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
}

& $python tasks.py start
exit $LASTEXITCODE
