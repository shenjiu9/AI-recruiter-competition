"""Interview snapshots and non-overlapping interviewer/candidate reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    schema = "iv" if pg else None
    if pg:
        op.execute("CREATE SCHEMA IF NOT EXISTS iv")
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "interview",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("application_id", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=schema,
    )
    for name in ("application_id", "candidate_id"):
        op.create_index("ix_interview_" + name, "interview", [name], schema=schema)
    op.create_table(
        "availability",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=schema,
    )
    op.create_table(
        "reservation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("interview_id", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(80), nullable=False),
        sa.Column("slot_id", sa.String(64), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        schema=schema,
    )
    for name in ("interview_id", "resource"):
        op.create_index("ix_reservation_" + name, "reservation", [name], schema=schema)
    if pg:
        op.execute(
            "ALTER TABLE iv.reservation ADD CONSTRAINT reservation_no_overlap EXCLUDE USING gist (resource WITH =, tstzrange(start_at, end_at, '[)') WITH &&)"
        )


def downgrade():
    schema = "iv" if op.get_bind().dialect.name == "postgresql" else None
    for name in ("reservation", "availability", "interview"):
        op.drop_table(name, schema=schema)
