"""Validation of the settings groups (what the admin may store). Free colours are deliberately not possible: only the presets."""
from __future__ import annotations

import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import defaults


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _url(value: str, *, allow_mail: bool = True) -> str:
    value = value.strip()
    if value.startswith(("/", "#")) and not value.startswith("//"):
        return value
    if re.match(r"^https?://[^\s/]+", value):
        return value
    if allow_mail and re.match(r"^(mailto:[^\s@]+@[^\s@]+|tel:[+\d\-\s()]+)$", value):
        return value
    raise ValueError("需要 http(s) 链接、站内路径或 mailto:")


class SiteIn(_M):
    name: str = Field(min_length=1, max_length=60)
    name_en: str = Field(max_length=60)
    tagline: str = Field(max_length=80)
    description: str = Field(max_length=300)
    language: str = Field(pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
    timezone: str
    logo_media_id: int | None = None
    favicon_media_id: int | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError("不认识这个时区，例如 Asia/Shanghai") from exc
        return v


class AuthorLink(_M):
    label: str = Field(min_length=1, max_length=20)
    kind: Literal["mail", "link"]
    url: str = Field(min_length=1, max_length=300)

    @field_validator("url")
    @classmethod
    def _u(cls, v: str) -> str:
        return _url(v)


class AuthorIn(_M):
    name: str = Field(min_length=1, max_length=40)
    bio: str = Field(max_length=600)
    avatar_media_id: int | None = None
    links: list[AuthorLink] = Field(max_length=8)


class Decor(_M):
    tape: bool
    doodles: bool


class CopyIn(_M):
    not_found_title: str = Field(max_length=40)
    not_found_text: str = Field(max_length=200)
    error_title: str = Field(max_length=40)
    error_text: str = Field(max_length=200)


class AppearanceIn(_M):
    theme: Literal["default", "sky", "sakura", "fog"]
    decor: Decor
    motion: Literal["full", "soft", "off"]
    code_theme: Literal["frost", "blossom", "fog"]
    texts: CopyIn


class SitemapIn(_M):
    moments: bool
    pages: bool
    taxonomy: bool


_ROBOTS_LINE = re.compile(r"^(#.*|(Disallow|Allow|Crawl-delay|User-agent|Noindex):\s*\S.*)$", re.I)


class SeoIn(_M):
    title: str = Field(max_length=120)
    description: str = Field(max_length=300)
    keywords: list[str] = Field(max_length=15)
    share_image_media_id: int | None = None
    robots_extra: str = Field(max_length=2000)
    sitemap: SitemapIn

    @field_validator("keywords")
    @classmethod
    def _kw(cls, v: list[str]) -> list[str]:
        return [k.strip()[:30] for k in v if k.strip()]

    @field_validator("robots_extra")
    @classmethod
    def _robots(cls, v: str) -> str:
        lines = [ln.rstrip() for ln in v.splitlines() if ln.strip()]
        for ln in lines:
            if not _ROBOTS_LINE.match(ln.strip()):
                raise ValueError(f"不是有效的 robots 规则：{ln[:40]}")
        return "\n".join(lines)


class FooterIn(_M):
    icp: str = Field(max_length=60)
    copyright: str = Field(max_length=120)
    text: str = Field(max_length=200)


class StatsIn(_M):
    enabled: bool


class BackupIn(_M):
    enabled: bool
    hour: int = Field(ge=0, le=23)
    keep: int = Field(ge=1, le=60)


MODELS: dict[str, type[_M]] = {
    "site": SiteIn, "author": AuthorIn, "appearance": AppearanceIn, "seo": SeoIn, "footer": FooterIn, "stats": StatsIn, "backup": BackupIn,
}
# which fields of which group point at pictures (they must exist, and are recorded as "used")
MEDIA_FIELDS: dict[str, tuple[str, ...]] = {
    "site": ("logo_media_id", "favicon_media_id"), "author": ("avatar_media_id",), "seo": ("share_image_media_id",),
}

_ = defaults
