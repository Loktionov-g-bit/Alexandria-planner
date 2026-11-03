"""users: absence with a deputy, personal calendar feed token

Revision ID: f5b1c8d2e4a7
Revises: e2a8b5c7d913
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "f5b1c8d2e4a7"
down_revision = "e2a8b5c7d913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("away_from", sa.Date(), nullable=True))
        b.add_column(sa.Column("away_until", sa.Date(), nullable=True))
        b.add_column(sa.Column("deputy_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("calendar_token", sa.String(length=64), nullable=True))
        b.create_foreign_key("fk_users_deputy_id_users", "users", ["deputy_id"], ["id"], ondelete="SET NULL")
        b.create_unique_constraint("uq_users_calendar_token", ["calendar_token"])


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_calendar_token", type_="unique")
        b.drop_constraint("fk_users_deputy_id_users", type_="foreignkey")
        b.drop_column("calendar_token")
        b.drop_column("deputy_id")
        b.drop_column("away_until")
        b.drop_column("away_from")
