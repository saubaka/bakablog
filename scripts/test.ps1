$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

& $Python -m ruff check $Root
& $Python -m ruff format --check $Root
& $Python -m pytest
