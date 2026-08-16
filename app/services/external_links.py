"""Normalize, classify and route third-party links through a local notice page."""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import bleach
from flask import current_app, has_request_context, request, url_for
from markupsafe import Markup

from app.extensions import db
from app.models import ExternalLinkRule

LINK_CLASSIFICATIONS = {"safe", "dangerous"}
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
PLAIN_URL_PATTERN = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'，。！？；：、）】）》”’]+", re.IGNORECASE
)
TRAILING_URL_PUNCTUATION = re.compile(r"[.,;:!?，。！？；：、)\]}】）》”’]+$")
SKIP_LINKIFY_TAGS = {"a", "pre", "code", "script", "style", "textarea"}


class ExternalLinkError(ValueError):
    """Raised when an external destination or managed hostname is invalid."""


def normalize_hostname(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ExternalLinkError("请填写需要管理的域名或网址。")
    if CONTROL_PATTERN.search(candidate):
        raise ExternalLinkError("域名中不能包含控制字符。")
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    if parsed.username or parsed.password:
        raise ExternalLinkError("不能保存包含账号或密码的网址。")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        raise ExternalLinkError("没有识别到有效域名。")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ExternalLinkError("域名格式无法识别。") from error
    if len(hostname) > 253 or any(len(label) > 63 for label in hostname.split(".")):
        raise ExternalLinkError("域名长度超出允许范围。")
    return hostname


def normalize_destination(value: str) -> str:
    candidate = str(value or "").strip()
    if candidate.lower().startswith("www."):
        candidate = f"https://{candidate}"
    if not candidate or len(candidate) > 2048 or CONTROL_PATTERN.search(candidate):
        raise ExternalLinkError("跳转网址无效或过长。")
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ExternalLinkError("只允许跳转到完整的HTTP或HTTPS网址。")
    if parsed.username or parsed.password:
        raise ExternalLinkError("不允许跳转到包含账号或密码的网址。")
    try:
        hostname = normalize_hostname(parsed.hostname)
        port = parsed.port
    except ValueError as error:
        raise ExternalLinkError("网址端口无效。") from error
    host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, parsed.fragment)
    )


def is_external_destination(destination: str) -> bool:
    parsed = urlsplit(destination)
    candidate_host = (parsed.hostname or "").lower()
    request_host = request.host.split(":", 1)[0].lower() if has_request_context() else ""
    configured_host = (urlsplit(str(current_app.config.get("SITE_URL", ""))).hostname or "").lower()
    return bool(candidate_host and candidate_host not in {request_host, configured_host})


def notice_url(destination: str) -> str:
    candidate = str(destination or "").strip()
    if candidate.startswith(("/", "#", "?")) or candidate.lower().startswith(("mailto:", "tel:")):
        return candidate
    normalized = normalize_destination(candidate)
    if not is_external_destination(normalized):
        return normalized
    return url_for("public.external_link_notice", url=normalized)


def classify_destination(destination: str) -> SimpleNamespace:
    normalized = normalize_destination(destination)
    hostname = normalize_hostname(urlsplit(normalized).hostname or "")
    rule = db.session.scalar(
        db.select(ExternalLinkRule).where(ExternalLinkRule.hostname == hostname)
    )
    return SimpleNamespace(
        destination=normalized,
        hostname=hostname,
        classification=rule.classification if rule else "unknown",
        display_name=(rule.display_name or hostname) if rule else hostname,
        note=(rule.note or "") if rule else "",
        rule=rule,
    )


def _link_callback(attrs, new=False):  # type: ignore[no-untyped-def]
    href_key = (None, "href")
    href = attrs.get(href_key, "")
    try:
        normalized = normalize_destination(href)
    except ExternalLinkError:
        return attrs
    if not is_external_destination(normalized):
        attrs[href_key] = normalized
        return attrs
    attrs[href_key] = notice_url(normalized)
    attrs[(None, "class")] = "external-text-link"
    attrs[(None, "data-external-link")] = ""
    attrs[(None, "data-external-destination")] = normalized
    attrs[(None, "rel")] = "nofollow noopener noreferrer"
    attrs.pop((None, "target"), None)
    return attrs


class _PlainUrlLinkifier(HTMLParser):
    """Wrap URL-shaped text without altering existing HTML tags or anchors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.skipped: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        self.parts.append(self.get_starttag_text())
        if tag.lower() in SKIP_LINKIFY_TAGS:
            self.skipped.append(tag.lower())

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")
        lowered = tag.lower()
        if self.skipped and self.skipped[-1] == lowered:
            self.skipped.pop()

    def handle_data(self, data: str) -> None:
        if self.skipped:
            self.parts.append(data)
            return
        cursor = 0
        for match in PLAIN_URL_PATTERN.finditer(data):
            raw = match.group(0)
            trailing_match = TRAILING_URL_PUNCTUATION.search(raw)
            trailing = trailing_match.group(0) if trailing_match else ""
            visible = raw[: -len(trailing)] if trailing else raw
            self.parts.append(data[cursor : match.start()])
            self.parts.append(f'<a href="{escape(visible, quote=True)}">{escape(visible)}</a>')
            self.parts.append(trailing)
            cursor = match.end()
        self.parts.append(data[cursor:])

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def unknown_decl(self, data: str) -> None:
        self.parts.append(f"<![{data}]>")


def _wrap_plain_urls(value: str) -> str:
    parser = _PlainUrlLinkifier()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts)


def linkify_external_html(value: object) -> Markup:
    """Link plain-text URLs and route external anchors through the notice page."""

    if value is None:
        return Markup("")
    linked = bleach.linkify(
        _wrap_plain_urls(str(value)),
        callbacks=[_link_callback],
        skip_tags={"pre", "code", "script", "style", "textarea"},
        parse_email=False,
    )
    return Markup(linked)
