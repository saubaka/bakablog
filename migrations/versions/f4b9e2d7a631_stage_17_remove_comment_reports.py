"""Stage seventeen: retire comment reporting and its stored data."""

import sqlalchemy as sa
from alembic import op

revision = "f4b9e2d7a631"
down_revision = "c6f9a2d81b47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM moderation_notifications "
        "WHERE target_type = 'report' OR notification_type = 'new_report'"
    )
    op.drop_table("comment_reports")
    op.drop_column("comments", "report_count")


def downgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "comment_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["comments.id"],
            name="fk_comment_reports_comment_id_comments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_comment_reports_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comment_id",
            "visitor_hash",
            name="uq_comment_report_visitor",
        ),
        sa.UniqueConstraint(
            "comment_id",
            "user_id",
            name="uq_comment_report_user",
        ),
    )
    op.create_index(
        op.f("ix_comment_reports_user_id"),
        "comment_reports",
        ["user_id"],
        unique=False,
    )
