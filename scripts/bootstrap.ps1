param(
    [switch]$Offline,
    [switch]$DownloadWheels
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    python -m venv (Join-Path $Root ".venv")
}

if ($Offline) {
    & $VenvPython -m pip install --no-index --find-links (Join-Path $Root "wheelhouse") -r (Join-Path $Root "requirements-dev.txt")
} else {
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-dev.txt")
}

if ($DownloadWheels) {
    & $VenvPython -m pip download -r (Join-Path $Root "requirements-dev.txt") --dest (Join-Path $Root "wheelhouse")
}

& $VenvPython -c "from app import create_app; print(create_app('testing').url_map)"
