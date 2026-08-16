$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "production-env.ps1")

Assert-CloudDiaryProductionEnvironment
& $Python -m pip check
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Dependency check"
& $Python -m flask --app wsgi:app system-check
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "System check"
& $Python -c "import os; from wsgi import app; c=app.test_client(); r=c.get('/healthz', base_url=os.environ['CLOUD_DIARY_SITE_URL']); assert r.status_code == 200, r.status_code; print('Production import and health route check passed.')"
Assert-CloudDiaryCommandSucceeded -ExitCode $LASTEXITCODE -Step "Health route check"
