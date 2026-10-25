"""Validation of the home page modules."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import defaults
from app.timeutil import iso, parse_iso


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Button(_M):
    label: str = Field(min_length=1, max_length=20)
    url: str = Field(min_length=1, max_length=300)
    style: Literal["fill", "line", "link"] = "line"

    @field_validator("url")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("/") and not v.startswith("//") or v.startswith(("http://", "https://", "mailto:")):
            return v
        raise ValueError("需要站内路径或 http(s) 链接")


class Hero(_M):
    note: str = Field(default="", max_length=60)
    intro: str = Field(default="", max_length=300)
    buttons: list[Button] = Field(default_factory=list, max_length=3)
    doodles: list[Literal["star", "heart", "sparkle", "flower", "paw", "wave", "loop"]] = Field(default_factory=list, max_length=3)


class Featured(_M):
    title: str = Field(default="精选", max_length=30)
    mode: Literal["auto", "manual"] = "auto"
    post_ids: list[int] = Field(default_factory=list, max_length=6)
    count: int = Field(default=3, ge=1, le=6)


class LatestPosts(_M):
    title: str = Field(default="最近的文章", max_length=30)
    intro: str = Field(default="", max_length=120)
    count: int = Field(default=6, ge=1, le=12)
    layout: Literal["mixed", "list", "grid"] = "mixed"


class LatestMoments(_M):
    title: str = Field(default="最近的动态", max_length=30)
    intro: str = Field(default="", max_length=120)
    count: int = Field(default=3, ge=1, le=8)


class Shelf(_M):
    title: str = Field(default="书架", max_length=30)
    intro: str = Field(default="", max_length=120)
    tag_count: int = Field(default=14, ge=0, le=30)


class About(_M):
    title: str = Field(default="关于我", max_length=30)
    intro: str = Field(default="", max_length=120)
    text: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("text")
    @classmethod
    def _t(cls, v: list[str]) -> list[str]:
        return [p.strip()[:400] for p in v if p.strip()]


class NowItem(_M):
    icon: str
    text: str = Field(min_length=1, max_length=60)

    @field_validator("icon")
    @classmethod
    def _i(cls, v: str) -> str:
        if v not in defaults.ICONS:
            raise ValueError("没有这个图标")
        return v


class Now(_M):
    title: str = Field(default="近况", max_length=20)
    items: list[NowItem] = Field(default_factory=list, max_length=6)


class Notice(_M):
    text: str = Field(default="", max_length=160)
    starts_at: str | None = None
    ends_at: str | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _d(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        try:
            return iso(parse_iso(v))
        except ValueError as exc:
            raise ValueError("时间格式不对，例如 2026-10-22T08:00:00Z") from exc


CONFIG_MODELS: dict[str, type[_M]] = {
    "hero": Hero, "featured": Featured, "latest_posts": LatestPosts, "latest_moments": LatestMoments, "shelf": Shelf, "about": About,
    "now": Now, "notice": Notice,
}


class BlockIn(_M):
    type: Literal["hero", "featured", "latest_posts", "latest_moments", "shelf", "about", "now", "notice"]
    enabled: bool = True
    config: dict = Field(default_factory=dict)


def parse_time(value: str | None) -> datetime | None:
    return parse_iso(value) if value else None
