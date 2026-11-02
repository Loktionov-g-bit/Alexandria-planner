"""departments: update channel (stable | beta)

Revision ID: c4d2a7e81b05
Revises: b3c91e0d4f22
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d2a7e81b05"
down_revision = "b3c91e0d4f22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("departments") as b:
        b.add_column(sa.Column("update_channel", sa.String(8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("departments") as b:
        b.drop_column("update_channel")
