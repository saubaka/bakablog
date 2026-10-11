from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.system_update import (
    UpdateError,
    queue_privileged_action,
    read_update_state,
    required_free_bytes,
    update_paths,
    validate_manifest,
)


def release_manifest(version: str = "9.0.0") -> dict[str, object]:
    return {
        "schema_version": 1,
        "channel": "stable",
        "version": version,
        "published_at": "2026-08-25T00:00:00+08:00",
        "title": "测试更新",
        "notes": "安全更新测试",
        "package": {
            "url": f"https://github.com/saubaka/bakablog/releases/download/v{version}/update.zip",
            "size": 4096,
            "sha256": "a" * 64,
        },
    }


def test_manifest_validation_rejects_non_official_sources():
    manifest = release_manifest()
    package = manifest["package"]
    assert isinstance(package, dict)
    package["url"] = "https://example.com/update.zip"
    with pytest.raises(UpdateError, match="官方 GitHub"):
        validate_manifest(manifest)


def test_manifest_validation_and_space_reserve(tmp_path: Path):
    release = validate_manifest(release_manifest())
    package = release["package"]
    assert isinstance(package, dict)
    assert release["version"] == "9.0.0"
    assert package["sha256"] == "a" * 64
    assert required_free_bytes(package, tmp_path) >= 256 * 1024 * 1024


def test_install_request_requires_verified_download(tmp_path: Path):
    with pytest.raises(UpdateError, match="尚未完成"):
        queue_privileged_action(tmp_path, "1.36.5", "install")


def test_install_request_is_narrowly_scoped(tmp_path: Path):
    paths = update_paths(tmp_path)
    state = read_update_state(tmp_path, "1.36.5")
    state.update(
        latest_version="1.36.5",
        available=True,
        downloaded=True,
        can_install=True,
        status="downloaded",
    )
    paths["state"].parent.mkdir(parents=True, exist_ok=True)
    paths["state"].write_text(json.dumps(state), encoding="utf-8")
    paths["download"].parent.mkdir(parents=True, exist_ok=True)
    paths["download"].write_bytes(b"verified-package")

    queued = queue_privileged_action(tmp_path, "1.36.5", "install")
    request = json.loads(paths["request"].read_text(encoding="utf-8"))
    assert queued["status"] == "queued"
    assert request["action"] == "install"
    assert request["version"] == "1.36.5"
    assert request["package"] == str(paths["download"])
    assert set(request) == {"schema_version", "action", "requested_at", "version", "package"}


def test_update_routes_render_realtime_state(logged_in_client):
    page = logged_in_client.get("/admin/system/about/")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "data-update-center" in body
    assert "安装更新" in body
    assert "回退上一版本" in body

    status = logged_in_client.get("/admin/system/update/status/")
    assert status.status_code == 200
    assert status.headers["Cache-Control"] == "no-store"
    assert status.get_json()["data"]["current_version"] == "1.49.0"
