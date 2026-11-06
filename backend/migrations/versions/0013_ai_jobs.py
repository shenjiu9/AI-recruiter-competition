"""Durable AI jobs and encrypted action traces."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    schema = "engine" if op.get_bind().dialect.name == "postgresql" else None
    if schema:
        op.execute("CREATE SCHEMA IF NOT EXISTS engine")
    op.create_table(
        "job",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("partition_key", sa.String(80), nullable=False),
        sa.Column("queue", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=schema,
    )
    op.create_index("ix_job_due", "job", ["queue", "status", "due_at"], schema=schema)
    op.create_index("ix_job_partition_key", "job", ["partition_key"], schema=schema)


def downgrade():
    op.drop_table("job", schema="engine" if op.get_bind().dialect.name == "postgresql" else None)
