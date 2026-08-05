"""Expand 演进示例：users 增加 updated_at（带默认值，旧代码无感知）

Revision ID: 0002_add_users_updated_at
Revises: 0001_initial
Create Date: 2026-08-04
"""
import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_users_updated_at"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 方向三：只做增量（加列带 server_default），不删改已有列
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "updated_at")