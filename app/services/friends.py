"""Friend-link URL validation and SSRF-safe availability checks."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit


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
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
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
    current_url = validate_public_http_url(value, resolve=False)
    for redirect_count in range(6):
        parsed = urlsplit(current_url)
        hostname = parsed.hostname or ""
        approved_ips = _resolve_public_ips(hostname)
        try:
            status, location = _request_pinned_head(
                current_url,
                approved_ips,
                timeout=timeout,
            )
        except (TimeoutError, OSError, http.client.HTTPException, ssl.SSLError) as error:
            raise FriendCheckError(f"连接失败：{str(error)[:160]}") from error
        if status in {301, 302, 303, 307, 308} and location:
            if redirect_count >= 5:
                raise FriendCheckError("友链重定向次数过多。")
            current_url = validate_public_http_url(
                urljoin(current_url, location),
                resolve=False,
            )
            continue
        return FriendCheckResult(status < 400, status, f"HTTP {status}")
    raise FriendCheckError("友链重定向次数过多。")


def _request_pinned_head(
    url: str,
    approved_ips: list[str],
    *,
    timeout: float,
) -> tuple[int, str | None]:
    """Connect only to an address from the validated DNS snapshot."""

    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    authority = hostname
    if ":" in authority:
        authority = f"[{authority}]"
    if parsed.port:
        authority = f"{authority}:{parsed.port}"
    last_error: OSError | http.client.HTTPException | ssl.SSLError | None = None
    for address in approved_ips:
        connection: http.client.HTTPConnection
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(hostname, address, port, timeout=timeout)
        else:
            connection = _PinnedHTTPConnection(hostname, address, port, timeout=timeout)
        try:
            connection.request(
                "HEAD",
                target,
                headers={
                    "Host": authority,
                    "User-Agent": "CloudDiary-LinkCheck/1.0",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            return response.status, response.getheader("Location")
        except (OSError, http.client.HTTPException, ssl.SSLError) as error:
            last_error = error
        finally:
            connection.close()
    if last_error is not None:
        raise last_error
    raise FriendCheckError("域名没有可用地址。")


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        hostname: str,
        approved_ip: str,
        port: int,
        *,
        timeout: float,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self.approved_ip = approved_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self.approved_ip, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        approved_ip: str,
        port: int,
        *,
        timeout: float,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self.approved_ip = approved_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self.approved_ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


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
