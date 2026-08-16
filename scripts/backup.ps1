param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "production-env.ps1")
Assert-CloudDiaryProductionEnvironment

if ($Output) {
    & $Python -m flask --app wsgi:app site-backup --output $Output
} else {
    & $Python -m flask --app wsgi:app site-backup
}
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Backup"
