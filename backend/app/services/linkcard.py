"""Link cards for moments: fetch a page's title / description / icon on the server, safely.

The fetch is the one place where the server connects to an address typed by a (trusted but fallible) user, so it is hardened
against SSRF: only http(s), no credentials in the URL, the host name is resolved ONCE and every resulting address must be a public
one (no loopback, private, link-local, metadata, multicast, reserved ranges), the connection is then pinned to that address (no DNS
rebinding between check and use), every redirect hop is checked the same way, and size / time / redirect count are capped.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.errors import ApiError

USER_AGENT = "BakaBlog-LinkPreview/1.0 (+personal blog; fetches title and description once)"
MAX_BYTES = 512 * 1024
MAX_ICON_BYTES = 128 * 1024
MAX_REDIRECTS = 3
TOTAL_TIMEOUT = 8.0
_REDIRECT = {301, 302, 303, 307, 308}

Resolver = Callable[[str, int], list[str]]
Connector = Callable[[str, str, int, bool, float], http.client.HTTPConnection]


class FetchError(ApiError):
    def __init__(self, message: str, code: str = "fetch_failed", status: int = 422):
        super().__init__(status, code, message)


@dataclass
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes
    headers: dict = field(default_factory=dict)


def default_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("无法解析这个网址的域名。", "dns_failed") from exc
    return list(dict.fromkeys(info[4][0] for info in infos))


class _Pinned(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedTLS(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)  # certificate is checked against the NAME, not the address


def default_connector(host: str, ip: str, port: int, tls: bool, timeout: float) -> http.client.HTTPConnection:
    return _PinnedTLS(host, ip, port, timeout) if tls else _Pinned(host, ip, port, timeout)


def is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        elif addr.sixtofour is not None:
            addr = addr.sixtofour
    return addr.is_global and not addr.is_multicast


def check_url(url: str, resolver: Resolver) -> tuple[str, str, int, bool, str]:
    """-> (host, ip to connect to, port, tls, path+query). Raises FetchError for anything not allowed."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise FetchError("只支持 http / https 链接。", "bad_scheme")
    if parts.username or parts.password:
        raise FetchError("链接里不能带用户名和密码。", "bad_url")
    host = parts.hostname
    if not host:
        raise FetchError("链接不完整。", "bad_url")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("端口不对。", "bad_url") from exc
    ips = resolver(host, port)
    if not ips or not all(is_public(ip) for ip in ips):
        raise FetchError("不能访问内网或本机地址。", "forbidden_address")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return host, ips[0], port, parts.scheme == "https", path


def fetch(url: str, *, max_bytes: int = MAX_BYTES, accept: str = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
          resolver: Resolver | None = None, connector: Connector | None = None) -> Fetched:
    resolver = resolver or default_resolver
    connector = connector or default_connector
    deadline = time.monotonic() + TOTAL_TIMEOUT
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        host, ip, port, tls, path = check_url(current, resolver)
        remaining = max(0.5, deadline - time.monotonic())
        conn = connector(host, ip, port, tls, min(remaining, 5.0))
        try:
            conn.request("GET", path, headers={"Host": host if port in (80, 443) else f"{host}:{port}", "User-Agent": USER_AGENT,
                                               "Accept": accept, "Accept-Encoding": "identity", "Connection": "close"})
            response = conn.getresponse()
            status = response.status
            if status in _REDIRECT:
                location = response.getheader("Location")
                if not location:
                    raise FetchError("对方的重定向不完整。", "bad_redirect")
                current = urljoin(current, location)
                continue
            if status >= 400:
                raise FetchError(f"对方返回了 {status}。", "http_error")
            body = response.read(max_bytes + 1)[:max_bytes]
            headers = {k.lower(): v for k, v in response.getheaders()}
            return Fetched(current, status, (headers.get("content-type") or "").split(";")[0].strip().lower(), body, headers)
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise FetchError("连接失败或超时。", "connect_failed") from exc
        finally:
            conn.close()
        if time.monotonic() > deadline:
            raise FetchError("对方响应太慢。", "timeout")
    raise FetchError("重定向次数太多。", "too_many_redirects")


# ---- parsing ---------------------------------------------------------------------------------------------------------------------
class _HeadParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.icons: list[tuple[str, str, str]] = []  # (rel, href, sizes)
        self._in_title = False
        self._title_seen = False
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title" and not self._title_seen:
            self._in_title = True
            self._title_seen = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a:
                self.meta.setdefault(key, a["content"].strip())
        elif tag == "link" and a.get("href"):
            rel = a.get("rel", "").lower()
            if "icon" in rel:
                self.icons.append((rel, a["href"], a.get("sizes", "")))
        elif tag == "body":
            self.done = True

    def handle_endtag(self, tag):
        if self.done:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self._in_title and not self.done and len(self.title) < 300:
            self.title += data


def decode(body: bytes, content_type_header: str = "") -> str:
    charset = "utf-8"
    if "charset=" in content_type_header.lower():
        charset = content_type_header.lower().split("charset=", 1)[1].split(";")[0].strip().strip("\"'")
    else:
        head = body[:2048].lower()
        marker = head.find(b"charset=")
        if marker >= 0:
            raw = head[marker + 8: marker + 60].lstrip(b"\"' ")
            for sep in (b'"', b"'", b">", b";", b" ", b"/"):
                raw = raw.split(sep)[0]
            charset = raw.decode("ascii", "ignore") or "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


@dataclass
class Preview:
    url: str
    title: str
    description: str
    domain: str
    site_name: str
    icon_url: str | None


def parse_preview(page: Fetched) -> Preview:
    domain = (urlsplit(page.url).hostname or "").lower().removeprefix("www.")
    if page.content_type not in ("text/html", "application/xhtml+xml"):
        return Preview(page.url, domain, "", domain, "", None)
    parser = _HeadParser()
    text = decode(page.body, page.headers.get("content-type", ""))
    for chunk in (text[i: i + 4096] for i in range(0, len(text), 4096)):
        parser.feed(chunk)
        if parser.done:
            break
    title = (parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title or domain).strip()
    description = (parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description") or "").strip()
    icon = None
    ranked = sorted(parser.icons, key=lambda i: ("apple-touch" not in i[0], ".svg" in i[1].lower() or ".ico" in i[1].lower()))
    if ranked:
        icon = urljoin(page.url, ranked[0][1])
    return Preview(page.url, " ".join(title.split())[:200], " ".join(description.split())[:300], domain,
                   parser.meta.get("og:site_name", "")[:80], icon)


def preview(url: str, *, resolver: Resolver | None = None, connector: Connector | None = None) -> Preview:
    return parse_preview(fetch(url, resolver=resolver, connector=connector))


def fetch_icon(icon_url: str, *, resolver: Resolver | None = None, connector: Connector | None = None) -> bytes | None:
    """The icon file bytes, or None when it cannot be fetched or is not a picture."""
    try:
        got = fetch(icon_url, max_bytes=MAX_ICON_BYTES, accept="image/png,image/*;q=0.8", resolver=resolver, connector=connector)
    except ApiError:
        return None
    return got.body if got.body and got.content_type.startswith("image/") else None
