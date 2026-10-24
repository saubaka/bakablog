from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime
from app.timeutil import utcnow


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (CheckConstraint("kind IN ('image','icon')", name="kind"), Index("ix_media_deleted", "deleted_at"))

    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of the uploaded bytes (24 hex characters); names the files on disk
    filename: Mapped[str] = mapped_column(String(255), default="")  # display only, never used as a path
    kind: Mapped[str] = mapped_column(String(8), default="image")
    mime: Mapped[str] = mapped_column(String(40), default="")  # type of the original upload
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int] = mapped_column(Integer, default=0)  # size of the original upload
    alt: Mapped[str] = mapped_column(String(300), default="")
    caption: Mapped[str] = mapped_column(String(500), default="")
    color: Mapped[str] = mapped_column(String(7), default="#e6f1fc")  # dominant colour, the placeholder while the image loads
    variants: Mapped[list] = mapped_column(JSON, default=list)  # [{"size": 480, "w": 480, "h": 320, "bytes": 12345}, ...]
    animated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class MediaRef(Base):
    """Where a picture is used. Recomputed whenever the content that uses it is saved."""

    __tablename__ = "media_refs"
    __table_args__ = (
        UniqueConstraint("media_id", "entity_type", "entity_id", name="uq_media_refs_entity"),
        Index("ix_media_refs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # post | moment | page | series | setting | home_block
    entity_id: Mapped[int] = mapped_column(Integer, default=0)
