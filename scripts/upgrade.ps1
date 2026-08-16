param(
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "production-env.ps1")

Assert-CloudDiaryProductionEnvironment
if (-not $SkipBackup) {
    & (Join-Path $PSScriptRoot "backup.ps1")
}
& $Python -m flask --app wsgi:app db upgrade
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Database upgrade"
& $Python -m flask --app wsgi:app seed-permissions
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Permission seed"
& $Python -m flask --app wsgi:app system-check
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "System check"
Write-Host "Upgrade checks completed. Restart the application and inspect /readyz."
