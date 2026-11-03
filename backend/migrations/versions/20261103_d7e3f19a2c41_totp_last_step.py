"""users: last accepted TOTP step (each 2FA code works only once)

Revision ID: d7e3f19a2c41
Revises: c4d2a7e81b05
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "d7e3f19a2c41"
down_revision = "c4d2a7e81b05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_last_step", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_last_step")
