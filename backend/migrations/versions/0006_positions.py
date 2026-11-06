"""Position projection, generation decisions and per-consumer durable inbox."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    pos, platform = ("pos", "platform") if pg else (None, None)
    if pg:
        op.execute('CREATE SCHEMA IF NOT EXISTS "pos"')
    op.create_table(
        "position",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("dept", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("confidential", sa.Boolean(), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=pos,
    )
    op.create_index("ix_position_dept", "position", ["dept"], schema=pos)
    op.create_index("ix_position_signature", "position", ["signature"], schema=pos)
    op.create_table(
        "generation",
        sa.Column("requisition_id", sa.String(64), primary_key=True),
        sa.Column("position_id", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=pos,
    )
    op.create_index("ix_generation_position_id", "generation", ["position_id"], schema=pos)
    op.create_table(
        "inbox",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("consumer", sa.String(80), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        schema=platform,
    )


def downgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    op.drop_table("inbox", schema="platform" if pg else None)
    op.drop_table("generation", schema="pos" if pg else None)
    op.drop_table("position", schema="pos" if pg else None)
