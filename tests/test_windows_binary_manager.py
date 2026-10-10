from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_bakablog_windows_binary_and_menu_contract():
    executable = Path("bakablog.exe")
    source = Path("tools/bakablog-manager/Program.cs").read_text(encoding="utf-8")

    assert executable.is_file()
    assert executable.stat().st_size > 10_000_000
    assert executable.read_bytes()[:2] == b"MZ"
    assert "\ufffd" not in source
    for expected in (
        "启动 {Spec.Name}",
        "停止 {Spec.Name}",
        "重新启动 {Spec.Name}",
        "获取本机临时恢复入口",
        "重置管理器选项",
        "切换开机自启",
    ):
        assert expected in source

    # Keep validating the Windows release asset on every platform, but a PE
    # executable can only be launched natively during the Windows test run.
    if sys.platform != "win32":
        return

    result = subprocess.run(
        [str(executable.resolve()), "--status-json"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    payload = json.loads(result.stdout)
    assert payload["service"] == "bakablog"
    assert payload["port"] == 5000
    assert payload["windows"].startswith("Windows ")
