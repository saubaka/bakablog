from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime
from app.timeutil import utcnow


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text, default="")
    sticker: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    show_on_shelf: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    posts = relationship("Post", back_populates="category")


class Tag(Base):
    """Shared by posts and moments."""

    __tablename__ = "tags"
    __table_args__ = (CheckConstraint("color IN ('sky','rose','mist','white')", name="color"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(40, collation="NOCASE"), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(8), default="sky")
    sticker: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    posts = relationship("Post", secondary="post_tags", back_populates="tags")
    moments = relationship("Moment", secondary="moment_tags", back_populates="tags")


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (CheckConstraint("status IN ('ongoing','finished')", name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    cover_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), default="ongoing")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    cover = relationship("Media", foreign_keys=[cover_media_id])
    posts = relationship("Post", back_populates="series", order_by="Post.series_order")
