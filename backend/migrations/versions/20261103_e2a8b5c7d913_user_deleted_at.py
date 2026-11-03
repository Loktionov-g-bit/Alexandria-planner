"""users: deleted_at (account erased by an admin, kept only as a name in history)

Revision ID: e2a8b5c7d913
Revises: d7e3f19a2c41
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "e2a8b5c7d913"
down_revision = "d7e3f19a2c41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
