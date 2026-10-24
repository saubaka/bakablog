from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime
from app.timeutil import utcnow


class Setting(Base):
    """key -> JSON. Only what the admin changed is stored; defaults come from app/defaults.py."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class HomeBlock(Base):
    """The home page is a list of blocks. No rows at all = the default layout."""

    __tablename__ = "home_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NavItem(Base):
    """No rows at all = the default navigation."""

    __tablename__ = "nav_items"
    __table_args__ = (
        CheckConstraint("region IN ('top','mobile','footer')", name="region"),
        Index("ix_nav_items_region", "region", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(8))
    label: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))  # route | page | category | tag | series | link | action
    target: Mapped[str] = mapped_column(String(300), default="")
    sticker: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Redirect(Base):
    __tablename__ = "redirects"
    __table_args__ = (CheckConstraint("status_code IN (301,302)", name="status_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(300), unique=True)
    target: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int] = mapped_column(Integer, default=301)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    auto: Mapped[bool] = mapped_column(Boolean, default=False)  # created by a slug change
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
