from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bakablog_linux_binaries_are_self_contained_elf_targets():
    targets = {
        "linux-x64": 0x3E,
        "linux-arm64": 0xB7,
    }
    for runtime, expected_machine in targets.items():
        for family, name in (("bakablog", "bakablog"), ("bakagate", "bakagate")):
            binary = ROOT / "dist" / family / runtime / name
            header = binary.read_bytes()[:64]
            assert header[:4] == b"\x7fELF"
            assert header[4] == 2  # ELF64
            assert struct.unpack_from("<H", header, 18)[0] == expected_machine
            assert binary.stat().st_size > 10_000_000


def test_linux_edge_template_uses_dynamic_loopback_without_cloudflare_ranges():
    nginx = (ROOT / "deploy" / "nginx" / "cloud-diary.conf.example").read_text(encoding="utf-8")
    serve = (ROOT / "scripts" / "serve.sh").read_text(encoding="utf-8")
    manager = (ROOT / "tools" / "bakagate-manager" / "Program.cs").read_text(encoding="utf-8")
    updater = (ROOT / "tools" / "bakagate-manager" / "SystemUpdateManager.cs").read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1:8080" in nginx
    assert "bakagate-cloudflare-ips" not in nginx
    assert "www.cloudflare.com/ips-" not in manager
    assert "RefreshCloudflareRanges" not in manager
    assert "FindAvailablePort" in manager
    assert "--prepare-port" in manager
    assert "local_port = config.LocalPort" in manager
    assert "Restart=always" in manager
    assert "ssl_reject_handshake on" in nginx
    assert "ssl_verify_client" not in nginx
    assert "OriginPullCaFingerprint" not in manager
    assert "return 444" in nginx
    assert '127.0.0.1:${PORT}' in serve
    assert "--process-update-request" in manager
    assert "bakablog-update.path" in manager
    assert "SHA-256" in updater
    assert "site-backup" in updater
    assert "site-restore" in updater
    assert "WaitForHealth" in updater


def test_linux_bootstrap_targets_the_configured_repository():
    script = (ROOT / "deploy-linux.sh").read_text(encoding="utf-8")
    assert "https://github.com/saubaka/bakablog.git" in script
    assert 'PROJECT_DIRECTORY="/opt/bakablog/current"' in script
    assert 'merge --ff-only "origin/$BRANCH"' in script
    assert "--manager-only" in script
    assert "linux-x64" in script
    assert "linux-arm64" in script
    assert "/usr/local/bin/bakablog" in script
    assert "dist/bakablog/$RUNTIME/bakablog" in script
    assert "reset --hard" not in script


def test_bakagit_contains_identical_debian_release_assets():
    paths = (
        Path("app/cli.py"),
        Path("deploy-linux.sh"),
        Path("tools/bakagate-manager/Program.cs"),
        Path("tools/bakagate-manager/SystemUpdateManager.cs"),
        Path("tools/bakagate-manager/bakagate.csproj"),
        Path("updates/stable.json"),
        Path("updates/README.md"),
        Path("scripts/build_update_package.py"),
        Path("scripts/build-bakagate.ps1"),
        Path("scripts/serve.sh"),
        Path("deploy/nginx/cloud-diary.conf.example"),
        Path("dist/bakagate/linux-x64/bakagate"),
        Path("dist/bakagate/linux-arm64/bakagate"),
        Path("dist/bakablog/linux-x64/bakablog"),
        Path("dist/bakablog/linux-arm64/bakablog"),
    )
    for relative in paths:
        assert (ROOT / relative).read_bytes() == (ROOT / "bakagit" / relative).read_bytes()
