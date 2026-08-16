param(
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 30,
    [switch]$TruncateWal,
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "production-env.ps1")

Assert-CloudDiaryProductionEnvironment
& $Python -m flask --app wsgi:app db-check
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Database integrity check"
if ($TruncateWal) {
    & $Python -m flask --app wsgi:app db-optimize --truncate
} else {
    & $Python -m flask --app wsgi:app db-optimize
}
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Database optimization"
if (-not $SkipBackup) {
    & $Python -m flask --app wsgi:app site-backup
    Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Maintenance backup"
}

$backupRoot = (Resolve-Path -LiteralPath (Join-Path $env:CLOUD_DIARY_INSTANCE_PATH "backups")).Path
$cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
Get-ChildItem -LiteralPath $backupRoot -Filter "cloud-diary-*.zip" -File |
    Where-Object { $_.LastWriteTimeUtc -lt $cutoff } |
    ForEach-Object {
        $resolved = $_.FullName
        if (-not $resolved.StartsWith($backupRoot + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to delete a path outside the backup directory: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Force
    }
Write-Host "Routine maintenance completed."
