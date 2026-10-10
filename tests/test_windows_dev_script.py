from pathlib import Path


def test_windows_development_script_migrates_before_starting_flask():
    script = Path("scripts/dev.ps1").read_text(encoding="utf-8")

    migration = script.index("db upgrade")
    system_check = script.index("system-check")
    server_start = script.index("run --host 127.0.0.1 --port 5000 --debug")

    assert migration < system_check < server_start
    assert script.count("$LASTEXITCODE -ne 0") == 2


def test_cmd_launcher_is_local_only_and_checks_before_starting_flask():
    script = Path("start.bat").read_text(encoding="utf-8")
    normalized = script.lower()

    migration = normalized.index("db upgrade")
    system_check = normalized.index("system-check")
    server_start = normalized.index("run --host")

    assert migration < system_check < server_start
    assert "--check-only" in normalized
    assert "--no-index" in normalized
    assert "wheelhouse" in normalized
    assert "%~dp0" in normalized
    assert "powershell.exe" not in normalized
    assert ".ps1" not in normalized
    assert "executionpolicy" not in normalized
    assert "bypass" not in normalized
    assert "curl" not in normalized
    assert "certutil" not in normalized
