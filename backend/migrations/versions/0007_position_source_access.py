"""Separate revocable position membership from original requisition participants."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    schema = "req" if op.get_bind().dialect.name == "postgresql" else None
    op.create_table(
        "position_source_access",
        sa.Column("requisition_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), primary_key=True),
        schema=schema,
    )


def downgrade():
    schema = "req" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("position_source_access", schema=schema)
