"""Security primitives: password hashing, tokens, client address, response headers, same-origin check."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import re
import secrets

from flask import Flask, Request, Response, request

from app.config import Config
from app.config import cfg as current_cfg

# ---- passwords: scrypt, stored as scrypt$N$r$p$salt$hash (base64) ------------------------------------------------------------
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 128 * 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, n: int = 2**15) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${n}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def needs_rehash(stored: str, n: int) -> bool:
    try:
        return int(stored.split("$")[1]) < n
    except (IndexError, ValueError):
        return True


# A fixed hash to verify against when the user name does not exist, so "unknown user" costs the same time as "wrong password".
_DUMMY_HASH: dict[int, str] = {}


def dummy_verify(password: str, n: int) -> None:
    if n not in _DUMMY_HASH:
        _DUMMY_HASH[n] = hash_password("not-a-real-password", n)
    verify_password(password, _DUMMY_HASH[n])


# ---- tokens ------------------------------------------------------------------------------------------------------------------
def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---- client address ----------------------------------------------------------------------------------------------------------
def ip_prefix(addr: str | None) -> str:
    """What the site keeps of an address: IPv4 /24, IPv6 /48. Never the full address."""
    if not addr:
        return ""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return ""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    bits = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{bits}", strict=False))


def client_prefix(req: Request | None = None) -> str:
    req = req or request
    return ip_prefix(req.remote_addr)


_UA_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("CriOS/", "Chrome"),
                ("Safari/", "Safari"))
_UA_SYSTEMS = (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Mac OS X", "macOS"), ("Windows", "Windows"),
               ("CrOS", "ChromeOS"), ("Linux", "Linux"))


def device_label(user_agent: str | None) -> str:
    ua = user_agent or ""
    browser = next((name for needle, name in _UA_BROWSERS if needle in ua), "浏览器")
    system = next((name for needle, name in _UA_SYSTEMS if needle in ua), "")
    return f"{browser} · {system}" if system else browser


def device_class(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "tablet"
    if "mobile" in ua or "iphone" in ua or "android" in ua:
        return "phone"
    if ua:
        return "desktop"
    return "other"


_BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|fetch|monitor|curl|wget|python-requests|httpx|headless|lighthouse", re.I)


def looks_like_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(_BOT_RE.search(user_agent))


# ---- same-origin check for state-changing requests ---------------------------------------------------------------------------
def same_origin(req: Request) -> bool:
    """Browsers send Origin (and Sec-Fetch-Site) on cross-site and on most POST requests. If either says "elsewhere", refuse."""
    fetch_site = req.headers.get("Sec-Fetch-Site")
    if fetch_site and fetch_site not in ("same-origin", "none"):
        return False
    origin = req.headers.get("Origin")
    if origin and origin != "null":
        host = req.host
        origin_host = origin.split("://", 1)[-1].split("/", 1)[0]
        return origin_host == host
    return origin is None


# ---- response headers --------------------------------------------------------------------------------------------------------
CSP_PAGE = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)
# the admin may show its own preview page in a frame (spa.PREVIEW_PATH); nothing else
CSP_ADMIN = CSP_PAGE.replace("img-src 'self' data:", "img-src 'self' data: blob:") + "; frame-src 'self'"
CSP_API = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def register(app: Flask, cfg: Config) -> None:
    @app.after_request
    def _headers(response: Response):
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        path = request.path
        if "Content-Security-Policy" not in h:
            if path.startswith(("/api/", "/sitemap", "/robots")):
                h["Content-Security-Policy"] = CSP_API
            elif path.startswith("/admin"):
                h["Content-Security-Policy"] = CSP_ADMIN
            elif not path.startswith("/media/"):
                h["Content-Security-Policy"] = CSP_PAGE
        if current_cfg().cookie_secure:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if path.startswith("/api/admin"):
            h["Cache-Control"] = "no-store"
            h["Vary"] = "Cookie"
        return response
