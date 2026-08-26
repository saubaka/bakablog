"""Database-backed host and transport access policy."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.services.cache import site_context_cache
from app.services.content import get_settings, set_setting

ACCESS_ALLOWED_HOSTS_KEY = "access_allowed_hosts"
ACCESS_REQUIRE_HTTPS_KEY = "access_require_https"
ACCESS_BOUND_URLS_KEY = "access_bound_urls"
ACCESS_HOTLINK_KEY = "access_hotlink_protection"
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    allowed_hosts: tuple[str, ...] = ()
    require_https: bool = False
    bound_urls: tuple[str, ...] = ()
    hotlink_protection: bool = False


def normalize_host(value: str) -> str:
    """Normalize an IP address or DNS hostname without a port."""

    candidate = value.strip().lower().rstrip(".")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if not candidate or "://" in candidate or any(char in candidate for char in "/?#@"):
        raise ValueError("主机名不能包含协议、端口、路径或账号信息。")
    try:
        return ipaddress.ip_address(candidate).compressed.lower()
    except ValueError:
        pass
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("主机名包含无法识别的字符。") from error
    if len(candidate) > 253 or any(
        not _HOST_LABEL.fullmatch(label) for label in candidate.split(".")
    ):
        raise ValueError(f"无效的主机名：{value.strip() or '空值'}")
    return candidate


def parse_allowed_hosts(value: str) -> tuple[str, ...]:
    """Parse comma/newline separated exact hosts and ``*.example.com`` rules."""

    rules: list[str] = []
    for raw in re.split(r"[,\s]+", value.strip()):
        if not raw:
            continue
        wildcard = raw.startswith("*.")
        host = normalize_host(raw[2:] if wildcard else raw)
        if wildcard:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                host = f"*.{host}"
            else:
                raise ValueError("IP 地址不能使用通配符。")
        if host not in rules:
            rules.append(host)
    return tuple(rules)


def serialize_allowed_hosts(value: str) -> str:
    return "\n".join(parse_allowed_hosts(value))


def request_hostname(host_header: str) -> str:
    try:
        hostname = urlsplit(f"//{host_header}").hostname
    except ValueError as error:
        raise ValueError("请求 Host 无效。") from error
    if not hostname:
        raise ValueError("请求 Host 为空。")
    return normalize_host(hostname)


def host_is_allowed(hostname: str, rules: tuple[str, ...]) -> bool:
    if not rules:
        return True
    normalized = normalize_host(hostname)
    for rule in rules:
        if rule.startswith("*."):
            suffix = rule[1:]
            if normalized.endswith(suffix) and normalized != rule[2:]:
                return True
        elif normalized == rule:
            return True
    return False


def parse_bound_urls(value: str) -> tuple[str, ...]:
    """Normalize one HTTP(S) site origin per line."""

    urls: list[str] = []
    for raw in re.split(r"[,\s]+", value.strip()):
        if not raw:
            continue
        candidate = raw if "://" in raw else f"http://{raw}"
        parsed = urlsplit(candidate)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(f"无效的网站网址：{raw}")
        host = normalize_host(parsed.hostname)
        try:
            port_number = parsed.port
        except ValueError as error:
            raise ValueError(f"无效的网站网址端口：{raw}") from error
        port = f":{port_number}" if port_number else ""
        display_host = f"[{host}]" if ":" in host else host
        normalized = f"{parsed.scheme}://{display_host}{port}"
        if normalized not in urls:
            urls.append(normalized)
    return tuple(urls)


def bound_url_hosts(urls: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(normalize_host(urlsplit(url).hostname or "") for url in urls))


def origin_is_allowed(scheme: str, host_header: str, urls: tuple[str, ...]) -> bool:
    """Require an exact scheme, host and explicit port match when origins are bound."""

    if not urls:
        return True
    try:
        origin = parse_bound_urls(f"{scheme}://{host_header}")
    except ValueError:
        return False
    return bool(origin and origin[0] in urls)


def get_access_policy() -> AccessPolicy:
    """Return the cached policy, failing closed to the configured site origin."""

    def load() -> AccessPolicy:
        try:
            values = get_settings(
                {
                    ACCESS_ALLOWED_HOSTS_KEY: "",
                    ACCESS_REQUIRE_HTTPS_KEY: "0",
                    ACCESS_BOUND_URLS_KEY: "",
                    ACCESS_HOTLINK_KEY: "0",
                }
            )
            rules = parse_allowed_hosts(values[ACCESS_ALLOWED_HOSTS_KEY])
            require_https = values[ACCESS_REQUIRE_HTTPS_KEY].strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            bound_urls = parse_bound_urls(values[ACCESS_BOUND_URLS_KEY])
            hotlink = values[ACCESS_HOTLINK_KEY].strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            return AccessPolicy(rules, require_https, bound_urls, hotlink)
        except (SQLAlchemyError, ValueError):
            db.session.rollback()
            current_app.logger.exception(
                "access policy load failed; restricting access to configured site origin"
            )
            return _configured_origin_policy()

    return site_context_cache.get_or_set(
        f"access-policy:{current_app.instance_path}",
        int(current_app.config["ACCESS_POLICY_CACHE_SECONDS"]),
        load,
    )


def _configured_origin_policy() -> AccessPolicy:
    """Build a restrictive fallback without consulting the unavailable database."""

    try:
        urls = parse_bound_urls(str(current_app.config["SITE_URL"]))
        if len(urls) != 1:
            raise ValueError("SITE_URL must contain exactly one origin")
        hosts = bound_url_hosts(urls)
    except (KeyError, TypeError, ValueError):
        current_app.logger.critical(
            "configured site origin is invalid; denying all ordinary request hosts"
        )
        return AccessPolicy(("invalid.invalid",), True, (), True)
    require_https = current_app.config.get("ENV_NAME") == "production" or urls[0].startswith(
        "https://"
    )
    return AccessPolicy(hosts, require_https, urls, True)


def save_access_policy(allowed_hosts: str, require_https: bool) -> AccessPolicy:
    normalized = serialize_allowed_hosts(allowed_hosts)
    set_setting(ACCESS_ALLOWED_HOSTS_KEY, normalized)
    set_setting(ACCESS_REQUIRE_HTTPS_KEY, "1" if require_https else "0")
    site_context_cache.clear()
    current = get_access_policy()
    return AccessPolicy(
        parse_allowed_hosts(normalized),
        require_https,
        current.bound_urls,
        current.hotlink_protection,
    )


def save_bound_urls(value: str) -> AccessPolicy:
    urls = parse_bound_urls(value)
    hosts = bound_url_hosts(urls)
    set_setting(ACCESS_BOUND_URLS_KEY, "\n".join(urls))
    set_setting(ACCESS_ALLOWED_HOSTS_KEY, "\n".join(hosts))
    site_context_cache.clear()
    current = get_access_policy()
    return AccessPolicy(hosts, current.require_https, urls, current.hotlink_protection)


def save_security_policy(require_https: bool, hotlink_protection: bool) -> AccessPolicy:
    set_setting(ACCESS_REQUIRE_HTTPS_KEY, "1" if require_https else "0")
    set_setting(ACCESS_HOTLINK_KEY, "1" if hotlink_protection else "0")
    site_context_cache.clear()
    current = get_access_policy()
    return AccessPolicy(
        current.allowed_hosts,
        require_https,
        current.bound_urls,
        hotlink_protection,
    )


def hotlink_is_allowed(referer: str, policy: AccessPolicy) -> bool:
    if not policy.hotlink_protection or not referer:
        return True
    try:
        hostname = urlsplit(referer).hostname
        return bool(hostname and host_is_allowed(hostname, policy.allowed_hosts))
    except ValueError:
        return False
