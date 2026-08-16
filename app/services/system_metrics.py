"""Local host and runtime resource metrics for the protected admin panel."""

from __future__ import annotations

import os
import platform
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

_network_lock = threading.Lock()
_last_network_sample: tuple[float, int, int] | None = None


def _format_bytes(value: float) -> str:
    size = max(0.0, float(value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return "0 B"


def _format_rate(value: float) -> str:
    return f"{_format_bytes(value)}/s"


def _format_link_speed(bytes_per_second: float | None) -> str:
    if not bytes_per_second:
        return "链路容量不可用"
    bits_per_second = bytes_per_second * 8
    if bits_per_second >= 1_000_000_000:
        return f"{bits_per_second / 1_000_000_000:.1f} Gbps 链路"
    return f"{bits_per_second / 1_000_000:.0f} Mbps 链路"


def _safe_percent(value: float) -> float:
    return round(min(100.0, max(0.0, float(value))), 1)


def _host_os_label() -> str:
    system = platform.system() or "Unknown OS"
    if system == "Linux":
        try:
            pretty_name = platform.freedesktop_os_release().get("PRETTY_NAME")
        except OSError:
            pretty_name = None
        if pretty_name:
            return pretty_name
    if system == "Windows":
        edition = platform.win32_edition()
        release = platform.release()
        return " ".join(part for part in (system, release, edition) if part)
    return " ".join(part for part in (system, platform.release()) if part)


def host_snapshot(environment: str) -> dict[str, str]:
    """Return safe host facts suitable for the administrator-only pages."""

    booted_at = datetime.fromtimestamp(psutil.boot_time(), tz=UTC).astimezone()
    uptime_seconds = max(0, int(time.time() - psutil.boot_time()))
    days, remainder = divmod(uptime_seconds, 86_400)
    hours, minutes = divmod(remainder, 3_600)
    minutes //= 60
    uptime = f"{days}天 {hours}小时" if days else f"{hours}小时 {minutes}分钟"
    return {
        "os": _host_os_label(),
        "hostname": platform.node() or socket.gethostname() or "未识别",
        "python": platform.python_version(),
        "environment": environment,
        "booted_at": booted_at.strftime("%Y-%m-%d %H:%M"),
        "uptime": uptime,
    }


def _network_capacity() -> float | None:
    """Return the fastest active non-loopback interface capacity in bytes/s."""

    try:
        speeds = [
            stats.speed
            for name, stats in psutil.net_if_stats().items()
            if stats.isup
            and stats.speed > 0
            and name.casefold() != "lo"
            and not name.casefold().startswith("loopback")
        ]
    except (OSError, RuntimeError):
        return None
    return max(speeds) * 1_000_000 / 8 if speeds else None


def _network_rates() -> tuple[float, float, int, int]:
    global _last_network_sample

    counters = psutil.net_io_counters()
    if counters is None:
        return 0.0, 0.0, 0, 0
    now = time.monotonic()
    received = int(counters.bytes_recv)
    sent = int(counters.bytes_sent)
    with _network_lock:
        previous = _last_network_sample
        _last_network_sample = (now, received, sent)
    if previous is None:
        return 0.0, 0.0, received, sent
    elapsed = max(0.001, now - previous[0])
    receive_rate = max(0.0, (received - previous[1]) / elapsed)
    send_rate = max(0.0, (sent - previous[2]) / elapsed)
    return receive_rate, send_rate, received, sent


def collect_runtime_metrics(instance_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Collect a compact, real-time snapshot without exposing process secrets."""

    cpu_percent = _safe_percent(psutil.cpu_percent(interval=0.06))
    logical_cores = psutil.cpu_count(logical=True) or 1
    physical_cores = psutil.cpu_count(logical=False) or logical_cores

    memory = psutil.virtual_memory()
    memory_percent = _safe_percent(memory.percent)

    disk_target = Path(instance_path).resolve()
    disk = psutil.disk_usage(str(disk_target))
    disk_percent = _safe_percent(disk.percent)

    receive_rate, send_rate, received_total, sent_total = _network_rates()
    capacity = _network_capacity()
    network_percent = _safe_percent(
        ((receive_rate + send_rate) / capacity * 100) if capacity else 0
    )

    return {
        "sampled_at": datetime.now().astimezone().strftime("%H:%M:%S"),
        "resources": {
            "cpu": {
                "percent": cpu_percent,
                "current": f"{cpu_percent:.1f}%",
                "total": f"{physical_cores} 物理核心 · {logical_cores} 逻辑核心",
            },
            "memory": {
                "percent": memory_percent,
                "current": f"已用 {_format_bytes(memory.used)}",
                "total": f"总计 {_format_bytes(memory.total)}",
            },
            "disk": {
                "percent": disk_percent,
                "current": f"已用 {_format_bytes(disk.used)}",
                "total": f"总计 {_format_bytes(disk.total)} · 可用 {_format_bytes(disk.free)}",
            },
            "network": {
                "percent": network_percent,
                "current": f"↓ {_format_rate(receive_rate)} · ↑ {_format_rate(send_rate)}",
                "total": (
                    f"{_format_link_speed(capacity)} · 累计 ↓ {_format_bytes(received_total)}"
                    f" / ↑ {_format_bytes(sent_total)}"
                ),
            },
        },
    }
