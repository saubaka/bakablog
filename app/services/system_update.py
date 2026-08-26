"""Validated update discovery, download and privileged request hand-off.

The Flask process never replaces application files.  It verifies a repository
manifest and archive, then writes a narrowly-scoped request consumed by the
root-owned ``bakablog`` Linux manager.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.release import UPDATE_CHANNEL, UPDATE_MANIFEST_URL

MAX_MANIFEST_BYTES = 256 * 1024
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MIN_FREE_RESERVE_BYTES = 256 * 1024 * 1024
ALLOWED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
}
BUSY_STATES = {"checking", "downloading", "queued", "installing", "rolling_back"}
_thread_lock = threading.Lock()


class UpdateError(RuntimeError):
    """Raised when an update input or state transition is unsafe."""


def update_paths(instance_path: str | Path) -> dict[str, Path]:
    root = Path(instance_path).resolve() / "updates"
    return {
        "root": root,
        "state": root / "state.json",
        "request": root / "request.json",
        "download": root / "downloads" / "pending-update.zip",
        "lock": root / "job.lock",
        "rollback": root / "rollback.json",
    }


def initial_state(current_version: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "channel": UPDATE_CHANNEL,
        "current_version": current_version,
        "latest_version": current_version,
        "status": "idle",
        "progress": 0,
        "message": "尚未检查更新",
        "checked_at": None,
        "updated_at": _now(),
        "available": False,
        "downloaded": False,
        "can_install": False,
        "can_rollback": False,
        "package": None,
        "release": None,
        "disk": disk_snapshot(instance_path=None),
        "events": [],
    }


def read_update_state(instance_path: str | Path, current_version: str) -> dict[str, Any]:
    paths = update_paths(instance_path)
    state = initial_state(current_version)
    try:
        stored = json.loads(paths["state"].read_text(encoding="utf-8"))
        if isinstance(stored, dict) and stored.get("schema_version") == 1:
            state.update(stored)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    state["current_version"] = current_version
    state["can_rollback"] = paths["rollback"].is_file()
    state["disk"] = disk_snapshot(paths["root"])
    return state


def check_for_updates(instance_path: str | Path, current_version: str) -> dict[str, Any]:
    paths = update_paths(instance_path)
    with _job_guard(paths):
        state = read_update_state(instance_path, current_version)
        _transition(paths, state, "checking", 8, "正在连接官方仓库")
        try:
            manifest = _fetch_json(UPDATE_MANIFEST_URL)
            release = validate_manifest(manifest)
            available = _version_tuple(release["version"]) > _version_tuple(current_version)
            if available and not release.get("package"):
                raise UpdateError("远程新版本尚未发布可验证的软件包。")
            state.update(
                latest_version=release["version"],
                release=release,
                package=release.get("package"),
                available=available,
                checked_at=_now(),
                downloaded=False,
                can_install=False,
            )
            message = f"发现新版本 v{release['version']}" if available else "当前已经是最新版本"
            _transition(paths, state, "available" if available else "current", 100, message)
        except Exception as error:
            _transition(paths, state, "error", 0, _safe_error(error))
        return state


def start_download(instance_path: str | Path, current_version: str) -> dict[str, Any]:
    paths = update_paths(instance_path)
    with _thread_lock:
        state = read_update_state(instance_path, current_version)
        if state.get("status") in BUSY_STATES:
            raise UpdateError("更新任务正在进行，请稍候。")
        release = state.get("release")
        if not state.get("available") or not isinstance(release, dict):
            raise UpdateError("请先检查并确认存在新版本。")
        package = release.get("package")
        if not isinstance(package, dict):
            raise UpdateError("远程版本没有可下载的软件包。")
        required = required_free_bytes(package, paths["root"])
        free = shutil.disk_usage(paths["root"].parent).free
        if free < required:
            raise UpdateError(
                f"可用空间不足：需要至少 {_format_bytes(required)}，当前 {_format_bytes(free)}。"
            )
        _transition(paths, state, "downloading", 1, "正在准备下载")
        thread = threading.Thread(
            target=_download_worker,
            args=(str(instance_path), current_version),
            name="bakablog-update-download",
            daemon=True,
        )
        thread.start()
        return state


def queue_privileged_action(
    instance_path: str | Path, current_version: str, action: str
) -> dict[str, Any]:
    if action not in {"install", "rollback"}:
        raise UpdateError("不支持的更新操作。")
    paths = update_paths(instance_path)
    state = read_update_state(instance_path, current_version)
    if state.get("status") in BUSY_STATES:
        raise UpdateError("更新任务正在进行，请稍候。")
    if action == "install" and not state.get("can_install"):
        raise UpdateError("软件包尚未完成下载和校验。")
    if action == "rollback" and not paths["rollback"].is_file():
        raise UpdateError("没有可用于回退的完整备份。")
    request_payload = {
        "schema_version": 1,
        "action": action,
        "requested_at": _now(),
        "version": state.get("latest_version") if action == "install" else current_version,
        "package": str(paths["download"]) if action == "install" else None,
    }
    _atomic_json(paths["request"], request_payload, mode=0o640)
    _transition(
        paths,
        state,
        "queued",
        0,
        "安装请求已提交，等待系统管理器接管" if action == "install" else "回退请求已提交，等待系统管理器接管",
    )
    return state


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise UpdateError("远程版本清单格式无效。")
    if value.get("channel") != UPDATE_CHANNEL:
        raise UpdateError("远程版本通道不匹配。")
    version = str(value.get("version", ""))
    _version_tuple(version)
    published_at = str(value.get("published_at", ""))
    if not published_at or len(published_at) > 40:
        raise UpdateError("远程版本发布时间无效。")
    result: dict[str, Any] = {
        "version": version,
        "published_at": published_at,
        "title": str(value.get("title", f"v{version}"))[:120],
        "notes": str(value.get("notes", ""))[:4000],
    }
    package = value.get("package")
    if package is not None:
        if not isinstance(package, dict):
            raise UpdateError("远程软件包信息无效。")
        url = _validate_download_url(str(package.get("url", "")))
        try:
            size = int(package.get("size", 0))
        except (TypeError, ValueError) as error:
            raise UpdateError("远程软件包大小无效。") from error
        checksum = str(package.get("sha256", "")).lower()
        if size <= 0 or size > MAX_PACKAGE_BYTES:
            raise UpdateError("远程软件包大小超出安全限制。")
        if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
            raise UpdateError("远程软件包缺少有效的 SHA-256。")
        result["package"] = {"url": url, "size": size, "sha256": checksum}
    return result


def required_free_bytes(package: dict[str, Any], storage_root: Path) -> int:
    package_size = int(package["size"])
    project_hint = 0
    try:
        project_hint = sum(
            item.stat().st_size for item in storage_root.parent.rglob("*") if item.is_file()
        )
    except OSError:
        project_hint = package_size * 2
    # Archive + staged tree + old-code snapshot + data backup + fixed reserve.
    return max(package_size * 4 + project_hint * 2, MIN_FREE_RESERVE_BYTES)


def disk_snapshot(instance_path: str | Path | None) -> dict[str, Any]:
    target = Path(instance_path or Path.cwd()).resolve()
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    return {
        "free": usage.free,
        "total": usage.total,
        "free_label": _format_bytes(usage.free),
        "total_label": _format_bytes(usage.total),
    }


def _download_worker(instance_path: str, current_version: str) -> None:
    paths = update_paths(instance_path)
    try:
        with _job_guard(paths):
            state = read_update_state(instance_path, current_version)
            package = state.get("package")
            if not isinstance(package, dict):
                raise UpdateError("下载任务缺少软件包信息。")
            paths["download"].parent.mkdir(parents=True, exist_ok=True)
            temporary = paths["download"].with_suffix(".part")
            temporary.unlink(missing_ok=True)
            request = Request(package["url"], headers={"User-Agent": "bakablog-updater/1"})
            digest = hashlib.sha256()
            received = 0
            expected = int(package["size"])
            with urlopen(request, timeout=30) as response, temporary.open("wb") as target:  # noqa: S310
                final_url = response.geturl()
                _validate_download_url(final_url)
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > MAX_PACKAGE_BYTES or received > expected:
                        raise UpdateError("下载内容超出版本清单声明的大小。")
                    target.write(chunk)
                    digest.update(chunk)
                    state["updated_at"] = _now()
                    state["progress"] = max(1, min(99, int(received / expected * 100)))
                    state["message"] = f"正在下载 {_format_bytes(received)} / {_format_bytes(expected)}"
                    _write_state(paths, state)
                target.flush()
                os.fsync(target.fileno())
            if received != expected:
                raise UpdateError("下载大小与版本清单不一致。")
            if digest.hexdigest() != package["sha256"]:
                raise UpdateError("软件包 SHA-256 校验失败，已拒绝安装。")
            os.replace(temporary, paths["download"])
            state.update(downloaded=True, can_install=True)
            _transition(paths, state, "downloaded", 100, "下载与完整性校验完成")
    except Exception as error:
        paths["download"].with_suffix(".part").unlink(missing_ok=True)
        state = read_update_state(instance_path, current_version)
        state.update(downloaded=False, can_install=False)
        _transition(paths, state, "error", 0, _safe_error(error))


def _fetch_json(url: str) -> Any:
    _validate_download_url(url)
    request = Request(url, headers={"User-Agent": "bakablog-updater/1", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:  # noqa: S310
            _validate_download_url(response.geturl())
            raw = response.read(MAX_MANIFEST_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise UpdateError("无法连接官方更新仓库，请稍后重试。") from error
    if len(raw) > MAX_MANIFEST_BYTES:
        raise UpdateError("远程版本清单超出安全限制。")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError("远程版本清单无法解析。") from error


def _validate_download_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise UpdateError("更新地址必须使用受信任的 HTTPS 地址。")
    if (parsed.hostname or "").lower() not in ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateError("更新地址不属于官方 GitHub 仓库。")
    return url


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or any(not item.isdigit() for item in parts):
        raise UpdateError("版本号必须使用 x.y.z 格式。")
    values = tuple(int(item) for item in parts)
    if any(item > 9999 for item in values):
        raise UpdateError("版本号超出安全限制。")
    return values  # type: ignore[return-value]


class _job_guard:
    def __init__(self, paths: dict[str, Path]) -> None:
        self.paths = paths
        self.fd: int | None = None

    def __enter__(self) -> None:
        self.paths["root"].mkdir(parents=True, exist_ok=True)
        if self.paths["lock"].exists():
            try:
                age = datetime.now(UTC).timestamp() - self.paths["lock"].stat().st_mtime
                if age > 30 * 60:
                    self.paths["lock"].unlink()
            except OSError:
                pass
        try:
            self.fd = os.open(self.paths["lock"], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(self.fd, f"{os.getpid()}\n".encode())
        except FileExistsError as error:
            raise UpdateError("另一个更新任务正在运行。") from error

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        self.paths["lock"].unlink(missing_ok=True)


def _transition(
    paths: dict[str, Path], state: dict[str, Any], status: str, progress: int, message: str
) -> None:
    state.update(status=status, progress=progress, message=message, updated_at=_now())
    events = list(state.get("events") or [])[-11:]
    events.append({"at": state["updated_at"], "status": status, "message": message})
    state["events"] = events
    _write_state(paths, state)


def _write_state(paths: dict[str, Path], state: dict[str, Any]) -> None:
    _atomic_json(paths["state"], state, mode=0o640)


def _atomic_json(path: Path, payload: dict[str, Any], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _safe_error(error: Exception) -> str:
    if isinstance(error, UpdateError):
        return str(error)
    return "更新任务遇到异常，未对当前站点做任何修改。"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _format_bytes(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{int(amount)} B" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return "0 B"
