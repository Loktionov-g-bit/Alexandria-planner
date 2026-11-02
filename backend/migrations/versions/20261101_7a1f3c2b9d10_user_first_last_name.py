"""users: first_name and last_name (display_name stays as "first last")

Revision ID: 7a1f3c2b9d10
Revises: 2d4c8980c574
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = "7a1f3c2b9d10"
down_revision = "2d4c8980c574"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # expand-only: new columns with defaults, so the previous release keeps working on the same DB
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("first_name", sa.String(60), nullable=False, server_default=""))
        b.add_column(sa.Column("last_name", sa.String(60), nullable=False, server_default=""))
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("display_name", sa.String),
                     sa.column("first_name", sa.String), sa.column("last_name", sa.String))
    conn = op.get_bind()
    for uid, name in conn.execute(sa.select(users.c.id, users.c.display_name)).all():
        first, _, last = (name or "").strip().partition(" ")
        conn.execute(users.update().where(users.c.id == uid).values(first_name=first[:60], last_name=last.strip()[:60]))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("last_name")
        b.drop_column("first_name")
