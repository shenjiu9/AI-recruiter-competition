"""Retain normalized identity aliases from older resume versions."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    schema = "cand" if op.get_bind().dialect.name == "postgresql" else None
    table = op.create_table(
        "candidate_identity",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        schema=schema,
    )
    op.create_index(
        "ix_candidate_identity_candidate_id", "candidate_identity", ["candidate_id"], schema=schema
    )
    candidates = sa.table(
        "candidate",
        sa.column("id"),
        sa.column("phone_hash"),
        sa.column("email_hash"),
        schema=schema,
    )
    for row in op.get_bind().execute(sa.select(candidates)):
        for digest in {row.phone_hash, row.email_hash} - {None}:
            op.get_bind().execute(table.insert().values(digest=digest, candidate_id=row.id))


def downgrade():
    op.drop_table(
        "candidate_identity", schema="cand" if op.get_bind().dialect.name == "postgresql" else None
    )
