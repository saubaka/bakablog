param(
    [string]$Username = "admin",
    [string]$DisplayName = "Site administrator"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

$env:CLOUD_DIARY_ENV = "development"
& $Python -m flask --app wsgi:app site-init --username $Username --display-name $DisplayName
