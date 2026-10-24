from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PageView(Base):
    """Anonymous daily counters. No cookies, no addresses."""

    __tablename__ = "page_views"
    __table_args__ = (UniqueConstraint("day", "kind", "ref_id", name="uq_page_views_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(12))  # post | moment | page | home | list
    ref_id: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    uniques: Mapped[int] = mapped_column(Integer, default=0)


class Referrer(Base):
    __tablename__ = "referrers"
    __table_args__ = (UniqueConstraint("day", "domain", name="uq_referrers_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    domain: Mapped[str] = mapped_column(String(120))
    count: Mapped[int] = mapped_column(Integer, default=0)


class DeviceStat(Base):
    __tablename__ = "device_stats"
    __table_args__ = (UniqueConstraint("day", "device", name="uq_device_stats_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    device: Mapped[str] = mapped_column(String(12))  # phone | tablet | desktop | other
    count: Mapped[int] = mapped_column(Integer, default=0)


class Visitor(Base):
    """Who has already been counted today, per page: sha256 of a daily random salt + address prefix + browser. The salt and
    these rows are deleted when the day ends, so nothing links one day's visit to the next."""

    __tablename__ = "visitors"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    hash: Mapped[str] = mapped_column(String(32), primary_key=True)
    page_key: Mapped[str] = mapped_column(String(32), primary_key=True)  # "*" for the whole site, else "post:12"
