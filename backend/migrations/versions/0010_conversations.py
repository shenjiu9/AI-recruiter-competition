"""Encrypted candidate conversations and durable H5 delivery queue."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    schema = "comm" if op.get_bind().dialect.name == "postgresql" else None
    if schema:
        op.execute("CREATE SCHEMA IF NOT EXISTS comm")
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=schema,
    )


def downgrade():
    schema = "comm" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("conversation", schema=schema)
