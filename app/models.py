"""Stage-four database models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


role_permissions = db.Table(
    "role_permissions",
    db.Column(
        "role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column(
        "permission_id",
        db.Integer,
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_roles = db.Table(
    "user_roles",
    db.Column(
        "user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column(
        "role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False, default="")


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    permissions = db.relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        backref=db.backref("roles", lazy="selectin"),
    )


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (db.Index("ix_users_active_created", "is_active", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    password_changed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    last_login_at = db.Column(db.DateTime(timezone=True))
    roles = db.relationship(
        "Role",
        secondary=user_roles,
        lazy="selectin",
        backref=db.backref("users", lazy="selectin"),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = utc_now()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_permission(self, code: str) -> bool:
        return any(
            permission.code in {code, "*"} for role in self.roles for permission in role.permissions
        )

    @property
    def is_superadmin(self) -> bool:
        return any(role.code == "superadmin" for role in self.roles)

    @property
    def can_login(self) -> bool:
        """Only the active built-in superadministrator may establish a session."""

        return self.is_active and self.is_superadmin


class UserSession(db.Model):
    __tablename__ = "user_sessions"
    __table_args__ = (
        db.Index("ix_user_sessions_user_active", "user_id", "revoked_at", "expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), index=True)
    user = db.relationship("User", lazy="joined")


class LoginLog(db.Model):
    __tablename__ = "login_logs"
    __table_args__ = (
        db.Index("ix_login_logs_created_success", "created_at", "success"),
        db.Index("ix_login_logs_username_created", "username", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username = db.Column(db.String(80), nullable=False)
    success = db.Column(db.Boolean, nullable=False)
    ip_address = db.Column(db.String(64), nullable=False, default="")
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    user = db.relationship("User", lazy="joined")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        db.Index("ix_audit_logs_created_action", "created_at", "action"),
        db.Index("ix_audit_logs_target", "target_type", "target_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(80), nullable=False)
    target_id = db.Column(db.String(80), nullable=False, default="")
    summary = db.Column(db.String(255), nullable=False, default="")
    request_id = db.Column(db.String(64), nullable=False, default="")
    ip_address = db.Column(db.String(64), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    actor = db.relationship("User", lazy="joined")


class Media(db.Model):
    __tablename__ = "media"
    __table_args__ = (
        db.Index("ix_media_created_type", "created_at", "mime_type"),
        db.CheckConstraint("size_bytes >= 0", name="ck_media_size_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    thumbnail_filename = db.Column(db.String(255), unique=True, nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(80), nullable=False, index=True)
    size_bytes = db.Column(db.Integer, nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    alt_text = db.Column(db.String(160), nullable=False, default="")
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="joined")


post_tags = db.Table(
    "post_tags",
    db.Column(
        "post_id", db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class Post(db.Model):
    __tablename__ = "posts"
    __table_args__ = (
        db.Index("ix_posts_publication", "status", "published_at", "deleted_at"),
        db.Index("ix_posts_category_publication", "category_id", "status", "published_at"),
        db.Index("ix_posts_featured_pinned", "is_featured", "is_pinned", "published_at"),
        db.CheckConstraint(
            "status IN ('draft', 'published', 'scheduled')", name="ck_posts_valid_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    summary = db.Column(db.String(360), nullable=False, default="")
    content_markdown = db.Column(db.Text, nullable=False, default="")
    content_html = db.Column(db.Text, nullable=False, default="")
    toc_html = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    allow_comments = db.Column(db.Boolean, nullable=False, default=False)
    reading_minutes = db.Column(db.Integer, nullable=False, default=1)
    seo_title = db.Column(db.String(180), nullable=False, default="")
    seo_description = db.Column(db.String(300), nullable=False, default="")
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"))
    cover_media_id = db.Column(db.Integer, db.ForeignKey("media.id", ondelete="SET NULL"))
    author_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, index=True
    )
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)
    category = db.relationship(
        "Category", lazy="joined", backref=db.backref("posts", lazy="dynamic")
    )
    cover_media = db.relationship("Media", lazy="joined")
    author = db.relationship("User", lazy="joined")
    tags = db.relationship(
        "Tag",
        secondary=post_tags,
        lazy="selectin",
        backref=db.backref("posts", lazy="dynamic"),
    )
    versions = db.relationship(
        "PostVersion",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="PostVersion.version_number.desc()",
    )


class PostVersion(db.Model):
    __tablename__ = "post_versions"
    __table_args__ = (
        db.UniqueConstraint("post_id", "version_number", name="uq_post_versions_number"),
        db.Index("ix_post_versions_post_created", "post_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(360), nullable=False, default="")
    content_markdown = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = db.relationship("User", lazy="joined")


class SiteProfile(db.Model):
    __tablename__ = "site_profiles"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(80), nullable=False, default="sau_baka")
    headline = db.Column(db.String(160), nullable=False, default="独立开发者 / 设计爱好者")
    location = db.Column(db.String(120), nullable=False, default="")
    email = db.Column(db.String(160), nullable=False, default="")
    short_bio = db.Column(db.String(360), nullable=False, default="")
    bio_markdown = db.Column(db.Text, nullable=False, default="")
    bio_html = db.Column(db.Text, nullable=False, default="")
    resume_url = db.Column(db.String(255), nullable=False, default="")
    avatar_media_id = db.Column(db.Integer, db.ForeignKey("media.id", ondelete="SET NULL"))
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    avatar_media = db.relationship("Media", lazy="joined")


class PersonalSkill(db.Model):
    __tablename__ = "personal_skills"
    __table_args__ = (db.CheckConstraint("level BETWEEN 0 AND 100", name="ck_skills_level"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    group_name = db.Column(db.String(80), nullable=False, default="技能")
    level = db.Column(db.Integer, nullable=False, default=80)
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)


class Experience(db.Model):
    __tablename__ = "experiences"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    organization = db.Column(db.String(140), nullable=False, default="")
    period = db.Column(db.String(80), nullable=False, default="")
    description = db.Column(db.String(500), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)


class PersonalGoal(db.Model):
    __tablename__ = "personal_goals"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.String(360), nullable=False, default="")
    status = db.Column(db.String(30), nullable=False, default="in_progress")
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)


class SocialLink(db.Model):
    __tablename__ = "social_links"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(80), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    icon_name = db.Column(db.String(40), nullable=False, default="link")
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)


class Project(db.Model):
    __tablename__ = "projects"
    __table_args__ = (
        db.Index("ix_projects_public", "status", "published_at", "deleted_at"),
        db.CheckConstraint("status IN ('draft', 'published')", name="ck_projects_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(180), nullable=False, unique=True, index=True)
    summary = db.Column(db.String(360), nullable=False, default="")
    content_markdown = db.Column(db.Text, nullable=False, default="")
    content_html = db.Column(db.Text, nullable=False, default="")
    tech_stack = db.Column(db.String(300), nullable=False, default="")
    project_url = db.Column(db.String(500), nullable=False, default="")
    repository_url = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    cover_media_id = db.Column(db.Integer, db.ForeignKey("media.id", ondelete="SET NULL"))
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)
    cover_media = db.relationship("Media", lazy="joined")


class Moment(db.Model):
    __tablename__ = "moments"
    __table_args__ = (
        db.Index("ix_moments_public", "status", "published_at", "deleted_at"),
        db.CheckConstraint("status IN ('draft', 'published')", name="ck_moments_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    content_markdown = db.Column(db.Text, nullable=False)
    content_html = db.Column(db.Text, nullable=False)
    mood = db.Column(db.String(40), nullable=False, default="晴朗")
    location = db.Column(db.String(120), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    allow_comments = db.Column(db.Boolean, nullable=False, default=False)
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)


class HomeModule(db.Model):
    __tablename__ = "home_modules"

    id = db.Column(db.Integer, primary_key=True)
    module_key = db.Column(db.String(50), nullable=False, unique=True, index=True)
    title = db.Column(db.String(100), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    item_limit = db.Column(db.Integer, nullable=False, default=3)
    style_variant = db.Column(db.String(40), nullable=False, default="cards")


class NavigationItem(db.Model):
    __tablename__ = "navigation_items"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(80), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    location = db.Column(db.String(20), nullable=False, default="header")
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    open_new_tab = db.Column(db.Boolean, nullable=False, default=False)


class SiteSetting(db.Model):
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(80), nullable=False, unique=True, index=True)
    setting_value = db.Column(db.Text, nullable=False, default="")


class ExternalLinkRule(db.Model):
    __tablename__ = "external_link_rules"
    __table_args__ = (
        db.CheckConstraint(
            "classification IN ('safe', 'dangerous')",
            name="ck_external_link_rules_classification",
        ),
        db.Index(
            "ix_external_link_rules_classification_hostname",
            "classification",
            "hostname",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(253), nullable=False, unique=True, index=True)
    classification = db.Column(db.String(20), nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False, default="")
    note = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CustomPage(db.Model):
    __tablename__ = "custom_pages"
    __table_args__ = (
        db.CheckConstraint("status IN ('draft', 'published')", name="ck_pages_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(180), nullable=False, unique=True, index=True)
    summary = db.Column(db.String(300), nullable=False, default="")
    content_markdown = db.Column(db.Text, nullable=False, default="")
    content_html = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    show_in_navigation = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class FriendCategory(db.Model):
    __tablename__ = "friend_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)


class FriendLink(db.Model):
    __tablename__ = "friend_links"
    __table_args__ = (
        db.Index("ix_friend_links_public", "status", "sort_order"),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'disabled')",
            name="ck_friend_links_status",
        ),
        db.CheckConstraint(
            "health_status IN ('unknown', 'ok', 'error')", name="ck_friend_links_health"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    application_code = db.Column(
        db.String(40), nullable=False, unique=True, index=True, default=lambda: uuid4().hex
    )
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    description = db.Column(db.String(300), nullable=False)
    avatar_url = db.Column(db.String(500), nullable=False, default="")
    applicant_email = db.Column(db.String(160), nullable=False, default="")
    ip_hash = db.Column(db.String(64), nullable=False, default="", index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("friend_categories.id", ondelete="SET NULL"))
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    health_status = db.Column(db.String(20), nullable=False, default="unknown", index=True)
    last_status_code = db.Column(db.Integer)
    last_checked_at = db.Column(db.DateTime(timezone=True))
    health_message = db.Column(db.String(255), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    category = db.relationship(
        "FriendCategory", lazy="joined", backref=db.backref("links", lazy="dynamic")
    )


class Album(db.Model):
    __tablename__ = "albums"
    __table_args__ = (
        db.Index("ix_albums_public", "status", "sort_order"),
        db.CheckConstraint("status IN ('draft', 'published')", name="ck_albums_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), nullable=False, unique=True, index=True)
    description = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    photos = db.relationship(
        "Photo", lazy="selectin", cascade="all, delete-orphan", order_by="Photo.sort_order"
    )


class Photo(db.Model):
    __tablename__ = "photos"
    __table_args__ = (db.Index("ix_photos_album_sort", "album_id", "sort_order"),)

    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(db.Integer, db.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey("media.id", ondelete="RESTRICT"), nullable=False)
    caption = db.Column(db.String(300), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    media = db.relationship("Media", lazy="joined")


class Comment(db.Model):
    __tablename__ = "comments"
    __table_args__ = (
        db.Index("ix_comments_post_public", "post_id", "status", "is_pinned", "created_at"),
        db.Index("ix_comments_moment_public", "moment_id", "status", "is_pinned", "created_at"),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'spam', 'blocked')", name="ck_comments_status"
        ),
        db.CheckConstraint("author_type IN ('visitor', 'staff')", name="ck_comments_author_type"),
        db.CheckConstraint(
            "(post_id IS NOT NULL AND moment_id IS NULL) OR "
            "(post_id IS NULL AND moment_id IS NOT NULL)",
            name="ck_comments_single_target",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"))
    moment_id = db.Column(db.Integer, db.ForeignKey("moments.id", ondelete="CASCADE"))
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"))
    admin_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    author_type = db.Column(db.String(20), nullable=False, default="visitor")
    author_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), nullable=False, default="")
    website = db.Column(db.String(500), nullable=False, default="")
    content = db.Column(db.String(3000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    like_count = db.Column(db.Integer, nullable=False, default=0)
    ip_hash = db.Column(db.String(64), nullable=False, default="", index=True)
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    post = db.relationship("Post", lazy="joined")
    moment = db.relationship("Moment", lazy="joined")
    parent = db.relationship(
        "Comment", remote_side=[id], backref=db.backref("replies", lazy="selectin")
    )
    admin_user = db.relationship("User", foreign_keys=[admin_user_id], lazy="joined")


class CommentReaction(db.Model):
    __tablename__ = "comment_reactions"
    __table_args__ = (
        db.UniqueConstraint("comment_id", "visitor_hash", name="uq_comment_reaction_visitor"),
    )

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(
        db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    visitor_hash = db.Column(db.String(64), nullable=False)
    reaction_type = db.Column(db.String(20), nullable=False, default="like")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class GuestbookMessage(db.Model):
    __tablename__ = "guestbook_messages"
    __table_args__ = (
        db.Index("ix_guestbook_public", "status", "is_pinned", "created_at"),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'spam', 'blocked')", name="ck_guestbook_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), nullable=False, default="")
    content = db.Column(db.String(3000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    admin_reply = db.Column(db.String(2000), nullable=False, default="")
    replied_at = db.Column(db.DateTime(timezone=True))
    ip_hash = db.Column(db.String(64), nullable=False, default="", index=True)
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class ModerationNotification(db.Model):
    __tablename__ = "moderation_notifications"
    __table_args__ = (db.Index("ix_notifications_read_created", "is_read", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(db.String(40), nullable=False)
    target_type = db.Column(db.String(40), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
