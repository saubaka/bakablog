"""Friend-link URL validation and SSRF-safe availability checks."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class FriendCheckError(ValueError):
    """A friend URL is invalid, unsafe or unreachable."""


@dataclass(frozen=True)
class FriendCheckResult:
    ok: bool
    status_code: int | None
    message: str


def validate_public_http_url(value: str, resolve: bool = True) -> str:
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise FriendCheckError("友链必须使用完整的公网 http 或 https 地址。")
    try:
        port = parsed.port
    except ValueError as error:
        raise FriendCheckError("友链端口格式无效。") from error
    if port and port not in {80, 443}:
        raise FriendCheckError("友链检查仅允许标准的80或443端口。")
    if resolve:
        _resolve_public_ips(parsed.hostname)
    return url


def check_friend_url(value: str, timeout: float = 5.0) -> FriendCheckResult:
    url = validate_public_http_url(value)
    request = Request(url, method="HEAD", headers={"User-Agent": "CloudDiary-LinkCheck/1.0"})
    try:
        with build_opener(_SafeRedirectHandler()).open(request, timeout=timeout) as response:
            status = response.status
            return FriendCheckResult(status < 400, status, f"HTTP {status}")
    except HTTPError as error:
        return FriendCheckResult(False, error.code, f"HTTP {error.code}")
    except (URLError, TimeoutError, OSError) as error:
        raise FriendCheckError(f"连接失败：{str(error)[:160]}") from error


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Revalidate redirects so a public URL cannot bounce to an internal host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_public_http_url(newurl, resolve=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _resolve_public_ips(hostname: str) -> list[str]:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as error:
        raise FriendCheckError("域名无法解析。") from error
    if not addresses:
        raise FriendCheckError("域名没有可用地址。")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise FriendCheckError("友链地址不能指向本机、内网或保留网络。")
    return sorted(addresses)
