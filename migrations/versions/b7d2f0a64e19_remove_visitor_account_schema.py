"""Remove the remaining visitor-account schema.

Revision ID: b7d2f0a64e19
Revises: a1c7e5f9032b
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d2f0a64e19"
down_revision = "a1c7e5f9032b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # Signed-in reactions have no visitor fingerprint and cannot participate in
    # the public, account-free reaction model.
    connection.execute(sa.text("DELETE FROM comment_reactions WHERE visitor_hash IS NULL"))

    for table in (
        "post_bookmarks",
        "user_deletion_requests",
        "user_moderation_actions",
        "user_notifications",
        "user_preferences",
        "user_recovery_codes",
        "user_tokens",
        "notification_broadcasts",
    ):
        op.drop_table(table)

    with op.batch_alter_table("comments") as batch:
        batch.drop_index("ix_comments_user_id")
        batch.drop_constraint("fk_comments_user_id_users", type_="foreignkey")
        batch.drop_constraint("ck_comments_author_type", type_="check")
        batch.drop_column("user_id")
        batch.create_check_constraint(
            "ck_comments_author_type", "author_type IN ('visitor', 'staff')"
        )

    with op.batch_alter_table("comment_reactions") as batch:
        batch.drop_index("ix_comment_reactions_user_id")
        batch.drop_constraint("fk_comment_reactions_user_id_users", type_="foreignkey")
        batch.drop_constraint("uq_comment_reaction_user", type_="unique")
        batch.drop_column("user_id")
        batch.alter_column(
            "visitor_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )

    with op.batch_alter_table("guestbook_messages") as batch:
        batch.drop_index("ix_guestbook_messages_user_id")
        batch.drop_constraint("fk_guestbook_messages_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("friend_links") as batch:
        batch.drop_constraint("fk_friend_links_applicant_user_id_users", type_="foreignkey")
        batch.drop_column("applicant_user_id")

    for index_name in (
        "ix_users_status_created",
        "ix_users_deleted_at",
        "ix_users_status",
        "ix_users_email",
    ):
        op.drop_index(index_name, table_name="users")
    for column_name in (
        "email",
        "status",
        "email_verified_at",
        "suspended_until",
        "status_reason",
        "bio",
        "website",
        "profile_visibility",
        "last_seen_at",
        "deleted_at",
        "avatar_media_id",
        "totp_seed",
        "totp_enabled_at",
    ):
        # SQLite 3.35+ can safely drop these now-unindexed legacy columns
        # without rebuilding users and triggering user_roles cascades.
        op.drop_column("users", column_name)


def downgrade() -> None:
    raise RuntimeError("访客账号数据结构已永久移除，请通过完整站点备份回退。")
