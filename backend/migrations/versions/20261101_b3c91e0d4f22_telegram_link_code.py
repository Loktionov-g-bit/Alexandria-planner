"""users: one-time Telegram link code

Revision ID: b3c91e0d4f22
Revises: 8a46f21a2fb3
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c91e0d4f22"
down_revision = "8a46f21a2fb3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("telegram_link_code", sa.String(32), nullable=True))
        b.add_column(sa.Column("telegram_link_expires", sa.DateTime(timezone=True), nullable=True))
        b.create_unique_constraint("uq_users_telegram_link_code", ["telegram_link_code"])


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_telegram_link_code", type_="unique")
        b.drop_column("telegram_link_expires")
        b.drop_column("telegram_link_code")
