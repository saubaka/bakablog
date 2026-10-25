"""What the public may see. Every public query (lists, sitemap, search, counts) goes through these predicates."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_

from app.models import Moment, Page, Post
from app.timeutil import utcnow


def post_listed(now: datetime | None = None):
    """Shown in lists, archive, sitemap, search: published, its time has come, not in the trash."""
    return and_(Post.status == "published", Post.published_at <= (now or utcnow()), Post.deleted_at.is_(None))


def post_accessible(now: datetime | None = None):
    """Opens by its address: listed posts and "link only" posts."""
    return and_(Post.status.in_(("published", "unlisted")), Post.published_at <= (now or utcnow()), Post.deleted_at.is_(None))


def moment_listed(now: datetime | None = None):
    return and_(Moment.visibility == "public", Moment.published_at <= (now or utcnow()), Moment.deleted_at.is_(None))


def moment_accessible(now: datetime | None = None):
    return and_(Moment.visibility.in_(("public", "unlisted")), Moment.published_at <= (now or utcnow()), Moment.deleted_at.is_(None))


def page_listed():
    return and_(Page.status == "published", Page.deleted_at.is_(None))


def page_accessible():
    return and_(Page.status.in_(("published", "unlisted")), Page.deleted_at.is_(None))
