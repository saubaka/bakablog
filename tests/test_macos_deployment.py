from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_macos_shell_scripts_are_posix_syntax_valid():
    for relative in (
        "start-macos.sh",
        "deploy-macos.sh",
        "scripts/macos-run.sh",
        "scripts/manage-macos.sh",
    ):
        subprocess.run(
            ["/bin/sh", "-n", str(ROOT / relative)],
            check=True,
            capture_output=True,
            text=True,
        )


def test_macos_local_launcher_preserves_windows_environment():
    script = (ROOT / "start-macos.sh").read_text(encoding="utf-8")
    assert '.venv-macos' in script
    assert 'CLOUD_DIARY_ENV=development' in script
    assert '127.0.0.1' in script
    assert '--no-debugger --no-reload' in script
    assert 'rm -rf' not in script
    assert '.venv/Scripts' not in script


def test_macos_deployment_is_rootless_loopback_launchd_service():
    deploy = (ROOT / "deploy-macos.sh").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/macos-run.sh").read_text(encoding="utf-8")
    manager = (ROOT / "scripts/manage-macos.sh").read_text(encoding="utf-8")

    assert 'com.saubaka.bakablog' in deploy
    assert 'Library/Application Support/BakaBlog' in deploy
    assert 'Library/LaunchAgents' in deploy
    assert 'RunAtLoad' in deploy
    assert 'KeepAlive' in deploy
    assert 'merge --ff-only "origin/$BRANCH"' in deploy
    assert 'reset --hard' not in deploy
    assert 'without sudo' in deploy
    assert 'CLOUD_DIARY_SITE_URL' in deploy
    assert 'value.scheme == "https"' in deploy
    assert '--header "X-Forwarded-Proto: https"' in deploy
    assert "--noproxy '*'" in deploy
    assert '--bind "127.0.0.1:${PORT}"' in runner
    assert '0.0.0.0' not in runner
    assert 'launchctl bootstrap' in manager
    assert 'launchctl bootout' in manager
    assert 'system-check' in manager
    assert "--noproxy '*'" in manager


def test_macos_docs_keep_windows_and_linux_entry_points():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    macos_doc = (ROOT / "docs/phase-9/deployment-macos.md").read_text(encoding="utf-8")

    assert 'start.bat' in readme
    assert 'deploy-linux.sh' in readme
    assert 'start-macos.sh' in readme
    assert 'deploy-macos.sh' in readme
    assert 'launchd' in readme
    assert 'HTTPS反向代理' in macos_doc
    assert 'Windows' in macos_doc
    assert 'systemd' in macos_doc


def test_macos_assets_are_identical_in_bakagit_and_windows_files_remain():
    mirrored = (
        Path("README.md"),
        Path(".env.production.example"),
        Path(".gitignore"),
        Path("start-macos.sh"),
        Path("deploy-macos.sh"),
        Path("scripts/macos-run.sh"),
        Path("scripts/manage-macos.sh"),
        Path("docs/phase-9/deployment-macos.md"),
    )
    for relative in mirrored:
        assert (ROOT / relative).read_bytes() == (ROOT / "bakagit" / relative).read_bytes()

    windows_files = (
        Path("start.bat"),
        Path("bakablog.exe"),
        Path("scripts/bootstrap.ps1"),
        Path("scripts/serve.ps1"),
        Path("scripts/preflight.ps1"),
    )
    for relative in windows_files:
        assert (ROOT / relative).is_file()
        if relative != Path("bakablog.exe"):
            assert (ROOT / relative).read_bytes() == (ROOT / "bakagit" / relative).read_bytes()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only preflight")
def test_macos_deployment_check_only_is_non_mutating(tmp_path):
    app_support = tmp_path / "Application Support" / "BakaBlog"
    result = subprocess.run(
        [
            "/bin/sh",
            str(ROOT / "deploy-macos.sh"),
            "--local",
            "--check-only",
            "--site-url",
            "https://blog.example.test",
            "--instance-dir",
            str(app_support / "instance"),
            "--python",
            sys.executable,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "macOS deployment preflight passed" in result.stdout
    assert not app_support.exists()
