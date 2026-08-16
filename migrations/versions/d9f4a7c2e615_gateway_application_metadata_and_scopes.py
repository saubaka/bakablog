"""Store Cloudgate application metadata and requested permissions."""

import sqlalchemy as sa
from alembic import op

revision = "d9f4a7c2e615"
down_revision = "b8d2e4f6a913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("gateway_configurations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "application_name",
                sa.String(length=100),
                nullable=False,
                server_default="Cloud Diary",
            )
        )
        batch_op.add_column(
            sa.Column(
                "application_description",
                sa.String(length=240),
                nullable=False,
                server_default="记录文章、项目与生活时刻的个人博客。",
            )
        )
        batch_op.add_column(
            sa.Column(
                "application_homepage_url",
                sa.String(length=500),
                nullable=False,
                server_default="http://127.0.0.1:5000",
            )
        )
        batch_op.add_column(
            sa.Column(
                "privacy_policy_url",
                sa.String(length=500),
                nullable=False,
                server_default="http://127.0.0.1:5000/privacy/",
            )
        )
        batch_op.add_column(
            sa.Column(
                "application_icon_url",
                sa.String(length=500),
                nullable=False,
                server_default="http://127.0.0.1:5000/static/icons/cloud-diary-app.svg",
            )
        )
    op.execute(
        "UPDATE gateway_configurations "
        "SET scopes = 'openid profile email avatar' "
        "WHERE scopes = 'openid profile email'"
    )


def downgrade() -> None:
    with op.batch_alter_table("gateway_configurations") as batch_op:
        batch_op.drop_column("application_icon_url")
        batch_op.drop_column("privacy_policy_url")
        batch_op.drop_column("application_homepage_url")
        batch_op.drop_column("application_description")
        batch_op.drop_column("application_name")
