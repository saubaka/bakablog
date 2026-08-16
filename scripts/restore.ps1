param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "production-env.ps1")

if (-not $ConfirmRestore) {
    throw "Restore overwrites live data. Re-run with -ConfirmRestore after checking the maintenance window and archive."
}
Assert-CloudDiaryProductionEnvironment
$resolvedArchive = (Resolve-Path -LiteralPath $Archive).Path

& $Python -m flask --app wsgi:app site-backup-verify $resolvedArchive
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Backup verification"
& $Python -m flask --app wsgi:app site-restore $resolvedArchive --yes
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Restore"
