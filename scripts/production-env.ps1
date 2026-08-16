function Assert-CloudDiaryProductionEnvironment {
    if (-not $env:CLOUD_DIARY_SECRET_KEY -or $env:CLOUD_DIARY_SECRET_KEY.Length -lt 32) {
        throw "CLOUD_DIARY_SECRET_KEY must contain at least 32 characters."
    }
    if (-not $env:CLOUD_DIARY_SITE_URL -or $env:CLOUD_DIARY_SITE_URL -notmatch '^https?://[^/]+/?$') {
        throw "CLOUD_DIARY_SITE_URL must be an HTTP or HTTPS origin."
    }
    if (-not $env:CLOUD_DIARY_INSTANCE_PATH) {
        throw "Set CLOUD_DIARY_INSTANCE_PATH to an absolute data directory outside the release."
    }
    if (-not [IO.Path]::IsPathRooted($env:CLOUD_DIARY_INSTANCE_PATH)) {
        throw "CLOUD_DIARY_INSTANCE_PATH must be an absolute path."
    }

    $env:CLOUD_DIARY_ENV = "production"
    foreach ($name in @("data", "uploads", "cache", "logs", "backups", "tmp")) {
        New-Item -ItemType Directory -Path (Join-Path $env:CLOUD_DIARY_INSTANCE_PATH $name) -Force | Out-Null
    }
}

function Assert-CloudDiaryCommandSucceeded {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,
        [Parameter(Mandatory = $true)]
        [string]$Step
    )
    if ($ExitCode -ne 0) {
        throw "$Step failed with exit code $ExitCode."
    }
}
