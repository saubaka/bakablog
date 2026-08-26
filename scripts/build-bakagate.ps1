[CmdletBinding()]
param(
    [ValidateSet("all", "linux-x64", "linux-arm64")]
    [string]$Runtime = "all"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectFile = Join-Path $projectRoot "tools\bakagate-manager\bakagate.csproj"
$outputRoot = Join-Path $projectRoot "dist\bakablog"
$legacyOutputRoot = Join-Path $projectRoot "dist\bakagate"
$targets = if ($Runtime -eq "all") { @("linux-x64", "linux-arm64") } else { @($Runtime) }

foreach ($target in $targets) {
    $targetOutput = Join-Path $outputRoot $target
    dotnet publish $projectFile -c Release -r $target --self-contained true -p:PublishSingleFile=true -o $targetOutput
    if ($LASTEXITCODE -ne 0) {
        throw "bakagate publish failed for $target."
    }
    $binary = Join-Path $targetOutput "bakablog"
    if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
        throw "bakablog binary was not created: $binary"
    }
    $legacyTargetOutput = Join-Path $legacyOutputRoot $target
    New-Item -ItemType Directory -Path $legacyTargetOutput -Force | Out-Null
    Copy-Item -LiteralPath $binary -Destination (Join-Path $legacyTargetOutput "bakagate") -Force
    Write-Host "[OK] $binary" -ForegroundColor Green
}
