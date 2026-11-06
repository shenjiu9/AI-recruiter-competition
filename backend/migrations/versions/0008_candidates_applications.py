"""Encrypted candidate files, identity dedupe and active application uniqueness."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    cand, appl = ("cand", "appl") if pg else (None, None)
    op.create_table(
        "candidate",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("phone_hash", sa.String(64), unique=True),
        sa.Column("email_hash", sa.String(64), unique=True),
        sa.Column("merged_into", sa.String(64)),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=cand,
    )
    op.create_index("ix_candidate_merged_into", "candidate", ["merged_into"], schema=cand)
    op.create_table(
        "resume",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        schema=cand,
    )
    op.create_index("ix_resume_candidate_id", "resume", ["candidate_id"], schema=cand)
    op.create_table(
        "application",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("position_id", sa.String(64), nullable=False),
        sa.Column("active_key", sa.String(140), unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        schema=appl,
    )
    for column in ("candidate_id", "position_id"):
        op.create_index("ix_application_" + column, "application", [column], schema=appl)


def downgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    op.drop_table("application", schema="appl" if pg else None)
    op.drop_table("resume", schema="cand" if pg else None)
    op.drop_table("candidate", schema="cand" if pg else None)
