"""Hiring decisions, shared decision cards and versioned automation configuration."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    for schema, table in (("hire", "hire"), ("decision", "card"), ("automation", "configuration")):
        if pg:
            op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        op.create_table(
            table,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            schema=schema if pg else None,
        )


def downgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    for schema, table in (("automation", "configuration"), ("decision", "card"), ("hire", "hire")):
        op.drop_table(table, schema=schema if pg else None)
