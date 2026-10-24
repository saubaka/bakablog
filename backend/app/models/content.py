from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, Float, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime
from app.timeutil import utcnow

post_tags = Table(
    "post_tags", Base.metadata,
    Column("post_id", ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_post_tags_tag", "tag_id"),
)

moment_tags = Table(
    "moment_tags", Base.metadata,
    Column("moment_id", ForeignKey("moments.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_moment_tags_tag", "tag_id"),
)


class Post(Base):
    """status: draft | published | unlisted (link only) | private (admin only).
    A published post whose published_at is still in the future is "scheduled": it appears when the time comes."""

    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("status IN ('draft','published','unlisted','private')", name="status"),
        CheckConstraint("card_style IN ('auto','cover','side','note','quote')", name="card_style"),
        Index("ix_posts_status_published", "status", "published_at"),
        Index("ix_posts_deleted", "deleted_at"),
        Index("ix_posts_category", "category_id"),
        Index("ix_posts_series", "series_id", "series_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")  # empty in the editor = taken from the text at save time
    summary_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    content_md: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    toc: Mapped[list] = mapped_column(JSON, default=list)
    reading_minutes: Mapped[int] = mapped_column(Integer, default=1)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    cover_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    cover_alt: Mapped[str] = mapped_column(String(300), default="")
    cover_focus_x: Mapped[float] = mapped_column(Float, default=50.0)
    cover_focus_y: Mapped[float] = mapped_column(Float, default=50.0)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    series_order: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(10), default="draft")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    card_style: Mapped[str] = mapped_column(String(8), default="auto")
    show_toc: Mapped[bool] = mapped_column(Boolean, default=True)
    show_reading_time: Mapped[bool] = mapped_column(Boolean, default=True)
    show_author_card: Mapped[bool] = mapped_column(Boolean, default=False)

    seo_title: Mapped[str] = mapped_column(String(200), default="")
    seo_description: Mapped[str] = mapped_column(String(400), default="")
    seo_image_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    canonical_url: Mapped[str] = mapped_column(String(500), default="")

    view_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    category = relationship("Category", back_populates="posts")
    series = relationship("Series", back_populates="posts")
    cover = relationship("Media", foreign_keys=[cover_media_id])
    seo_image = relationship("Media", foreign_keys=[seo_image_media_id])
    tags = relationship("Tag", secondary=post_tags, back_populates="posts", order_by="Tag.name")


class Moment(Base):
    __tablename__ = "moments"
    __table_args__ = (
        CheckConstraint("visibility IN ('public','unlisted','private')", name="visibility"),
        Index("ix_moments_published", "visibility", "published_at"),
        Index("ix_moments_deleted", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_md: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    mood: Mapped[str | None] = mapped_column(String(16))
    link_card: Mapped[dict | None] = mapped_column(JSON)  # {"url", "title", "description", "domain", "icon_media_id"}
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(10), default="public")
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    tags = relationship("Tag", secondary=moment_tags, back_populates="moments", order_by="Tag.name")
    media = relationship("MomentMedia", order_by="MomentMedia.position", cascade="all, delete-orphan", back_populates="moment")


class MomentMedia(Base):
    __tablename__ = "moment_media"

    moment_id: Mapped[int] = mapped_column(ForeignKey("moments.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    alt: Mapped[str] = mapped_column(String(300), default="")

    moment = relationship("Moment", back_populates="media")
    image = relationship("Media")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        CheckConstraint("status IN ('draft','published','unlisted','private')", name="status"),
        CheckConstraint("template IN ('plain','wide','sidebar')", name="template"),
        Index("ix_pages_deleted", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    content_md: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    toc: Mapped[list] = mapped_column(JSON, default=list)
    template: Mapped[str] = mapped_column(String(8), default="plain")
    status: Mapped[str] = mapped_column(String(10), default="draft")
    seo_title: Mapped[str] = mapped_column(String(200), default="")
    seo_description: Mapped[str] = mapped_column(String(400), default="")
    seo_image_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    seo_image = relationship("Media", foreign_keys=[seo_image_media_id])
