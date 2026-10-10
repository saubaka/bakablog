@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1

rem baka blog Windows local launcher.
rem This file uses cmd.exe only. It does not change system security policies,
rem request administrator rights, download files, or open a browser.

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot enter the baka blog project directory.
  exit /b 1
)

set "CLOUDTRACE_EXIT=0"
set "CLOUDTRACE_CHECK_ONLY=0"
set "CLOUDTRACE_PYTHON=%CD%\.venv\Scripts\python.exe"
set "CLOUDTRACE_REQUIREMENTS=%CD%\requirements.txt"
set "CLOUDTRACE_WHEELHOUSE=%CD%\wheelhouse"

if /I "%~1"=="--check-only" (
  set "CLOUDTRACE_CHECK_ONLY=1"
  shift
)
if not "%~1"=="" (
  echo [ERROR] Unknown option: %~1
  echo Usage: start.bat [--check-only]
  set "CLOUDTRACE_EXIT=2"
  goto :finish
)

if not exist "%CD%\wsgi.py" (
  echo [ERROR] wsgi.py is missing. Run this file from the project directory.
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)
if not exist "%CLOUDTRACE_REQUIREMENTS%" (
  echo [ERROR] requirements.txt is missing.
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)

if not exist "%CLOUDTRACE_PYTHON%" (
  echo [SETUP] Creating the local Python virtual environment...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv ".venv"
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo [ERROR] Python was not found. Install Python 3.11, 3.12, 3.13, or 3.14 first.
      set "CLOUDTRACE_EXIT=1"
      goto :finish
    )
    python -m venv ".venv"
  )
  if errorlevel 1 (
    echo [ERROR] The local virtual environment could not be created.
    set "CLOUDTRACE_EXIT=1"
    goto :finish
  )
)

"%CLOUDTRACE_PYTHON%" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)"
if errorlevel 1 (
  echo [ERROR] baka blog requires Python 3.11, 3.12, 3.13, or 3.14.
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)

"%CLOUDTRACE_PYTHON%" -c "import flask, flask_login, flask_migrate, flask_sqlalchemy, flask_wtf, PIL, sqlalchemy" >nul 2>&1
if errorlevel 1 (
  if not exist "%CLOUDTRACE_WHEELHOUSE%\*.whl" (
    echo [ERROR] Python dependencies are missing and the local wheelhouse is empty.
    echo No network download was attempted.
    set "CLOUDTRACE_EXIT=1"
    goto :finish
  )
  echo [SETUP] Installing dependencies from the local wheelhouse...
  "%CLOUDTRACE_PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links "%CLOUDTRACE_WHEELHOUSE%" -r "%CLOUDTRACE_REQUIREMENTS%"
  if errorlevel 1 (
    echo [ERROR] Local dependency installation failed.
    set "CLOUDTRACE_EXIT=1"
    goto :finish
  )
)

"%CLOUDTRACE_PYTHON%" -m pip check >nul
if errorlevel 1 (
  echo [ERROR] The local Python environment has broken or conflicting packages.
  echo Run: .venv\Scripts\python.exe -m pip check
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)

if not defined CLOUD_DIARY_ENV set "CLOUD_DIARY_ENV=development"
if not defined CLOUD_DIARY_HOST set "CLOUD_DIARY_HOST=127.0.0.1"
if not defined CLOUD_DIARY_PORT set "CLOUD_DIARY_PORT=5010"
set "PYTHONUTF8=1"

"%CLOUDTRACE_PYTHON%" -c "import sys; p=sys.argv[1]; raise SystemExit(0 if p.isascii() and p.isdigit() and p == str(int(p)) and 1024 <= int(p) <= 65535 else 2)" "%CLOUD_DIARY_PORT%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] CLOUD_DIARY_PORT must be a number from 1024 to 65535.
  set "CLOUDTRACE_EXIT=2"
  goto :finish
)

if "%CLOUDTRACE_CHECK_ONLY%"=="1" goto :port_ready
set "CLOUDTRACE_INITIAL_PORT=%CLOUD_DIARY_PORT%"
set /a CLOUDTRACE_PORT_LIMIT=CLOUD_DIARY_PORT+20 >nul
if %CLOUDTRACE_PORT_LIMIT% GTR 65535 set "CLOUDTRACE_PORT_LIMIT=65535"

:probe_port
"%CLOUDTRACE_PYTHON%" -c "import socket,sys; sock=socket.socket(); sock.bind((sys.argv[1], int(sys.argv[2]))); sock.close()" "%CLOUD_DIARY_HOST%" "%CLOUD_DIARY_PORT%" >nul 2>&1
if not errorlevel 1 goto :port_ready
if %CLOUD_DIARY_PORT% GEQ %CLOUDTRACE_PORT_LIMIT% (
  echo [ERROR] No available local port near %CLOUDTRACE_INITIAL_PORT%.
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)
set /a CLOUD_DIARY_PORT+=1 >nul
goto :probe_port

:port_ready
if not "%CLOUDTRACE_CHECK_ONLY%"=="1" if not "%CLOUD_DIARY_PORT%"=="%CLOUDTRACE_INITIAL_PORT%" echo [INFO] Preferred port is busy. Using port %CLOUD_DIARY_PORT%.
set "CLOUD_DIARY_SITE_URL=http://%CLOUD_DIARY_HOST%:%CLOUD_DIARY_PORT%"

echo.
echo [1/3] Applying local SQLite migrations...
"%CLOUDTRACE_PYTHON%" -m flask --app wsgi:app db upgrade
if errorlevel 1 (
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)

echo.
echo [2/3] Running the baka blog system check...
"%CLOUDTRACE_PYTHON%" -m flask --app wsgi:app system-check
if errorlevel 1 (
  set "CLOUDTRACE_EXIT=1"
  goto :finish
)

if "%CLOUDTRACE_CHECK_ONLY%"=="1" (
  echo.
  echo [OK] Startup validation passed. Flask was not started.
  goto :finish
)

echo.
echo [3/3] Starting baka blog...
echo URL: %CLOUD_DIARY_SITE_URL%
echo First visit: open this URL and create the administrator in the browser.
echo Press Ctrl+C to stop the local server.
echo.
"%CLOUDTRACE_PYTHON%" -m flask --app wsgi:app run --host "%CLOUD_DIARY_HOST%" --port "%CLOUD_DIARY_PORT%" --no-debug --no-debugger --no-reload
set "CLOUDTRACE_EXIT=%ERRORLEVEL%"

:finish
if not "%CLOUDTRACE_EXIT%"=="0" (
  echo.
  echo [FAILED] baka blog did not start. Review the message above and try again.
  if not defined CLOUDTRACE_NO_PAUSE pause
)
popd >nul 2>&1
endlocal & exit /b %CLOUDTRACE_EXIT%
