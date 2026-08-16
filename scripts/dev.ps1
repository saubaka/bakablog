$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

$env:CLOUD_DIARY_ENV = "development"
Push-Location $Root
try {
    & $Python -m flask --app wsgi:app db upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed; Flask was not started."
    }

    & $Python -m flask --app wsgi:app system-check
    if ($LASTEXITCODE -ne 0) {
        throw "Database check failed; Flask was not started."
    }

    & $Python -m flask --app wsgi:app run --host 127.0.0.1 --port 5000 --debug
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $ExitCode
