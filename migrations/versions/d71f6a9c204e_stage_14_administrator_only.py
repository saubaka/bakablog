"""Stage fourteen: retire the member system and keep administrator access only.

The legacy member tables remain as empty compatibility structures so older
databases can still traverse the historical migration chain.  No runtime model,
route, form, template or service uses them after this revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "d71f6a9c204e"
down_revision = "b14d5f2e8c30"
branch_labels = None
depends_on = None


RETIRED_PERMISSIONS = (
    "users.view",
    "users.private.view",
    "users.manage",
    "users.moderate",
    "users.roles.manage",
    "roles.view",
    "roles.manage",
    "registration.manage",
    "sessions.manage",
    "user_data.manage",
    "user_notifications.manage",
)

RETIRED_SETTINGS = (
    "human_verification",
    "human_verification_config",
    "registration_mode",
    "require_email_verification",
    "allow_guest_comments",
    "allow_guest_guestbook",
    "allow_guest_reactions",
    "allow_guest_friend_links",
    "session_hours",
    "comment_edit_minutes",
    "deletion_cooling_days",
    "notification_retention_days",
    "avatar_max_bytes",
)


def upgrade() -> None:
    connection = op.get_bind()

    # Detach public interaction content from member accounts before deleting them.
    connection.execute(sa.text("UPDATE friend_links SET applicant_user_id = NULL"))
    connection.execute(sa.text("UPDATE guestbook_messages SET user_id = NULL"))
    connection.execute(sa.text("UPDATE comments SET user_id = NULL"))
    connection.execute(sa.text("DELETE FROM comment_reactions WHERE user_id IS NOT NULL"))
    connection.execute(sa.text("DELETE FROM comment_reports WHERE user_id IS NOT NULL"))

    # Remove every member-only data set, including login verification material.
    for table in (
        "user_tokens",
        "user_moderation_actions",
        "user_preferences",
        "user_notifications",
        "notification_broadcasts",
        "post_bookmarks",
        "user_recovery_codes",
        "user_deletion_requests",
    ):
        connection.execute(sa.text(f"DELETE FROM {table}"))

    # Keep accounts only when they belong to the single administrator role.
    connection.execute(
        sa.text(
            "DELETE FROM users WHERE id NOT IN ("
            "SELECT ur.user_id FROM user_roles ur "
            "JOIN roles r ON r.id = ur.role_id WHERE r.code = 'superadmin'"
            ")"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE users SET email = NULL, email_verified_at = NULL, "
            "suspended_until = NULL, status_reason = '', bio = '', website = '', "
            "profile_visibility = 'private', avatar_media_id = NULL, "
            "totp_seed = NULL, totp_enabled_at = NULL, last_seen_at = NULL, "
            "deleted_at = NULL, status = 'active', is_active = 1"
        )
    )

    connection.execute(
        sa.text(
            "DELETE FROM user_roles WHERE role_id IN "
            "(SELECT id FROM roles WHERE code <> 'superadmin')"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code <> 'superadmin')"
        )
    )
    connection.execute(sa.text("DELETE FROM roles WHERE code <> 'superadmin'"))

    retired_permissions = sa.bindparam("codes", expanding=True)
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(retired_permissions),
        {"codes": list(RETIRED_PERMISSIONS)},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": list(RETIRED_PERMISSIONS)},
    )
    connection.execute(
        sa.text("DELETE FROM site_settings WHERE setting_key IN :keys").bindparams(
            sa.bindparam("keys", expanding=True)
        ),
        {"keys": list(RETIRED_SETTINGS)},
    )


def downgrade() -> None:
    # Deliberately irreversible: deleted member accounts and verification secrets
    # must never be recreated from migration metadata.
    pass
