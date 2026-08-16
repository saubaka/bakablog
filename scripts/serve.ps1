param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8080,
    [ValidateRange(4, 64)]
    [int]$Threads = 8
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "production-env.ps1")

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local virtual environment is missing. Run scripts\bootstrap.ps1 first."
}

Assert-CloudDiaryProductionEnvironment
if (-not $env:CLOUD_DIARY_TRUST_PROXY_HEADERS) {
    $env:CLOUD_DIARY_TRUST_PROXY_HEADERS = "1"
}
& $Python -m waitress --listen="127.0.0.1:$Port" --threads=$Threads --channel-timeout=120 --ident=CloudDiary wsgi:app
exit $LASTEXITCODE
